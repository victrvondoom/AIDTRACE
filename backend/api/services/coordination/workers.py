"""Read-only evidence and capability workers plus deterministic review gating."""
from __future__ import annotations

from typing import Any

from api.services.coordination.capability_registry import CAPABILITY_REGISTRY, CapabilityRegistry
from api.services.coordination.contracts import (
    ActionProposal,
    AgentRole,
    Task,
)
from api.services.coordination.graph_store import CoordinationGraphStore


class EvidenceWorker:
    """Worker A checks supplied identifiers against the caller's graph, without inventing facts."""

    def __init__(self, store: CoordinationGraphStore, agent_id: str = "worker_evidence_a") -> None:
        self.store = store
        self.agent_id = agent_id
        self.role = AgentRole.EVIDENCE_WORKER

    def execute_task(self, task: Task, context: Any = None) -> tuple[bool, dict[str, Any], list, str | None]:
        found: list[dict[str, Any]] = []
        missing: list[str] = []
        for evidence_id in task.evidence_ids:
            node = self.store.read_node(evidence_id)
            if node:
                found.append({"id": evidence_id, "labels": node["labels"],
                              "status": node["properties"].get("status", "UNKNOWN")})
            else:
                missing.append(evidence_id)
        return True, {
            "evidence_status": "PRESENT" if found else "NO_EVIDENCE_FOUND",
            "found": found,
            "missing_ids": missing,
            "verified_citations": [item["id"] for item in found],
            "claim_scope": "graph node existence only; no domain conclusion was made",
        }, [], None


class ValidationWorker:
    """Worker B reports registry readiness and joins stored prerequisite results."""

    def __init__(
        self,
        store: CoordinationGraphStore,
        registry: CapabilityRegistry = CAPABILITY_REGISTRY,
        agent_id: str = "worker_validation_b",
    ) -> None:
        self.store = store
        self.registry = registry
        self.agent_id = agent_id
        self.role = AgentRole.VALIDATION_WORKER

    def execute_task(self, task: Task, context: Any = None) -> tuple[bool, dict[str, Any], list, str | None]:
        if task.capability_id == "core.capability_readiness":
            return True, self.registry.readiness(task.domain), [], None

        if task.capability_id == "core.deterministic_summary":
            by_id = {item.task_id: item for item in self.store.list_tasks_for_run(task.run_id)}
            dependencies = [by_id[task_id] for task_id in task.depends_on if task_id in by_id]
            evidence_result = next((item.result_data for item in dependencies
                                    if item.capability_id == "core.graph_evidence_lookup" and item.result_data), {})
            readiness = next((item.result_data for item in dependencies
                              if item.capability_id == "core.capability_readiness" and item.result_data), {})
            availability = readiness.get("availability", "PLANNED")
            missing = evidence_result.get("missing_ids", [])
            found = evidence_result.get("found", [])
            if availability != "OPERATIONAL":
                outcome = "CAPABILITY_NOT_OPERATIONAL"
            elif missing or not found:
                outcome = "EVIDENCE_INCOMPLETE"
            else:
                outcome = "READY_FOR_HUMAN_REVIEW"
            return True, {
                "outcome": outcome,
                "domain_execution_performed": False,
                "capability_availability": availability,
                "evidence_ids_found": [item["id"] for item in found],
                "evidence_ids_missing": missing,
                "next_step": "connect a tested domain adapter and review its exact evidence before proposing action",
            }, [], None

        return False, {}, [], f"No executor is registered for '{task.capability_id}'."


class DeterministicGovernance:
    """A proposal is never marked approved by this pre-review eligibility check."""

    def __init__(self, store: CoordinationGraphStore) -> None:
        self.store = store

    def evaluate_proposal(
        self,
        proposal: ActionProposal,
        evidence_fresh: bool = True,
    ) -> dict[str, Any]:
        if not evidence_fresh:
            proposal.status = "BLOCKED"
            proposal.rejection_reason = "Supporting evidence or decision has been superseded or invalidated."
            decision = "BLOCKED"
        elif proposal.requires_supervisor or not proposal.reversible:
            proposal.status = "WAITING_FOR_REVIEW"
            decision = "WAITING_FOR_REVIEW"
        else:
            proposal.status = "ELIGIBLE_FOR_REVIEW"
            decision = "ELIGIBLE_FOR_REVIEW"
        return {
            "decision": decision,
            "reason": proposal.rejection_reason or "Eligibility check only; no action was approved or executed.",
            "requires_supervisor": decision == "WAITING_FOR_REVIEW",
            "proposal_id": proposal.proposal_id,
            "executed": False,
        }
