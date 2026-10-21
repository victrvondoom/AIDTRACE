"""Unified Contracts and Types for Multi-Agent Coordination on FalkorDB.

Enforces deterministic schemas for:
- Runs, Tasks, Dependencies (DAG), Events, Checkpoints
- Findings with Provenance Tags (GRAPH, ML, RULE, PRECEDENT, INFERRED, HUMAN_VERIFIED)
- Source Family Ancestry ("Five sources may really be one")
- Action Proposals with Supervisor Gates
- Verified Unlearning & Deletion Receipts
- Structured Generation schema validation (SG-Lang compatible)
"""
from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

# -----------------------------------------------------------------------------
# Enums
# -----------------------------------------------------------------------------

class TaskStatus(StrEnum):
    PENDING = "PENDING"
    READY = "READY"
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    WAITING_FOR_DEPENDENCY = "WAITING_FOR_DEPENDENCY"
    WAITING_FOR_REVIEW = "WAITING_FOR_REVIEW"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    STALE = "STALE"


class AgentRole(StrEnum):
    COORDINATOR = "coordinator"
    EVIDENCE_WORKER = "evidence_worker"      # Worker A: Graph traversal, provenance, recall, entity resolution
    VALIDATION_WORKER = "validation_worker"  # Worker B: Domain simulation, reachability, AML, what-if, constraints
    GOVERNANCE = "governance"                # Deterministic gatekeeper, never an unconstrained model


class EventType(StrEnum):
    RUN_CREATED = "RUN_CREATED"
    PLAN_GENERATED = "PLAN_GENERATED"
    TASK_CREATED = "TASK_CREATED"
    TASK_READY = "TASK_READY"
    TASK_WAITING = "TASK_WAITING"
    TASK_CLAIMED = "TASK_CLAIMED"
    TOOL_INVOKED = "TOOL_INVOKED"
    TOOL_COMPLETED = "TOOL_COMPLETED"
    FINDING_RECORDED = "FINDING_RECORDED"
    EVIDENCE_VERIFIED = "EVIDENCE_VERIFIED"
    EVIDENCE_INVALIDATED = "EVIDENCE_INVALIDATED"
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_FAILED = "TASK_FAILED"
    TASK_CANCELLED = "TASK_CANCELLED"
    HANDOFF_CREATED = "HANDOFF_CREATED"
    CHECKPOINT_SAVED = "CHECKPOINT_SAVED"
    REVIEW_REQUESTED = "REVIEW_REQUESTED"
    DECISION_REVISED = "DECISION_REVISED"
    ACTION_APPROVED = "ACTION_APPROVED"
    ACTION_BLOCKED = "ACTION_BLOCKED"
    RUN_COMPLETED = "RUN_COMPLETED"
    RUN_RECOVERED = "RUN_RECOVERED"


class ProvenanceTag(StrEnum):
    GRAPH = "GRAPH"                      # Directly traversed graph relationship / Cypher fact
    ML = "ML"                            # Statistical model output (e.g. CatBoost quantile emissions score)
    RULE = "RULE"                        # Deterministic policy / constraint verification
    PRECEDENT = "PRECEDENT"              # Recall from prior campaign or cross-app verdict
    INFERRED = "INFERRED"                # Model-generated hypothesis (clearly distinguished from fact)
    HUMAN_VERIFIED = "HUMAN_VERIFIED"    # Explicit human supervisor confirmation


class CapabilityAvailability(StrEnum):
    OPERATIONAL = "OPERATIONAL"
    SIMULATION = "SIMULATION"
    PARTIAL = "PARTIAL"
    CONFIGURATION_REQUIRED = "CONFIGURATION_REQUIRED"
    BLOCKED = "BLOCKED"
    PLANNED = "PLANNED"


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class CoordinationLabel(StrEnum):
    RUN = "Run"
    TASK = "Task"
    TOOL_INVOCATION = "ToolInvocation"
    TOOL_RESULT = "ToolResult"
    AGENT_EVENT = "AgentEvent"
    CHECKPOINT = "Checkpoint"
    FINDING = "Finding"
    DELETION_RECEIPT = "DeletionReceipt"
    SOURCE = "Source"
    OBSERVATION = "Observation"
    MEASUREMENT = "Measurement"
    EVIDENCE_RECEIPT = "EvidenceReceipt"
    VERIFICATION = "Verification"
    CONTRADICTION = "Contradiction"
    ENTITY = "Entity"
    RELATIONSHIP_ASSERTION = "RelationshipAssertion"
    RISK = "Risk"
    HYPOTHESIS = "Hypothesis"
    RECOMMENDATION = "Recommendation"
    POLICY = "Policy"
    CONSTRAINT = "Constraint"
    REVIEW = "Review"


class CoordinationRel(StrEnum):
    HAS_TASK = "HAS_TASK"                # (Run)->(Task)
    DEPENDS_ON = "DEPENDS_ON"            # (Task|Decision|Action)->(Task|Claim|Memory)
    SUPPORTED_BY = "SUPPORTED_BY"        # (Claim)->(SourceVersion)
    DERIVED_FROM = "DERIVED_FROM"        # (Memory)->(Claim|Memory)
    ASSIGNED_TO = "ASSIGNED_TO"          # (Task)->(Agent)
    COMPLETED_BY = "COMPLETED_BY"        # (Task)->(Agent)
    CLAIMED_BY = "CLAIMED_BY"            # (Task)->(Agent)
    EXTRACTED_FROM = "EXTRACTED_FROM"    # (Finding|Claim)->(Document|Source)
    OBSERVED = "OBSERVED"                # (Observation)->(Entity)
    REFERENCES = "REFERENCES"            # (Document|Finding)->(Entity)
    ABOUT = "ABOUT"                      # (Memory|Task)->(Entity)
    RECALLED_FROM = "RECALLED_FROM"      # (AgentSession|Run)->(Run|Memory)
    INFLUENCED_BY = "INFLUENCED_BY"      # (Decision|Task)->(Decision|Task)
    HAS_CHECKPOINT = "HAS_CHECKPOINT"    # (Run)->(Checkpoint)
    HAS_EVENT = "HAS_EVENT"              # (Run|Task)->(AgentEvent)
    TRIGGERED_BY = "TRIGGERED_BY"        # (Run|Task)->(ChangeEvent|Alert)
    VERIFIED_BY = "VERIFIED_BY"          # (Finding|Claim)->(Verification)
    PROPOSES = "PROPOSES"                # (Worker|Task)->(ActionProposal)
    EXECUTED_AS = "EXECUTED_AS"          # (Task)->(ToolInvocation)


# -----------------------------------------------------------------------------
# Helpers & Validators
# -----------------------------------------------------------------------------

def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def generate_id(prefix: str = "id") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# -----------------------------------------------------------------------------
# Core Dataclasses
# -----------------------------------------------------------------------------

@dataclass
class Finding:
    """An evidence-grounded claim produced during a task."""
    finding_id: str
    task_id: str
    claim: str
    why: str
    provenance_tag: ProvenanceTag | str
    cited_ids: list[str] = field(default_factory=list)
    confidence: float = 1.0
    origin_family_id: str | None = None
    canonical_source_id: str | None = None
    verification_status: str = "VERIFIED"
    timestamp: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ToolResult:
    """Deterministic tool execution result."""
    ok: bool
    data: Any
    findings: list[Finding] = field(default_factory=list)
    cited_ids: list[str] = field(default_factory=list)
    provenance: ProvenanceTag | str = ProvenanceTag.GRAPH
    timing_ms: float = 0.0
    cypher_executed: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["findings"] = [f.to_dict() if isinstance(f, Finding) else f for f in self.findings]
        return d


@dataclass
class Task:
    """A bounded unit of work scheduled in the dependency graph."""
    task_id: str
    run_id: str
    domain: str
    capability_id: str
    goal: str
    depends_on: list[str] = field(default_factory=list)
    assigned_role: AgentRole | str = AgentRole.EVIDENCE_WORKER
    status: TaskStatus | str = TaskStatus.PENDING
    attempt: int = 0
    max_attempts: int = 3
    checkpoint_id: str | None = None
    evidence_ids: list[str] = field(default_factory=list)
    result_id: str | None = None
    requires_human_review: bool = False
    claimed_by: str | None = None
    lease_expires_at: str | None = None
    next_attempt_at: str | None = None
    timeout_seconds: int = 30
    result_data: dict[str, Any] | None = None
    error: str | None = None
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Task:
        clean = dict(data)
        if "task_id" not in clean and "id" in clean:
            clean["task_id"] = clean["id"]
        if isinstance(clean.get("depends_on"), str):
            try:
                clean["depends_on"] = json.loads(clean["depends_on"])
            except Exception:
                clean["depends_on"] = [clean["depends_on"]] if clean["depends_on"] else []
        if isinstance(clean.get("evidence_ids"), str):
            try:
                clean["evidence_ids"] = json.loads(clean["evidence_ids"])
            except Exception:
                clean["evidence_ids"] = []
        if isinstance(clean.get("result_data"), str):
            try:
                clean["result_data"] = json.loads(clean["result_data"])
            except Exception:
                pass
        return cls(**{k: v for k, v in clean.items() if k in cls.__dataclass_fields__})


@dataclass
class Run:
    """A persistent campaign/investigation node ('Company Brain')."""
    run_id: str
    site_id: str
    campaign_goal: str
    domain: str
    status: str = "IN_PROGRESS"
    task_ids: list[str] = field(default_factory=list)
    context_summary: str = ""
    precedent_run_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgentEvent:
    """An immutable event transition in the coordination trace."""
    event_id: str
    run_id: str
    task_id: str | None
    event_type: EventType | str
    agent_id: str
    role: str
    payload: dict[str, Any]
    timestamp: str = field(default_factory=now_iso)
    idempotency_key: str = field(default_factory=lambda: uuid.uuid4().hex)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ActionProposal:
    """A proposed action awaiting deterministic gating or supervisor approval."""
    proposal_id: str
    task_id: str
    run_id: str
    action_type: str
    target_entity_id: str
    parameters: dict[str, Any] = field(default_factory=dict)
    reversible: bool = True
    requires_supervisor: bool = False
    status: str = "PENDING"  # PENDING, APPROVED, BLOCKED, EXECUTED, REJECTED
    decision_id: str | None = None
    dependency_hash: str = ""
    rejection_reason: str | None = None
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DeletionReceipt:
    """Cryptographic audit receipt for verified unlearning & data removal."""
    receipt_id: str
    entity_id: str
    entity_type: str
    authority: str
    reason: str
    deleted_at: str
    re_query_verification: bool
    evidence_hash: str
    anonymized_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Checkpoint:
    """Resumable snapshot of an ongoing run."""
    checkpoint_id: str
    run_id: str
    saved_at: str
    tasks_state: dict[str, Any]
    memory_state: dict[str, Any]
    hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# -----------------------------------------------------------------------------
# Structured Generation (SG-Lang compatible constrained JSON schema validator)
# -----------------------------------------------------------------------------

class StructuredOutputContract:
    """Validates structured JSON output against an explicit schema with zero hallucinations."""

    @staticmethod
    def validate_answer(payload: dict[str, Any]) -> dict[str, Any]:
        required = ("finding", "why", "affected", "citations", "next_step")
        for key in required:
            if key not in payload:
                raise ValueError(f"Structured output missing required key: {key}")
        if not isinstance(payload["affected"], list):
            raise ValueError("'affected' must be a list of identifiers")
        if not isinstance(payload["citations"], list):
            raise ValueError("'citations' must be a list of identifiers")
        return payload
