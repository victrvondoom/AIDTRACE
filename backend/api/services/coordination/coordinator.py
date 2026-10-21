"""Graph-backed Coordinator for bounded, evidence-aware investigation runs."""
from __future__ import annotations

from typing import Any

from api.services.coordination.contracts import (
    AgentEvent,
    AgentRole,
    EventType,
    Run,
    Task,
    TaskStatus,
    generate_id,
)
from api.services.coordination.graph_store import CoordinationGraphStore
from api.services.coordination.scheduler import DependencyScheduler
from api.services.coordination.workers import DeterministicGovernance, EvidenceWorker, ValidationWorker


class CoordinatorAgent:
    """Plan graph lookups and capability checks; domain adapters remain separately registered."""

    def __init__(self, store: CoordinationGraphStore) -> None:
        self.store = store
        self.scheduler = DependencyScheduler(store)
        self.worker_a = EvidenceWorker(store)
        self.worker_b = ValidationWorker(store)
        self.governance = DeterministicGovernance(store)

    def plan_investigation(
        self,
        goal: str,
        domain: str = "general",
        site_id: str | None = None,
        context_ids: list[str] | None = None,
    ) -> Run:
        """Persist a generic two-worker plan without guessing what a domain should find."""
        if not goal.strip():
            raise ValueError("goal must not be empty")
        if site_id is not None and site_id != self.store.site_id:
            raise ValueError("run site must match the authenticated graph scope")
        evidence_ids = list(dict.fromkeys(context_ids or []))
        if len(evidence_ids) > 100:
            raise ValueError("at most 100 evidence identifiers are allowed")

        past_runs = self.store.find_past_campaigns(domain, limit=3)
        run_id = generate_id("run")
        run = Run(
            run_id=run_id,
            site_id=self.store.site_id,
            campaign_goal=goal.strip(),
            domain=domain.strip() or "general",
            status="IN_PROGRESS",
            precedent_run_ids=[item.run_id for item in past_runs],
            context_summary=(f"Recalled {len(past_runs)} prior coordination run(s). "
                             "Precedent records are context only and are not current evidence."),
        )
        self.store.create_run(run)
        self._record_event(run_id, EventType.RUN_CREATED, "coordinator", AgentRole.COORDINATOR,
                           {"goal": run.campaign_goal, "domain": run.domain,
                            "precedents_recalled": run.precedent_run_ids}, f"{run_id}:RUN_CREATED")

        tasks = self._decompose_goal(run_id, run.domain, evidence_ids)
        for task in tasks:
            self.store.create_task(task)
            self._record_event(run_id, EventType.TASK_CREATED, "coordinator", AgentRole.COORDINATOR,
                               {"task_id": task.task_id, "capability_id": task.capability_id,
                                "depends_on": task.depends_on}, f"{run_id}:TASK_CREATED:{task.task_id}", task.task_id)
        self.store.link_task_dependencies(run_id)
        run.task_ids = [task.task_id for task in tasks]
        self._record_event(run_id, EventType.PLAN_GENERATED, "coordinator", AgentRole.COORDINATOR,
                           {"task_count": len(tasks), "task_ids": run.task_ids}, f"{run_id}:PLAN_GENERATED")
        return run

    def _record_event(
        self,
        run_id: str,
        event_type: EventType,
        agent_id: str,
        role: AgentRole | str,
        payload: dict[str, Any],
        key: str,
        task_id: str | None = None,
    ) -> None:
        self.store.record_event(AgentEvent(
            event_id=generate_id("evt"), run_id=run_id, task_id=task_id,
            event_type=event_type, agent_id=agent_id, role=role, payload=payload,
            idempotency_key=key,
        ))

    @staticmethod
    def _decompose_goal(run_id: str, domain: str, evidence_ids: list[str]) -> list[Task]:
        evidence_task_id = generate_id("task_evidence")
        readiness_task_id = generate_id("task_capability")
        summary_task_id = generate_id("task_summary")
        return [
            Task(
                task_id=evidence_task_id, run_id=run_id, domain=domain,
                capability_id="core.graph_evidence_lookup",
                goal="Check whether the exact supplied evidence identifiers exist in this site's graph.",
                assigned_role=AgentRole.EVIDENCE_WORKER, evidence_ids=evidence_ids,
            ),
            Task(
                task_id=readiness_task_id, run_id=run_id, domain=domain,
                capability_id="core.capability_readiness",
                goal="Report registered domain capability availability and prerequisites.",
                assigned_role=AgentRole.VALIDATION_WORKER,
            ),
            Task(
                task_id=summary_task_id, run_id=run_id, domain=domain,
                capability_id="core.deterministic_summary",
                goal="Combine graph lookup and capability readiness without adding domain conclusions.",
                depends_on=[evidence_task_id, readiness_task_id],
                assigned_role=AgentRole.VALIDATION_WORKER,
            ),
        ]

    def execute_investigation(self, run_id: str) -> dict[str, Any]:
        if not self.store.get_run(run_id):
            raise KeyError(f"Run '{run_id}' not found in this site graph")
        workers = {
            AgentRole.EVIDENCE_WORKER.value: self.worker_a.execute_task,
            AgentRole.VALIDATION_WORKER.value: self.worker_b.execute_task,
        }
        cycle = 0
        result: dict[str, Any] = {}
        for cycle in range(1, 11):
            result = self.scheduler.run_parallel_cycle(run_id, workers, max_workers=2)
            if result.get("completed") or result.get("executed_count", 0) == 0:
                break

        checkpoint = self.scheduler.save_checkpoint(run_id)
        tasks = self.store.list_tasks_for_run(run_id)
        if any(task.status == TaskStatus.FAILED for task in tasks):
            status = "FAILED"
        elif any(task.status == TaskStatus.WAITING_FOR_REVIEW for task in tasks):
            status = "REVIEW_REQUIRED"
        elif all(task.status == TaskStatus.SUCCEEDED for task in tasks):
            summary = next((task.result_data or {} for task in tasks
                            if task.capability_id == "core.deterministic_summary"), {})
            status = "BLOCKED" if summary.get("outcome") in {
                "CAPABILITY_NOT_OPERATIONAL", "EVIDENCE_INCOMPLETE"
            } else "COMPLETED"
        elif all(str(task.status) in {TaskStatus.SUCCEEDED.value, TaskStatus.FAILED.value,
                                      TaskStatus.CANCELLED.value} for task in tasks):
            status = "CANCELLED" if any(task.status == TaskStatus.CANCELLED for task in tasks) else "COMPLETED"
        else:
            status = "IN_PROGRESS"

        self.store.update_run_status(run_id, status)
        self._record_event(run_id, EventType.RUN_COMPLETED, "coordinator", AgentRole.COORDINATOR,
                           {"status": status, "checkpoint_id": checkpoint.checkpoint_id},
                           f"{run_id}:RUN_COMPLETED:{checkpoint.checkpoint_id}")
        events = self.store.list_events_for_run(run_id)
        return {
            "run_id": run_id,
            "status": status,
            "cycle_count": cycle,
            "checkpoint_id": checkpoint.checkpoint_id,
            "tasks": [task.to_dict() for task in self.store.list_tasks_for_run(run_id)],
            "event_count": len(events),
            "events": [event.to_dict() for event in events],
            "findings_count": 0,
            "domain_analysis_performed": False,
        }
