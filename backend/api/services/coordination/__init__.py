"""Unified FalkorDB Multi-Agent Coordination Package."""
from __future__ import annotations

from api.services.coordination.capability_registry import CAPABILITY_REGISTRY, CapabilityDefinition
from api.services.coordination.contracts import (
    ActionProposal,
    AgentEvent,
    AgentRole,
    CapabilityAvailability,
    Checkpoint,
    CoordinationLabel,
    CoordinationRel,
    DeletionReceipt,
    EventType,
    Finding,
    ProvenanceTag,
    RiskLevel,
    Run,
    StructuredOutputContract,
    Task,
    TaskStatus,
    ToolResult,
)
from api.services.coordination.coordinator import CoordinatorAgent
from api.services.coordination.evidence_extensions import (
    VerifiedUnlearningEngine,
    evaluate_source_independence,
)
from api.services.coordination.graph_store import CoordinationGraphStore, CoordinationStoreUnavailable
from api.services.coordination.scheduler import DependencyScheduler
from api.services.coordination.workers import (
    DeterministicGovernance,
    EvidenceWorker,
    ValidationWorker,
)

__all__ = [
    "ActionProposal",
    "AgentEvent",
    "AgentRole",
    "CAPABILITY_REGISTRY",
    "CapabilityAvailability",
    "CapabilityDefinition",
    "Checkpoint",
    "CoordinationGraphStore",
    "CoordinationStoreUnavailable",
    "CoordinationLabel",
    "CoordinationRel",
    "CoordinatorAgent",
    "DeletionReceipt",
    "DependencyScheduler",
    "DeterministicGovernance",
    "EventType",
    "EvidenceWorker",
    "Finding",
    "ProvenanceTag",
    "RiskLevel",
    "Run",
    "StructuredOutputContract",
    "Task",
    "TaskStatus",
    "ToolResult",
    "ValidationWorker",
    "VerifiedUnlearningEngine",
    "evaluate_source_independence",
]
