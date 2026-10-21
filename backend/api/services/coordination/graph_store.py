"""Site-scoped coordination persistence.

Production calls use the existing FalkorDriftStore and never maintain a process-local mirror.
The in-memory implementation is an explicit test/demo backend and cannot be selected implicitly.
"""
from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Mapping
from typing import Any

from api.services.coordination.contracts import (
    AgentEvent,
    Checkpoint,
    CoordinationLabel,
    CoordinationRel,
    Finding,
    Run,
    Task,
    TaskStatus,
    now_iso,
)


class CoordinationStoreUnavailable(RuntimeError):
    """The configured graph store is unavailable; no local fallback was used."""


class InMemoryGraphStore:
    """Explicit, process-local backend for unit tests and clearly labelled demos only."""

    is_test_backend = True

    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, Any]] = {}
        self.labels: dict[str, str] = {}
        self.edges: dict[tuple[str, str, str], dict[str, Any]] = {}
        self._lock = threading.RLock()

    def upsert_node(self, label: str, node_id: str, props: Mapping[str, Any]) -> None:
        with self._lock:
            self.labels[node_id] = label
            self.nodes[node_id] = {**self.nodes.get(node_id, {}), **props, "id": node_id}

    def create_node_once(self, label: str, node_id: str, props: Mapping[str, Any]) -> dict[str, Any]:
        with self._lock:
            if node_id not in self.nodes:
                self.labels[node_id] = label
                self.nodes[node_id] = {**props, "id": node_id}
            return self.read_node(node_id) or {}

    def read_node(self, node_id: str) -> dict[str, Any] | None:
        with self._lock:
            if node_id not in self.nodes:
                return None
            return {"id": node_id, "label": self.labels.get(node_id, "Node"), "properties": dict(self.nodes[node_id])}

    def list_nodes(self, label: str, *, limit: int = 200) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {"id": node_id, **{k: v for k, v in props.items() if k != "id"}}
                for node_id, props in sorted(self.nodes.items())
                if self.labels.get(node_id) == label
            ][:limit]

    def update_node_properties(self, label: str, node_id: str, properties: Mapping[str, Any]) -> None:
        with self._lock:
            if self.labels.get(node_id) != label:
                raise KeyError(f"{label} node '{node_id}' does not exist")
            self.nodes[node_id].update(properties)

    def compare_and_set_node_properties(
        self, label: str, node_id: str, *, expected: Mapping[str, Any], properties: Mapping[str, Any]
    ) -> bool:
        with self._lock:
            current = self.read_node(node_id)
            if not current or current["label"] != label:
                return False
            if any(current["properties"].get(key) != value for key, value in expected.items()):
                return False
            self.nodes[node_id].update(properties)
            return True

    def link(self, source_id: str, rel: str, target_id: str, props: Mapping[str, Any] | None = None) -> None:
        with self._lock:
            if source_id not in self.nodes or target_id not in self.nodes:
                raise KeyError("both endpoint nodes must exist in this test graph")
            self.edges[(source_id, rel, target_id)] = dict(props or {})


class CoordinationGraphStore:
    """Typed coordination operations over FalkorDB or an explicit test/demo backend."""

    def __init__(
        self,
        drift_store: Any = None,
        site_id: str = "default_site",
        *,
        memory_backend: InMemoryGraphStore | None = None,
    ) -> None:
        if drift_store is not None and memory_backend is not None:
            raise ValueError("choose one graph backend")
        self.drift_store = drift_store
        self.memory_backend = memory_backend
        self.site_id = site_id

    @property
    def has_live_falkor(self) -> bool:
        if self.drift_store is None:
            return False
        try:
            return bool(self.drift_store.inspect_site(self.site_id).get("reachable"))
        except Exception:
            return False

    def _call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        if self.memory_backend is not None:
            fn = getattr(self.memory_backend, method)
            return fn(*args, **kwargs)
        if self.drift_store is None:
            raise CoordinationStoreUnavailable("FalkorDB is required; coordination has no implicit in-memory fallback")
        fn = getattr(self.drift_store, method)
        try:
            return fn(self.site_id, *args, **kwargs)
        except (ValueError, KeyError):
            raise
        except Exception as exc:
            raise CoordinationStoreUnavailable(f"FalkorDB coordination operation '{method}' failed") from exc

    @staticmethod
    def _props(value: Mapping[str, Any]) -> dict[str, Any]:
        return {key: item for key, item in value.items() if key not in {"id", "site_id"}}

    @staticmethod
    def _decode(value: Any, default: Any) -> Any:
        if not isinstance(value, str):
            return default if value is None else value
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return default

    def _node(self, node_id: str) -> dict[str, Any] | None:
        node = self._call("read_node", node_id)
        if not node:
            return None
        properties = node.get("properties", node)
        labels = node.get("labels", [])
        if not labels and node.get("label"):
            labels = [node["label"]]
        return {"id": node_id, "labels": list(labels), "properties": self._props(properties)}

    def _upsert(self, label: str, node_id: str, props: Mapping[str, Any]) -> None:
        if self.memory_backend is not None:
            self.memory_backend.upsert_node(label, node_id, props)
        else:
            self._call("upsert_node", label, node_id, props)

    def _create_once(self, label: str, node_id: str, props: Mapping[str, Any]) -> dict[str, Any]:
        if self.memory_backend is not None:
            return self.memory_backend.create_node_once(label, node_id, props)
        existing = self._call("create_node_once", label, node_id, props)
        return existing

    def _update(self, label: str, node_id: str, props: Mapping[str, Any]) -> None:
        if self.memory_backend is not None:
            self.memory_backend.update_node_properties(label, node_id, props)
        else:
            self._call("update_node_properties", label, node_id, props)

    def _link(self, source_label: str, source_id: str, rel: str, target_label: str, target_id: str) -> None:
        if self.memory_backend is not None:
            self.memory_backend.link(source_id, rel, target_id)
        else:
            self._call("link", source_label, source_id, rel, target_label, target_id)

    def _list(self, label: str, limit: int = 200) -> list[dict[str, Any]]:
        return self._call("list_nodes", label, limit=limit)

    def _cas(self, label: str, node_id: str, expected: Mapping[str, Any], props: Mapping[str, Any]) -> bool:
        return self._call(
            "compare_and_set_node_properties", label, node_id, expected=expected, properties=props
        )

    def create_run(self, run: Run) -> Run:
        props = {
            "campaign_goal": run.campaign_goal,
            "domain": run.domain,
            "status": run.status,
            "context_summary": run.context_summary,
            "created_at": run.created_at,
            "updated_at": run.updated_at,
            "precedent_run_ids": json.dumps(run.precedent_run_ids),
            "metadata": json.dumps(run.metadata, sort_keys=True),
        }
        self._upsert(CoordinationLabel.RUN.value, run.run_id, props)
        if self.memory_backend is not None:
            self.memory_backend.nodes[run.run_id]["site_id"] = self.site_id
        return run

    def get_run(self, run_id: str) -> Run | None:
        node = self._node(run_id)
        if not node or CoordinationLabel.RUN.value not in node["labels"]:
            return None
        props = node["properties"]
        tasks = self.list_tasks_for_run(run_id)
        return Run(
            run_id=run_id,
            site_id=self.site_id,
            campaign_goal=props.get("campaign_goal", ""),
            domain=props.get("domain", "general"),
            status=props.get("status", "IN_PROGRESS"),
            task_ids=[task.task_id for task in tasks],
            context_summary=props.get("context_summary", ""),
            precedent_run_ids=self._decode(props.get("precedent_run_ids"), []),
            metadata=self._decode(props.get("metadata"), {}),
            created_at=props.get("created_at", ""),
            updated_at=props.get("updated_at", ""),
        )

    def read_node(self, node_id: str) -> dict[str, Any] | None:
        """Read an exact node from this site's graph for evidence workers."""
        return self._node(node_id)

    def update_run_status(self, run_id: str, status: str) -> None:
        self._update(CoordinationLabel.RUN.value, run_id, {"status": status, "updated_at": now_iso()})

    def find_past_campaigns(self, domain: str, limit: int = 5) -> list[Run]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        rows = self._list(CoordinationLabel.RUN.value, 1000)
        task_ids: dict[str, list[str]] = {}
        for task in self._list(CoordinationLabel.TASK.value, 1000):
            task_ids.setdefault(str(task.get("run_id", "")), []).append(str(task.get("task_id", task["id"])))
        runs = [
            Run(
                run_id=str(row["id"]), site_id=self.site_id,
                campaign_goal=row.get("campaign_goal", ""), domain=row.get("domain", "general"),
                status=row.get("status", "IN_PROGRESS"), task_ids=task_ids.get(str(row["id"]), []),
                context_summary=row.get("context_summary", ""),
                precedent_run_ids=self._decode(row.get("precedent_run_ids"), []),
                metadata=self._decode(row.get("metadata"), {}),
                created_at=row.get("created_at", ""), updated_at=row.get("updated_at", ""),
            )
            for row in rows if domain == "all" or row.get("domain") == domain
        ]
        return sorted(runs, key=lambda run: run.created_at, reverse=True)[:limit]

    def create_task(self, task: Task) -> Task:
        if not self.get_run(task.run_id):
            raise KeyError(f"Run '{task.run_id}' does not exist in this site graph")
        props = {
            "task_id": task.task_id,
            "run_id": task.run_id,
            "domain": task.domain,
            "capability_id": task.capability_id,
            "goal": task.goal,
            "depends_on": json.dumps(task.depends_on),
            "assigned_role": str(task.assigned_role),
            "status": str(task.status),
            "attempt": task.attempt,
            "max_attempts": task.max_attempts,
            "requires_human_review": bool(task.requires_human_review),
            "checkpoint_id": task.checkpoint_id or "",
            "evidence_ids": json.dumps(task.evidence_ids),
            "result_id": task.result_id or "",
            "result_data": json.dumps(task.result_data, sort_keys=True) if task.result_data is not None else "{}",
            "error": task.error or "",
            "claimed_by": task.claimed_by or "",
            "lease_expires_at": task.lease_expires_at or "",
            "next_attempt_at": task.next_attempt_at or "",
            "timeout_seconds": task.timeout_seconds,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
        }
        self._upsert(CoordinationLabel.TASK.value, task.task_id, props)
        self._link(CoordinationLabel.RUN.value, task.run_id, CoordinationRel.HAS_TASK.value,
                   CoordinationLabel.TASK.value, task.task_id)
        self._ensure_agent(str(task.assigned_role))
        self._link(CoordinationLabel.TASK.value, task.task_id, CoordinationRel.ASSIGNED_TO.value,
                   "Agent", self._agent_id(str(task.assigned_role)))
        return task

    def link_task_dependencies(self, run_id: str) -> None:
        tasks = self.list_tasks_for_run(run_id)
        by_id = {task.task_id: task for task in tasks}
        for task in tasks:
            for dependency_id in task.depends_on:
                prerequisite = by_id.get(dependency_id)
                if not prerequisite:
                    raise ValueError(f"task dependency '{dependency_id}' must belong to the same run")
                self._link(CoordinationLabel.TASK.value, task.task_id, CoordinationRel.DEPENDS_ON.value,
                           CoordinationLabel.TASK.value, dependency_id)

    @staticmethod
    def _agent_id(agent_id: str) -> str:
        digest = hashlib.sha256(agent_id.encode("utf-8")).hexdigest()[:24]
        return f"agent_{digest}"

    def _ensure_agent(self, agent_id: str) -> str:
        node_id = self._agent_id(agent_id)
        self._upsert("Agent", node_id, {"name": agent_id, "role": agent_id, "updated_at": now_iso()})
        return node_id

    def get_task(self, task_id: str) -> Task | None:
        node = self._node(task_id)
        if not node or CoordinationLabel.TASK.value not in node["labels"]:
            return None
        props = node["properties"]
        data = dict(props)
        for field_name, fallback in (("depends_on", []), ("evidence_ids", []), ("result_data", {})):
            data[field_name] = self._decode(data.get(field_name), fallback)
        for field_name in ("checkpoint_id", "result_id", "error", "claimed_by", "lease_expires_at", "next_attempt_at"):
            if not data.get(field_name):
                data[field_name] = None
        return Task.from_dict({**data, "task_id": props.get("task_id", task_id)})

    def list_tasks_for_run(self, run_id: str) -> list[Task]:
        rows = self._list(CoordinationLabel.TASK.value, 1000)
        tasks = [self.get_task(str(row["id"])) for row in rows if row.get("run_id") == run_id]
        return sorted((task for task in tasks if task), key=lambda task: task.created_at)

    def update_task_status(
        self,
        task_id: str,
        status: TaskStatus | str,
        *,
        claimed_by: str | None = None,
        lease_expires_at: str | None = None,
        attempt: int | None = None,
        next_attempt_at: str | None = None,
        result_data: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        props: dict[str, Any] = {"status": str(status), "updated_at": now_iso()}
        if claimed_by is not None:
            props["claimed_by"] = claimed_by
            self._ensure_agent(claimed_by)
            self._link(CoordinationLabel.TASK.value, task_id, CoordinationRel.CLAIMED_BY.value,
                       "Agent", self._agent_id(claimed_by))
        if lease_expires_at is not None:
            props["lease_expires_at"] = lease_expires_at
        if attempt is not None:
            props["attempt"] = attempt
        if next_attempt_at is not None:
            props["next_attempt_at"] = next_attempt_at
        if result_data is not None:
            props["result_data"] = json.dumps(result_data, sort_keys=True)
        if error is not None:
            props["error"] = error
        self._update(CoordinationLabel.TASK.value, task_id, props)

    def transition_task(
        self,
        task_id: str,
        *,
        expected_status: TaskStatus | str,
        new_status: TaskStatus | str,
        expected_claimed_by: str | None = None,
        expected_attempt: int | None = None,
        expected_lease_expires_at: str | None = None,
        claimed_by: str | None = None,
        lease_expires_at: str | None = None,
        next_attempt_at: str | None = None,
        result_data: dict[str, Any] | None = None,
        error: str | None = None,
        attempt: int | None = None,
    ) -> bool:
        expected: dict[str, Any] = {"status": str(expected_status)}
        if expected_claimed_by is not None:
            expected["claimed_by"] = expected_claimed_by
        if expected_attempt is not None:
            expected["attempt"] = expected_attempt
        if expected_lease_expires_at is not None:
            expected["lease_expires_at"] = expected_lease_expires_at
        props: dict[str, Any] = {"status": str(new_status), "updated_at": now_iso()}
        if claimed_by is not None:
            props["claimed_by"] = claimed_by
        if lease_expires_at is not None:
            props["lease_expires_at"] = lease_expires_at
        if next_attempt_at is not None:
            props["next_attempt_at"] = next_attempt_at
        if result_data is not None:
            props["result_data"] = json.dumps(result_data, sort_keys=True)
        if error is not None:
            props["error"] = error
        if attempt is not None:
            props["attempt"] = attempt
        changed = self._cas(CoordinationLabel.TASK.value, task_id, expected, props)
        if changed and claimed_by:
            self._ensure_agent(claimed_by)
            self._link(CoordinationLabel.TASK.value, task_id, CoordinationRel.CLAIMED_BY.value,
                       "Agent", self._agent_id(claimed_by))
        if changed and new_status == TaskStatus.SUCCEEDED:
            task = self.get_task(task_id)
            if task:
                completed_by = expected_claimed_by or claimed_by
                if completed_by:
                    self._ensure_agent(completed_by)
                    self._link(CoordinationLabel.TASK.value, task_id, CoordinationRel.COMPLETED_BY.value,
                               "Agent", self._agent_id(completed_by))
        return changed

    def claim_task(self, task_id: str, agent_id: str, lease_expires_at: str) -> bool:
        task = self.get_task(task_id)
        if not task:
            return False
        self._ensure_agent(agent_id)
        changed = self._cas(
            CoordinationLabel.TASK.value,
            task_id,
            {"status": TaskStatus.READY.value, "attempt": task.attempt},
            {"status": TaskStatus.CLAIMED.value, "claimed_by": agent_id,
             "lease_expires_at": lease_expires_at, "attempt": task.attempt + 1,
             "updated_at": now_iso()},
        )
        if changed:
            self._link(CoordinationLabel.TASK.value, task_id, CoordinationRel.CLAIMED_BY.value,
                       "Agent", self._agent_id(agent_id))
        return changed

    def recover_expired_lease(self, task: Task) -> bool:
        return self._cas(
            CoordinationLabel.TASK.value,
            task.task_id,
            {"status": str(task.status), "attempt": task.attempt,
             "lease_expires_at": task.lease_expires_at or ""},
            {"status": TaskStatus.READY.value, "claimed_by": "", "lease_expires_at": "",
             "updated_at": now_iso()},
        )

    def record_event(self, event: AgentEvent) -> None:
        event_id = "evt_" + hashlib.sha256(event.idempotency_key.encode("utf-8")).hexdigest()[:32]
        props = {
            "run_id": event.run_id,
            "task_id": event.task_id or "",
            "event_type": str(event.event_type),
            "agent_id": event.agent_id,
            "role": str(event.role),
            "timestamp": event.timestamp,
            "idempotency_key": event.idempotency_key,
            "payload": json.dumps(event.payload, sort_keys=True),
        }
        node = self._create_once(CoordinationLabel.AGENT_EVENT.value, event_id, props)
        actual = node.get("properties", node)
        for key, value in props.items():
            if actual.get(key) != value:
                raise ValueError("event idempotency key was reused with a different event payload")
        if event.task_id:
            self._link(CoordinationLabel.TASK.value, event.task_id, CoordinationRel.HAS_EVENT.value,
                       CoordinationLabel.AGENT_EVENT.value, event_id)
        self._link(CoordinationLabel.RUN.value, event.run_id, CoordinationRel.HAS_EVENT.value,
                   CoordinationLabel.AGENT_EVENT.value, event_id)

    def list_events_for_run(self, run_id: str) -> list[AgentEvent]:
        rows = self._list(CoordinationLabel.AGENT_EVENT.value, 1000)
        events = []
        for row in rows:
            if row.get("run_id") != run_id:
                continue
            events.append(AgentEvent(
                event_id=str(row["id"]), run_id=run_id, task_id=row.get("task_id") or None,
                event_type=row.get("event_type", "UNKNOWN"), agent_id=row.get("agent_id", "unknown"),
                role=row.get("role", "unknown"), payload=self._decode(row.get("payload"), {}),
                timestamp=row.get("timestamp", ""), idempotency_key=row.get("idempotency_key", ""),
            ))
        return sorted(events, key=lambda event: event.timestamp)

    def record_finding(self, finding: Finding) -> None:
        props = {
            "task_id": finding.task_id,
            "claim": finding.claim,
            "why": finding.why,
            "provenance_tag": str(finding.provenance_tag),
            "cited_ids": json.dumps(finding.cited_ids),
            "confidence": finding.confidence,
            "origin_family_id": finding.origin_family_id or "",
            "canonical_source_id": finding.canonical_source_id or "",
            "verification_status": finding.verification_status,
            "timestamp": finding.timestamp,
        }
        self._upsert(CoordinationLabel.FINDING.value, finding.finding_id, props)
        self._link(CoordinationLabel.TASK.value, finding.task_id, CoordinationRel.VERIFIED_BY.value,
                   CoordinationLabel.FINDING.value, finding.finding_id)

    def save_checkpoint(self, checkpoint: Checkpoint) -> None:
        props = {
            "run_id": checkpoint.run_id,
            "saved_at": checkpoint.saved_at,
            "hash": checkpoint.hash,
            "tasks_state": json.dumps(checkpoint.tasks_state, sort_keys=True),
            "memory_state": json.dumps(checkpoint.memory_state, sort_keys=True),
        }
        self._upsert(CoordinationLabel.CHECKPOINT.value, checkpoint.checkpoint_id, props)
        self._link(CoordinationLabel.RUN.value, checkpoint.run_id, CoordinationRel.HAS_CHECKPOINT.value,
                   CoordinationLabel.CHECKPOINT.value, checkpoint.checkpoint_id)

    def get_latest_checkpoint(self, run_id: str) -> Checkpoint | None:
        rows = self._list(CoordinationLabel.CHECKPOINT.value, 1000)
        matches = [row for row in rows if row.get("run_id") == run_id]
        if not matches:
            return None
        row = max(matches, key=lambda item: item.get("saved_at", ""))
        return Checkpoint(
            checkpoint_id=str(row["id"]), run_id=run_id, saved_at=row.get("saved_at", ""),
            tasks_state=self._decode(row.get("tasks_state"), {}),
            memory_state=self._decode(row.get("memory_state"), {}), hash=row.get("hash", ""),
        )

