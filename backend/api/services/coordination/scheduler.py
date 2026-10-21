"""Persistent dependency scheduler with compare-and-set claims and bounded retries."""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

from api.services.coordination.contracts import (
    AgentEvent,
    AgentRole,
    Checkpoint,
    EventType,
    Finding,
    Run,
    Task,
    TaskStatus,
    generate_id,
    now_iso,
)
from api.services.coordination.graph_store import CoordinationGraphStore


WorkerResult = tuple[bool, dict[str, Any], list[Finding], str | None]


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
    except ValueError:
        return None


class DependencyScheduler:
    """Coordinate read-only workers; tasks, claims, transitions, and checkpoints live in the graph."""

    def __init__(self, store: CoordinationGraphStore, *, retry_base_seconds: int = 1,
                 retry_max_seconds: int = 60) -> None:
        self.store = store
        self.retry_base_seconds = max(1, retry_base_seconds)
        self.retry_max_seconds = max(self.retry_base_seconds, retry_max_seconds)

    def evaluate_readiness(self, run_id: str) -> list[Task]:
        tasks = self.store.list_tasks_for_run(run_id)
        task_map = {task.task_id: task for task in tasks}
        ready: list[Task] = []
        now = datetime.now(UTC)

        for task in tasks:
            status = str(task.status)
            if status in (TaskStatus.CLAIMED.value, TaskStatus.RUNNING.value):
                expiry = _parse_time(task.lease_expires_at)
                if expiry and expiry <= now and self.store.recover_expired_lease(task):
                    self._event(task, EventType.TASK_READY, "scheduler", "scheduler",
                                {"reason": "expired worker lease recovered"},
                                f"{task.task_id}:LEASE_EXPIRED:{task.attempt}")
                    task = self.store.get_task(task.task_id) or task
                    status = str(task.status)

            if status in (TaskStatus.PENDING.value, TaskStatus.WAITING_FOR_DEPENDENCY.value):
                dependencies = [task_map.get(dep_id) for dep_id in task.depends_on]
                if any(dep is None or str(dep.status) in (TaskStatus.FAILED.value, TaskStatus.CANCELLED.value)
                       for dep in dependencies):
                    changed = self.store.transition_task(
                        task.task_id, expected_status=status, new_status=TaskStatus.FAILED,
                        error="PREREQUISITE_FAILED", claimed_by="", lease_expires_at="",
                    )
                    if changed:
                        self._event(task, EventType.TASK_FAILED, "scheduler", "scheduler",
                                    {"reason": "prerequisite failed"}, f"{task.task_id}:PREREQUISITE_FAILED")
                    continue
                if all(dep and str(dep.status) == TaskStatus.SUCCEEDED.value for dep in dependencies):
                    retry_at = _parse_time(task.next_attempt_at)
                    if retry_at and retry_at > now:
                        continue
                    changed = self.store.transition_task(
                        task.task_id, expected_status=status, new_status=TaskStatus.READY,
                        claimed_by="", lease_expires_at="",
                    )
                    if changed:
                        self._event(task, EventType.TASK_READY, "scheduler", "scheduler",
                                    {"reason": "dependencies satisfied"},
                                    f"{task.task_id}:READY:{task.attempt}")
                        task = self.store.get_task(task.task_id) or task
                        ready.append(task)
                    continue
                if status == TaskStatus.PENDING.value and dependencies:
                    changed = self.store.transition_task(
                        task.task_id, expected_status=TaskStatus.PENDING,
                        new_status=TaskStatus.WAITING_FOR_DEPENDENCY,
                    )
                    if changed:
                        self._event(task, EventType.TASK_WAITING, "scheduler", "scheduler",
                                    {"reason": "prerequisites are not complete"},
                                    f"{task.task_id}:WAITING_FOR_DEPENDENCY")
                continue

            if status == TaskStatus.READY.value:
                retry_at = _parse_time(task.next_attempt_at)
                if not retry_at or retry_at <= now:
                    ready.append(task)
        return ready

    def claim_task(self, task_id: str, agent_id: str, lease_seconds: int = 30) -> bool:
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        task = self.store.get_task(task_id)
        if not task or str(task.status) != TaskStatus.READY.value:
            return False
        lease = (datetime.now(UTC) + timedelta(seconds=max(lease_seconds, task.timeout_seconds))).isoformat()
        claimed = self.store.claim_task(task_id, agent_id, lease)
        if claimed:
            updated = self.store.get_task(task_id) or task
            self._event(updated, EventType.TASK_CLAIMED, agent_id, str(updated.assigned_role),
                        {"attempt": updated.attempt, "lease_expires_at": lease},
                        f"{task_id}:CLAIMED:{updated.attempt}")
        return claimed

    def start_running(self, task_id: str, agent_id: str, *, expected_attempt: int) -> bool:
        task = self.store.get_task(task_id)
        if not task or task.attempt != expected_attempt:
            return False
        changed = self.store.transition_task(
            task_id, expected_status=TaskStatus.CLAIMED, expected_claimed_by=agent_id,
            expected_attempt=expected_attempt, new_status=TaskStatus.RUNNING, claimed_by=agent_id,
        )
        if changed:
            self._event(task, EventType.TOOL_INVOKED, agent_id, str(task.assigned_role),
                        {"capability_id": task.capability_id, "goal": task.goal},
                        f"{task_id}:TOOL_INVOKED:{task.attempt}")
        return changed

    def complete_task(
        self, task_id: str, agent_id: str, result_data: dict[str, Any],
        findings: list[Finding] | None = None,
        *, expected_attempt: int,
    ) -> bool:
        task = self.store.get_task(task_id)
        if not task or task.attempt != expected_attempt:
            return False
        target = TaskStatus.WAITING_FOR_REVIEW if task.requires_human_review else TaskStatus.SUCCEEDED
        changed = self.store.transition_task(
            task_id, expected_status=TaskStatus.RUNNING, expected_claimed_by=agent_id,
            expected_attempt=expected_attempt,
            new_status=target, claimed_by="", lease_expires_at="", next_attempt_at="",
            result_data=result_data, error="",
        )
        if not changed:
            return False
        for finding in findings or []:
            self.store.record_finding(finding)
            self._event(task, EventType.FINDING_RECORDED, agent_id, str(task.assigned_role),
                        {"finding_id": finding.finding_id, "cited_ids": finding.cited_ids},
                        f"{finding.finding_id}:RECORDED")
        self._event(task, EventType.TASK_COMPLETED, agent_id, str(task.assigned_role),
                    {"result_keys": sorted(result_data), "status": str(target)},
                    f"{task_id}:COMPLETED:{task.attempt}")
        if target == TaskStatus.WAITING_FOR_REVIEW:
            self._event(task, EventType.REVIEW_REQUESTED, agent_id, str(task.assigned_role),
                        {"status": "WAITING_FOR_REVIEW"},
                        f"{task_id}:REVIEW_REQUESTED:{task.attempt}")
        self.evaluate_readiness(task.run_id)
        return True

    def fail_task(self, task_id: str, agent_id: str, error: str, *, expected_attempt: int) -> bool:
        task = self.store.get_task(task_id)
        if not task or task.attempt != expected_attempt:
            return False
        if task.attempt < task.max_attempts:
            delay = min(self.retry_max_seconds, self.retry_base_seconds * (2 ** max(0, task.attempt - 1)))
            retry_at = (datetime.now(UTC) + timedelta(seconds=delay)).isoformat()
            target = TaskStatus.READY
            reason = "bounded retry scheduled"
            event_type = EventType.TASK_READY
        else:
            retry_at = ""
            target = TaskStatus.FAILED
            reason = "retry budget exhausted"
            event_type = EventType.TASK_FAILED
        changed = self.store.transition_task(
            task_id, expected_status=TaskStatus.RUNNING, expected_claimed_by=agent_id,
            expected_attempt=expected_attempt,
            new_status=target, claimed_by="", lease_expires_at="",
            next_attempt_at=retry_at, error=error,
        )
        if changed:
            self._event(task, event_type, agent_id, str(task.assigned_role),
                        {"reason": reason, "error": error, "retry_at": retry_at or None},
                        f"{task_id}:{target}:{task.attempt}")
            if target == TaskStatus.FAILED:
                self.evaluate_readiness(task.run_id)
        return changed

    def cancel_task(self, task_id: str, actor_id: str) -> bool:
        """Cancel a nonterminal task; a late read-only worker cannot commit after the status CAS."""
        task = self.store.get_task(task_id)
        if not task or str(task.status) in {
            TaskStatus.SUCCEEDED.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value,
        }:
            return False
        changed = self.store.transition_task(
            task_id, expected_status=task.status, expected_claimed_by=task.claimed_by or "",
            expected_attempt=task.attempt,
            new_status=TaskStatus.CANCELLED, claimed_by="", lease_expires_at="",
            next_attempt_at="", error="CANCELLED_BY_USER",
        )
        if changed:
            self._event(task, EventType.TASK_CANCELLED, actor_id, "operator",
                        {"previous_status": str(task.status)},
                        f"{task_id}:CANCELLED:{task.attempt}")
            self.evaluate_readiness(task.run_id)
        return changed

    def _event(self, task: Task, event_type: EventType, agent_id: str, role: str,
               payload: dict[str, Any], idempotency_key: str) -> None:
        self.store.record_event(AgentEvent(
            event_id=generate_id("evt"), run_id=task.run_id, task_id=task.task_id,
            event_type=event_type, agent_id=agent_id, role=role, payload=payload,
            idempotency_key=idempotency_key,
        ))

    def run_parallel_cycle(
        self,
        run_id: str,
        workers: dict[str, Callable[[Task], WorkerResult]],
        max_workers: int = 4,
    ) -> dict[str, Any]:
        if max_workers < 1:
            raise ValueError("max_workers must be positive")
        ready = self.evaluate_readiness(run_id)
        tasks_to_run: list[tuple[Task, str, Callable[[Task], WorkerResult]]] = []
        for task in ready:
            worker = workers.get(str(task.assigned_role)) or workers.get("default")
            agent_id = f"worker_{task.assigned_role}"
            if worker and self.claim_task(task.task_id, agent_id):
                claimed_task = self.store.get_task(task.task_id)
                if claimed_task and self.start_running(task.task_id, agent_id,
                                                       expected_attempt=claimed_task.attempt):
                    tasks_to_run.append((self.store.get_task(task.task_id) or claimed_task,
                                         agent_id, worker))

        if not tasks_to_run:
            all_tasks = self.store.list_tasks_for_run(run_id)
            terminal = all(str(task.status) in (TaskStatus.SUCCEEDED.value, TaskStatus.FAILED.value,
                                                  TaskStatus.CANCELLED.value, TaskStatus.WAITING_FOR_REVIEW.value)
                           for task in all_tasks)
            return {"executed_count": 0, "completed": terminal,
                    "tasks_summary": {task.task_id: str(task.status) for task in all_tasks}}

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        pending: dict[concurrent.futures.Future, tuple[Task, str, float]] = {}
        for task, agent_id, worker in tasks_to_run:
            future = executor.submit(worker, task)
            pending[future] = (task, agent_id, time.monotonic())
        timed_out: list[str] = []
        try:
            while pending:
                now = time.monotonic()
                expired = [future for future, (task, _, started) in pending.items()
                           if now - started >= max(1, task.timeout_seconds)]
                for future in expired:
                    task, agent_id, _ = pending.pop(future)
                    future.cancel()
                    timed_out.append(task.task_id)
                    self.fail_task(task.task_id, agent_id, "TASK_TIMEOUT",
                                   expected_attempt=task.attempt)
                if not pending:
                    break
                nearest = min(max(0.01, max(1, task.timeout_seconds) - (now - started))
                              for task, _, started in pending.values())
                done, _ = concurrent.futures.wait(
                    pending, timeout=min(nearest, 0.1), return_when=concurrent.futures.FIRST_COMPLETED
                )
                for future in done:
                    task, agent_id, _ = pending.pop(future)
                    try:
                        ok, result_data, findings, error = future.result()
                        if ok:
                            self.complete_task(task.task_id, agent_id, result_data, findings,
                                               expected_attempt=task.attempt)
                        else:
                            self.fail_task(task.task_id, agent_id, error or "WORKER_FAILED",
                                           expected_attempt=task.attempt)
                    except Exception as exc:
                        self.fail_task(task.task_id, agent_id, f"WORKER_EXCEPTION:{type(exc).__name__}",
                                       expected_attempt=task.attempt)
        finally:
            # A timed-out Python thread cannot be forcibly killed. Its result is discarded, and
            # attempt-bound compare-and-set prevents any delayed callback from overwriting a retry.
            executor.shutdown(wait=False, cancel_futures=True)

        all_tasks = self.store.list_tasks_for_run(run_id)
        terminal = all(str(task.status) in (TaskStatus.SUCCEEDED.value, TaskStatus.FAILED.value,
                                              TaskStatus.CANCELLED.value, TaskStatus.WAITING_FOR_REVIEW.value)
                       for task in all_tasks)
        return {
            "executed_count": len(tasks_to_run),
            "timed_out": timed_out,
            "completed": terminal,
            "tasks_summary": {task.task_id: str(task.status) for task in all_tasks},
        }

    def save_checkpoint(self, run_id: str) -> Checkpoint:
        tasks = self.store.list_tasks_for_run(run_id)
        state = {task.task_id: task.to_dict() for task in tasks}
        run = self.store.get_run(run_id)
        memory_state = {
            "precedent_run_ids": run.precedent_run_ids if run else [],
            "context_summary": run.context_summary if run else "",
            "evidence_ids_by_task": {task.task_id: task.evidence_ids for task in tasks},
        }
        canonical = json.dumps({"tasks": state, "memory": memory_state}, sort_keys=True,
                               separators=(",", ":"), default=str)
        checkpoint = Checkpoint(
            checkpoint_id=generate_id("chk"), run_id=run_id, saved_at=now_iso(),
            tasks_state=state, memory_state=memory_state,
            hash=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        )
        self.store.save_checkpoint(checkpoint)
        self.store.record_event(AgentEvent(
            event_id=generate_id("evt"), run_id=run_id, task_id=None,
            event_type=EventType.CHECKPOINT_SAVED, agent_id="scheduler", role="scheduler",
            payload={"checkpoint_id": checkpoint.checkpoint_id, "task_count": len(tasks)},
            idempotency_key=f"{checkpoint.checkpoint_id}:CHECKPOINT_SAVED",
        ))
        return checkpoint

    def recover_run(self, run_id: str) -> Run | None:
        run = self.store.get_run(run_id)
        if not run:
            return None
        checkpoint = self.store.get_latest_checkpoint(run_id)
        recovered_ids = []
        for task in self.store.list_tasks_for_run(run_id):
            if str(task.status) in (TaskStatus.CLAIMED.value, TaskStatus.RUNNING.value):
                if self.store.transition_task(
                    task.task_id, expected_status=task.status,
                    expected_claimed_by=task.claimed_by or "", new_status=TaskStatus.READY,
                    claimed_by="", lease_expires_at="",
                ):
                    recovered_ids.append(task.task_id)
        self.store.record_event(AgentEvent(
            event_id=generate_id("evt"), run_id=run_id, task_id=None,
            event_type=EventType.RUN_RECOVERED, agent_id="scheduler", role="scheduler",
            payload={"restored_from_checkpoint": checkpoint.checkpoint_id if checkpoint else None,
                     "ready_task_ids": recovered_ids,
                     "recovery_scope": "read-only or idempotent task execution"},
            idempotency_key=f"{run_id}:RUN_RECOVERED:{generate_id('recovery')}",
        ))
        return self.store.get_run(run_id)
