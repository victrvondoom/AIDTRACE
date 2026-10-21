"""Evidence Drift Cascade — the typed graph contract.

Pure module: no database, no I/O. Everything the engine writes to FalkorDB is validated here first,
so a malformed id or an unknown status never reaches a Cypher statement.

Temporal model (one timestamp per question, never one timestamp for all of them):

    event_time        when the underlying real-world event happened (inspection, test, failure)
    source_created_at when the author created the source document
    observed_at       when Kairos ingested it (transaction time, start)
    valid_from        when the fact became true in the world (valid time, start)
    valid_to          when it stopped being true; VALID_TO_OPEN = still valid (Kairos sentinel)
    revoked_at        when Kairos *learned* it was no longer valid (transaction time, end);
                      NOT_REVOKED = never revoked
    generated_at      when a memory / decision / plan was produced
    source_version_id the exact SourceVersion a claim came from
    graph_revision    the dependency-closure hash an approval was bound to

Dependency direction: every dependency edge points from the dependent to what it depends on,
`(Decision)-[:DEPENDS_ON]->(Claim)`. Impact traversal walks those edges backwards.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

# Kairos convention (AGENTS.md): `valid_to` uses a far-future sentinel, never NULL.
VALID_TO_OPEN = "9999-12-31T00:00:00.000000+00:00"
NOT_REVOKED = VALID_TO_OPEN

# Kairos authority levels: 1 is the strongest (regulator / approved MoC), 5 the weakest.
AUTHORITY_MIN, AUTHORITY_MAX = 1, 5
# Kairos quarantine rule: an extraction below this confidence is held for a human.
QUARANTINE_CONFIDENCE = 0.7

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:\-_]{0,127}$")
_SITE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:\-/_]{0,199}$")


class Label(StrEnum):
    DOCUMENT = "Document"
    SOURCE_VERSION = "SourceVersion"
    CLAIM = "Claim"
    AGENT = "Agent"
    AGENT_SESSION = "AgentSession"
    MEMORY = "Memory"
    DECISION = "Decision"
    DECISION_REVISION = "DecisionRevision"
    PLAN = "Plan"
    ACTION = "ActionProposal"
    APPROVAL = "Approval"
    CHANGE = "ChangeEvent"
    AUDIT = "AuditEvent"
    ASSET = "Asset"


class Rel(StrEnum):
    VERSION_OF = "VERSION_OF"            # (SourceVersion)->(Document)
    SUPPORTED_BY = "SUPPORTED_BY"        # (Claim)->(SourceVersion)
    DERIVED_FROM = "DERIVED_FROM"        # (Memory)->(Claim|Decision|Memory)
    DEPENDS_ON = "DEPENDS_ON"            # (Decision|Plan|ActionProposal)->(Claim|Memory|Decision|Plan)
    SUPERSEDES = "SUPERSEDES"            # newer -> older (SourceVersion, Claim)
    CONTRADICTS = "CONTRADICTS"          # (Claim)->(Claim), lower trust contradicting stronger
    RECALLED_IN = "RECALLED_IN"          # (Memory)->(AgentSession)
    PRODUCED = "PRODUCED"                # (AgentSession)->(Memory|Decision|Plan|ActionProposal)
    HAS_SESSION = "HAS_SESSION"            # (Agent)->(AgentSession)
    APPROVED_BY = "APPROVED_BY"          # (ActionProposal)->(Approval)
    ON_REVISION = "ON_REVISION"          # (Approval)->(DecisionRevision), immutable review target
    HAS_REVISION = "HAS_REVISION"          # (Decision)->(DecisionRevision)
    PREVIOUS = "PREVIOUS"                  # (DecisionRevision)->(DecisionRevision)
    REQUIRES_APPROVAL = "REQUIRES_APPROVAL"  # (ActionProposal)->(Decision) whose change voids approval
    INVALIDATED_BY = "INVALIDATED_BY"    # (any)->(ChangeEvent)
    AFFECTS = "AFFECTS"                  # (Claim|Decision|ActionProposal)->(Asset)


# Edges the impact traversal follows (backwards). Everything else is metadata.
DEPENDENCY_RELS = (Rel.SUPPORTED_BY.value, Rel.DERIVED_FROM.value, Rel.DEPENDS_ON.value)
DERIVED_LABELS = (Label.MEMORY.value, Label.DECISION.value, Label.PLAN.value, Label.ACTION.value)


class EdgeKind(StrEnum):
    """Why a dependency exists. Only LOGICAL and POLICY propagate invalidation (algorithm C)."""
    LOGICAL = "logical"   # the conclusion is computed from the dependency
    POLICY = "policy"     # a rule/permit requires the dependency to hold
    CONTEXT = "context"   # background only: a change advises review, never invalidates


PROPAGATING_KINDS = (EdgeKind.LOGICAL.value, EdgeKind.POLICY.value)


class SourceStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    WITHDRAWN = "WITHDRAWN"
    QUARANTINED = "QUARANTINED"


class ClaimStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"      # replaced by a different value from stronger evidence
    WITHDRAWN = "WITHDRAWN"        # its source was withdrawn and nothing replaced it
    CONTESTED = "CONTESTED"        # weaker evidence disagrees; still authoritative, flagged
    QUARANTINED = "QUARANTINED"    # below the confidence gate; never authoritative


class DerivedStatus(StrEnum):
    """Status of Memory, Decision and Plan nodes."""
    VALID = "VALID"
    PROVISIONAL = "PROVISIONAL"
    STALE = "STALE"                # a material dependency changed; must not be relied on
    INVALIDATED = "INVALIDATED"    # re-evaluated and no longer holds
    REVIEW = "REVIEW"              # contested or context-only change; a human should look


class ActionStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    SUSPENDED = "SUSPENDED"
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"


class ApprovalStatus(StrEnum):
    VALID = "VALID"
    VOID = "VOID"


class ChangeKind(StrEnum):
    SUPERSEDE = "SUPERSEDE"        # a new version replaces an old one
    CORRECT = "CORRECT"            # same document, corrected version (same mechanics as SUPERSEDE)
    WITHDRAW = "WITHDRAW"          # a source is withdrawn with no replacement
    CONTRADICT = "CONTRADICT"      # an independent source disagrees with an existing claim


class MemoryKind(StrEnum):
    EPISODIC = "EPISODIC"          # what an agent saw or did in one episode
    SEMANTIC = "SEMANTIC"          # a general fact the agent holds, with its source
    PROCEDURAL = "PROCEDURAL"      # an approved way of doing something


class Verification(StrEnum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    QUARANTINED = "QUARANTINED"


class AgentFocusLevel(StrEnum):
    BROAD = "BROAD"
    TARGETED = "TARGETED"
    HYPERFOCUS = "HYPERFOCUS"


class InputModality(StrEnum):
    DOCUMENT = "DOCUMENT"
    TEXT = "TEXT"
    VOICE = "VOICE"
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"
    TELEMETRY = "TELEMETRY"


class ContractError(ValueError):
    """Input that violates the graph contract. Routers map it to HTTP 422."""


def build_agent_focus_plan(
    focus_level: AgentFocusLevel | str,
    requested_modalities: list[InputModality | str],
) -> dict[str, Any]:
    """Describe the synthetic investigation focus and the existing Kairos modality boundaries.

    Focus changes investigation emphasis and the operator-facing plan. It never reduces the
    dependency traversal or revision-bound action checks used for safety decisions.
    """
    try:
        level = AgentFocusLevel(focus_level)
        modalities = [InputModality(modality) for modality in requested_modalities]
    except ValueError as exc:
        raise ContractError("unknown focus level or input modality") from exc
    scopes = {
        AgentFocusLevel.BROAD: "case-wide evidence, agent handoffs, decisions, and action state",
        AgentFocusLevel.TARGETED: "changed source, linked claims, and dependent decision",
        AgentFocusLevel.HYPERFOCUS: "one changed source through its transitive decision-to-action path",
    }
    scenario_modalities = {InputModality.DOCUMENT.value, InputModality.TEXT.value}
    requested = sorted({modality.value for modality in modalities})
    modality_capabilities = [
        {
            "modality": InputModality.DOCUMENT.value,
            "status": "KAIROS_PIPELINE_NOT_CASE_LINKED",
            "entrypoint": "POST /documents/ingest",
            "detail": "Kairos document vault and extraction are available separately; this demo uses a synthetic source and does not ingest a file.",
        },
        {
            "modality": InputModality.TEXT.value,
            "status": "SYNTHETIC_FIXTURE_ONLY",
            "entrypoint": "ResolveAI Evidence Drift demo",
            "detail": "The scenario's source and claims are generated fixtures; no user text or transcript is attached.",
        },
        {
            "modality": InputModality.VOICE.value,
            "status": "KAIROS_PIPELINE_NOT_CASE_LINKED",
            "entrypoint": "POST /elicitation/{work_order_id}/voice",
            "detail": "Kairos has a separate work-order voice transcription flow; its transcript is not attached to this ResolveAI case.",
        },
        {
            "modality": InputModality.IMAGE.value,
            "status": "KAIROS_PIPELINE_NOT_CASE_LINKED",
            "entrypoint": "POST /documents/ingest (image OCR)",
            "detail": "Kairos document extraction accepts supported raster formats; this demo does not upload or link an image.",
        },
        {
            "modality": InputModality.VIDEO.value,
            "status": "NO_PROCESSOR_CONNECTED",
            "entrypoint": None,
            "detail": "No video evidence processor is connected to this ResolveAI workflow.",
        },
        {
            "modality": InputModality.TELEMETRY.value,
            "status": "KAIROS_PIPELINE_NOT_CASE_LINKED",
            "entrypoint": "POST /events/*",
            "detail": "Kairos operational event ingestion exists separately; events are not linked to this demo's evidence dependency graph.",
        },
    ]
    return {
        "focus_level": level.value,
        "focus_scope": scopes[level],
        "focus_policy": "Complete bounded impact traversal and revision-bound action checks run at every focus level; focus changes investigation emphasis only.",
        "requested_modalities": requested,
        "scenario_modalities": sorted(scenario_modalities),
        "unconnected_modalities": sorted(set(requested) - scenario_modalities),
        "modality_capabilities": modality_capabilities,
        "runtime_status": "SYNTHETIC_TRACE_ONLY",
        "media_processing_connected": False,
    }


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def parse_ts(value: str, field_name: str) -> str:
    """Normalise an ISO-8601 timestamp to UTC with microseconds, so string order is time order."""
    if value == VALID_TO_OPEN:
        return value
    try:
        ts = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"{field_name}: not an ISO-8601 timestamp") from exc
    if ts.tzinfo is None:
        raise ContractError(f"{field_name}: timestamp must carry a timezone")
    return ts.astimezone(UTC).isoformat(timespec="microseconds")


def check_id(value: str, field_name: str = "id") -> str:
    if not isinstance(value, str) or not _ID.match(value):
        raise ContractError(f"{field_name}: must match {_ID.pattern}")
    return value


def check_site(value: str) -> str:
    if not isinstance(value, str) or not _SITE.match(value):
        raise ContractError("site_id: must be 1-64 characters of [A-Za-z0-9_-]")
    return value


def check_key(value: str) -> str:
    if not isinstance(value, str) or not _KEY.match(value):
        raise ContractError(f"fact key: must match {_KEY.pattern}")
    return value


def check_authority(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not AUTHORITY_MIN <= value <= AUTHORITY_MAX:
        raise ContractError(f"authority_level: integer {AUTHORITY_MIN}..{AUTHORITY_MAX} (1 strongest)")
    return value


def check_confidence(value: float) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0.0 <= float(value) <= 1.0:
        raise ContractError("confidence: number in [0, 1]")
    return float(value)


def check_value(value: Any) -> Any:
    """Fact values are scalars or flat lists of scalars: what a condition can compare."""
    scalar = (str, int, float, bool)
    if isinstance(value, scalar) or (isinstance(value, list) and all(isinstance(v, scalar) for v in value)):
        return value
    raise ContractError("fact value must be a string, number, boolean or a list of those")


def stable_hash(payload: Any) -> str:
    """Deterministic SHA-256 over canonical JSON. Used for revisions, idempotency and the audit chain."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def encode_value(value: Any) -> str:
    """Fact values are stored as canonical JSON so a string "180" and a number 180 never compare equal."""
    return json.dumps(check_value(value), sort_keys=True)


def decode_value(raw: str | None) -> Any:
    return None if raw in (None, "") else json.loads(raw)


# --------------------------------------------------------------------------------------------
# Decision preconditions — the machine-checkable part of a decision (CausalLatch).
# When evidence changes, a decision is not re-derived by a language model: its preconditions are
# re-evaluated against the current authoritative claims, deterministically.
# --------------------------------------------------------------------------------------------

_OPS = {
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "in": lambda a, b: a in b,
}


@dataclass(frozen=True)
class Condition:
    key: str
    op: str
    value: Any
    material: bool = True

    def __post_init__(self) -> None:
        check_key(self.key)
        if self.op not in _OPS:
            raise ContractError(f"condition op must be one of {sorted(_OPS)}")
        check_value(self.value)
        if not isinstance(self.material, bool):
            raise ContractError("condition material must be a boolean")
        if self.op == "in" and not isinstance(self.value, list):
            raise ContractError("condition 'in' needs a list value")

    def holds(self, actual: Any) -> bool:
        """A missing or incomparable value never satisfies a condition (fail closed)."""
        if actual is None:
            return False
        if isinstance(actual, bool) != isinstance(self.value, bool) and self.op != "in":
            return False
        try:
            return bool(_OPS[self.op](actual, self.value))
        except TypeError:
            return False

    def margin(self, actual: Any) -> float | None:
        """Relative distance from the threshold (0 = on the boundary). None for non-numeric ops."""
        if self.op not in ("<", "<=", ">", ">=") or isinstance(actual, bool):
            return None
        if not isinstance(actual, (int, float)) or not isinstance(self.value, (int, float)):
            return None
        scale = abs(self.value) or 1.0
        return abs(actual - self.value) / scale

    def as_dict(self) -> dict:
        return {"key": self.key, "op": self.op, "value": self.value, "material": self.material}


def parse_conditions(raw: list[dict] | str | None) -> list[Condition]:
    if raw in (None, "", []):
        return []
    try:
        items = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError as exc:
        raise ContractError("conditions must be valid JSON") from exc
    if not isinstance(items, list):
        raise ContractError("conditions must be a list")
    out = []
    for item in items:
        if not isinstance(item, dict):
            raise ContractError("each condition must be an object")
        material = item.get("material", True)
        if not isinstance(material, bool):
            raise ContractError("condition material must be a boolean")
        out.append(Condition(key=item.get("key", ""), op=item.get("op", ""), value=item.get("value"),
                             material=material))
    return out


@dataclass
class ConditionResult:
    condition: Condition
    actual: Any
    claim_id: str | None
    holds: bool

    def as_dict(self) -> dict:
        return {**self.condition.as_dict(), "actual": self.actual, "claim_id": self.claim_id, "holds": self.holds}


def evaluate_conditions(conditions: list[Condition], current: dict[str, tuple[str, Any]]) -> list[ConditionResult]:
    """`current` maps fact key -> (claim_id, value) of the authoritative claim right now."""
    results = []
    for cond in conditions:
        claim_id, value = current.get(cond.key, (None, None))
        results.append(ConditionResult(cond, value, claim_id, cond.holds(value)))
    return results


# --------------------------------------------------------------------------------------------
# Authority-aware conflict resolution (algorithm D)
# --------------------------------------------------------------------------------------------

class Verdict(StrEnum):
    REPLACE = "REPLACE"            # the new evidence is at least as authoritative: it supersedes
    CONTEST = "CONTEST"            # the new evidence is weaker: record a conflict, keep the old claim
    REJECT = "REJECT"              # the new evidence is quarantined: it cannot act at all


@dataclass(frozen=True)
class EvidenceStrength:
    authority_level: int
    verification_status: str
    confidence: float

    def __post_init__(self) -> None:
        check_authority(self.authority_level)
        check_confidence(self.confidence)
        if self.verification_status not in {status.value for status in Verification}:
            raise ContractError(f"unknown verification status: {self.verification_status}")


def resolve_authority(incumbent: EvidenceStrength, challenger: EvidenceStrength) -> Verdict:
    """Decide whether `challenger` may replace `incumbent`.

    Lower-trust evidence never silently replaces stronger verified evidence:
    - a quarantined or below-threshold challenger is rejected outright (Kairos quarantine rule);
    - an unverified challenger can only contest a verified incumbent;
    - otherwise the stronger authority (lower number) wins, and on a tie the newer version replaces.
    """
    if challenger.verification_status == Verification.QUARANTINED or challenger.confidence < QUARANTINE_CONFIDENCE:
        return Verdict.REJECT
    if incumbent.verification_status == Verification.VERIFIED and challenger.verification_status != Verification.VERIFIED:
        return Verdict.CONTEST
    if challenger.authority_level <= incumbent.authority_level:
        return Verdict.REPLACE
    return Verdict.CONTEST


@dataclass
class CascadeItem:
    """One node the cascade examined, with what it concluded and why."""
    node_id: str
    label: str
    depth: int
    before: str
    after: str
    reason: str
    via: list[str] = field(default_factory=list)
    detail: dict = field(default_factory=dict)

    @property
    def changed(self) -> bool:
        return self.before != self.after

    def as_dict(self) -> dict:
        return {"node_id": self.node_id, "label": self.label, "depth": self.depth, "before": self.before,
                "after": self.after, "changed": self.changed, "reason": self.reason, "via": self.via,
                "detail": self.detail}
