"""Isolated synthetic ResolveAI-to-CausalLatch-to-FalkorDB integration journey."""
from __future__ import annotations

import json

from .model import (
    ActionStatus,
    AgentFocusLevel,
    DerivedStatus,
    EvidenceStrength,
    Label,
    MemoryKind,
    InputModality,
    Rel,
    SourceStatus,
    Verification,
    Verdict,
    build_agent_focus_plan,
    evaluate_conditions,
    parse_conditions,
    resolve_authority,
    stable_hash,
)
from .store import FalkorDriftStore

CASE = "DEMO-DRIFT-HV-001"
ASSET = "DEMO-HV-PUMP-001"
DOCUMENT = "DEMO-DRIFT-SOP-001"
OLD_SOURCE = "DEMO-DRIFT-SOP-V1"
NEW_SOURCE = "DEMO-DRIFT-SOP-V2"
OLD_CLAIM = "DEMO-DRIFT-CLAIM-V1"
NEW_CLAIM = "DEMO-DRIFT-CLAIM-V2"
MEMORY = "DEMO-DRIFT-MEMORY-001"
DECISION = "DEMO-DRIFT-DECISION-001"
PLAN = "DEMO-DRIFT-PLAN-001"
ACTION = "DEMO-DRIFT-ACTION-001"
CHANGE = "DEMO-DRIFT-CHANGE-V2"
AUDIT = "DEMO-DRIFT-AUDIT-V2"
CURATOR = "DEMO-DRIFT-AGENT-CURATOR"
INVESTIGATOR = "DEMO-DRIFT-AGENT-INVESTIGATOR"
CURATOR_SESSION = "DEMO-DRIFT-SESSION-CURATOR"
INVESTIGATOR_SESSION = "DEMO-DRIFT-SESSION-INVESTIGATOR"
DECISION_REVISION_1 = "DEMO-DRIFT-DECISION-REV-001"
DECISION_REVISION_2 = "DEMO-DRIFT-DECISION-REV-002"
APPROVAL = "DEMO-DRIFT-APPROVAL-REV-001"


def run_evidence_supersession(
    store: FalkorDriftStore,
    site_id: str,
    *,
    focus_level: AgentFocusLevel | str = AgentFocusLevel.HYPERFOCUS,
    requested_modalities: list[InputModality | str] | None = None,
) -> dict:
    """Persist a repeatable source change, find dependent memory and suspend its action."""
    created_at = "2026-10-18T08:00:00+00:00"
    focus_plan = build_agent_focus_plan(
        focus_level,
        [InputModality.DOCUMENT, InputModality.TEXT]
        if requested_modalities is None else requested_modalities,
    )
    store.upsert_node(site_id, Label.ASSET, ASSET, {
        "case_id": CASE, "asset_tag": "DEMO-HV-PUMP-001", "synthetic": True,
    })
    store.upsert_node(site_id, Label.DOCUMENT, DOCUMENT, {
        "case_id": CASE, "title": "Synthetic supplier security-audit procedure", "synthetic": True,
    })
    store.upsert_node(site_id, Label.SOURCE_VERSION, OLD_SOURCE, {
        "case_id": CASE, "status": SourceStatus.SUPERSEDED.value, "authority_level": 4,
        "verification_status": Verification.VERIFIED.value, "confidence": 0.94,
        "observed_at": created_at, "event_time": "2026-10-01T08:00:00+00:00",
    })
    store.upsert_node(site_id, Label.SOURCE_VERSION, NEW_SOURCE, {
        "case_id": CASE, "status": SourceStatus.ACTIVE.value, "authority_level": 2,
        "verification_status": Verification.VERIFIED.value, "confidence": 0.99,
        "observed_at": created_at, "event_time": "2026-10-18T08:00:00+00:00",
    })
    store.upsert_node(site_id, Label.CLAIM, OLD_CLAIM, {
        "case_id": CASE, "fact_key": "inspection_interval_days", "fact_value": 180,
        "status": "SUPERSEDED", "authority_level": 4, "verification_status": "VERIFIED",
    })
    store.upsert_node(site_id, Label.CLAIM, NEW_CLAIM, {
        "case_id": CASE, "fact_key": "inspection_interval_days", "fact_value": 90,
        "status": "ACTIVE", "authority_level": 2, "verification_status": "VERIFIED",
    })
    store.upsert_node(site_id, Label.AGENT, CURATOR, {
        "case_id": CASE, "name": "Evidence Curator", "specialty": "source validation",
        "synthetic": True,
    })
    store.upsert_node(site_id, Label.AGENT, INVESTIGATOR, {
        "case_id": CASE, "name": "ResolveAI Supplier Risk Specialist", "specialty": "supplier audit decisions",
        "synthetic": True,
    })
    store.upsert_node(site_id, Label.AGENT_SESSION, CURATOR_SESSION, {
        "case_id": CASE, "focus_level": focus_plan["focus_level"],
        "focus_scope": f"source curator: {focus_plan['focus_scope']}",
        "requested_modalities": focus_plan["requested_modalities"],
        "unconnected_modalities": focus_plan["unconnected_modalities"],
        "trace_kind": "synthetic_demo", "synthetic": True,
    })
    store.upsert_node(site_id, Label.AGENT_SESSION, INVESTIGATOR_SESSION, {
        "case_id": CASE, "focus_level": focus_plan["focus_level"],
        "focus_scope": f"decision investigator: {focus_plan['focus_scope']}",
        "requested_modalities": focus_plan["requested_modalities"],
        "unconnected_modalities": focus_plan["unconnected_modalities"],
        "trace_kind": "synthetic_demo", "synthetic": True,
    })
    store.upsert_node(site_id, Label.MEMORY, MEMORY, {
        "case_id": CASE, "status": DerivedStatus.STALE.value, "memory_kind": MemoryKind.PROCEDURAL.value,
        "summary": "Prior supplier audit interval recalled by a second specialist agent.",
        "agent_id": INVESTIGATOR, "source_agent_id": CURATOR, "synthetic": True,
    })
    existing_decision = store.read_node(site_id, DECISION)
    if not existing_decision:
        store.upsert_node(site_id, Label.DECISION, DECISION, {
            "case_id": CASE, "status": DerivedStatus.VALID.value, "revision_n": 0,
            "summary": "Schedule the supplier audit using the prior approved procedure.",
            "conditions": json.dumps([{"key": "inspection_interval_days", "op": "==", "value": 180, "material": True}]),
            "generated_at": created_at, "synthetic": True,
        })
    store.upsert_node(site_id, Label.PLAN, PLAN, {
        "case_id": CASE, "status": DerivedStatus.STALE.value, "summary": "Schedule the supplier audit.",
        "synthetic": True,
    })
    if not store.read_node(site_id, ACTION):
        store.upsert_node(site_id, Label.ACTION, ACTION, {
            "case_id": CASE, "status": ActionStatus.APPROVED.value,
            "asset_id": ASSET, "requires_human_approval": True, "synthetic": True,
        })
    store.upsert_node(site_id, Label.CHANGE, CHANGE, {
        "case_id": CASE, "change_kind": "SUPERSEDE", "source_id": NEW_SOURCE,
        "observed_at": created_at, "idempotency_key": "synthetic-hv-sop-v2", "synthetic": True,
    })

    for source in (OLD_SOURCE, NEW_SOURCE):
        store.link(site_id, Label.SOURCE_VERSION, source, Rel.VERSION_OF, Label.DOCUMENT, DOCUMENT)
    store.link(site_id, Label.SOURCE_VERSION, NEW_SOURCE, Rel.SUPERSEDES, Label.SOURCE_VERSION, OLD_SOURCE)
    store.link(site_id, Label.AGENT, CURATOR, Rel.HAS_SESSION, Label.AGENT_SESSION, CURATOR_SESSION)
    store.link(site_id, Label.AGENT, INVESTIGATOR, Rel.HAS_SESSION, Label.AGENT_SESSION, INVESTIGATOR_SESSION)
    store.link(site_id, Label.AGENT_SESSION, CURATOR_SESSION, Rel.PRODUCED, Label.MEMORY, MEMORY)
    store.link(site_id, Label.MEMORY, MEMORY, Rel.RECALLED_IN, Label.AGENT_SESSION, INVESTIGATOR_SESSION)
    store.link(site_id, Label.AGENT_SESSION, INVESTIGATOR_SESSION, Rel.PRODUCED, Label.DECISION, DECISION)
    store.link(site_id, Label.CLAIM, OLD_CLAIM, Rel.SUPPORTED_BY, Label.SOURCE_VERSION, OLD_SOURCE)
    store.link(site_id, Label.CLAIM, NEW_CLAIM, Rel.SUPPORTED_BY, Label.SOURCE_VERSION, NEW_SOURCE)
    store.link(site_id, Label.CLAIM, NEW_CLAIM, Rel.SUPERSEDES, Label.CLAIM, OLD_CLAIM)
    store.link(site_id, Label.MEMORY, MEMORY, Rel.DERIVED_FROM, Label.CLAIM, OLD_CLAIM)
    store.link(site_id, Label.DECISION, DECISION, Rel.DEPENDS_ON, Label.MEMORY, MEMORY)
    store.link(site_id, Label.PLAN, PLAN, Rel.DEPENDS_ON, Label.DECISION, DECISION)
    store.link(site_id, Label.ACTION, ACTION, Rel.DEPENDS_ON, Label.PLAN, PLAN)
    store.link(site_id, Label.ACTION, ACTION, Rel.REQUIRES_APPROVAL, Label.DECISION, DECISION)
    for node, label in (
        (OLD_SOURCE, Label.SOURCE_VERSION), (OLD_CLAIM, Label.CLAIM), (MEMORY, Label.MEMORY),
        (DECISION, Label.DECISION), (PLAN, Label.PLAN), (ACTION, Label.ACTION),
    ):
        store.link(site_id, label, node, Rel.INVALIDATED_BY, Label.CHANGE, CHANGE)

    incumbent = EvidenceStrength(4, Verification.VERIFIED.value, 0.94)
    challenger = EvidenceStrength(2, Verification.VERIFIED.value, 0.99)
    authority_verdict = resolve_authority(incumbent, challenger)
    if authority_verdict != Verdict.REPLACE:
        raise RuntimeError("synthetic source authority check did not permit the verified stronger revision")

    # The decision contract lives on the Decision and is evaluated against the new authoritative Claim.
    decision = store.read_node(site_id, DECISION)
    conditions = parse_conditions(decision["properties"].get("conditions") if decision else None)
    conditions_json = json.dumps([condition.as_dict() for condition in conditions], sort_keys=True)
    prior_revision_hash = stable_hash({
        "case_id": CASE, "decision_id": DECISION, "revision_n": 1,
        "conditions": conditions_json, "dependencies": [MEMORY],
        "claim_id": OLD_CLAIM, "claim_value": 180,
    })
    first_revision = store.append_decision_revision(
        site_id, decision_id=DECISION, revision_id=DECISION_REVISION_1,
        expected_revision_n=0, previous_revision_id=None,
        graph_revision=prior_revision_hash, status=DerivedStatus.VALID.value,
        conditions_json=conditions_json, dependency_ids=[MEMORY], created_at=created_at,
        reason="Initial decision used the approved 180-day procedure.",
    )
    store.link(site_id, Label.DECISION_REVISION, DECISION_REVISION_1, Rel.DEPENDS_ON, Label.MEMORY, MEMORY)
    store.upsert_node(site_id, Label.APPROVAL, APPROVAL, {
        "case_id": CASE, "decision_id": DECISION, "revision_id": DECISION_REVISION_1,
        "graph_revision": first_revision["graph_revision"], "approval_status": "VALID",
        "approved_by": "synthetic procurement reviewer", "approved_at": created_at,
        "synthetic": True,
    })
    store.link(site_id, Label.APPROVAL, APPROVAL, Rel.ON_REVISION, Label.DECISION_REVISION, DECISION_REVISION_1)
    store.link(site_id, Label.ACTION, ACTION, Rel.APPROVED_BY, Label.APPROVAL, APPROVAL)
    condition_results = evaluate_conditions(
        conditions,
        {"inspection_interval_days": (NEW_CLAIM, 90)},
    )
    all_hold = bool(condition_results) and all(item.holds for item in condition_results)
    current_status = DerivedStatus.VALID.value if all_hold else DerivedStatus.INVALIDATED.value
    current_dependencies = [NEW_CLAIM]
    current_revision_hash = stable_hash({
        "case_id": CASE, "decision_id": DECISION, "revision_n": 2,
        "conditions": conditions_json, "dependencies": current_dependencies,
        "claim_id": NEW_CLAIM, "claim_value": 90,
    })
    current_revision = store.append_decision_revision(
        site_id, decision_id=DECISION, revision_id=DECISION_REVISION_2,
        expected_revision_n=1, previous_revision_id=DECISION_REVISION_1,
        graph_revision=current_revision_hash, status=current_status,
        conditions_json=conditions_json, dependency_ids=current_dependencies,
        created_at=created_at, reason="The newer approved procedure changed the audit interval.",
    )
    store.link(site_id, Label.DECISION_REVISION, DECISION_REVISION_2, Rel.DEPENDS_ON, Label.CLAIM, NEW_CLAIM)
    paths = store.find_impacts(site_id, [OLD_SOURCE])
    current_revision_node = store.read_node(site_id, DECISION_REVISION_2)
    approval_node = store.read_node(site_id, APPROVAL)
    approval_matches = bool(
        current_revision_node and approval_node
        and approval_node["properties"].get("approval_status") == "VALID"
        and approval_node["properties"].get("graph_revision") == current_revision["graph_revision"]
    )
    action_status = ActionStatus.APPROVED.value if all_hold and approval_matches else ActionStatus.SUSPENDED.value
    store.update_node_properties(site_id, Label.ACTION, ACTION, {"status": action_status})
    store.upsert_node(site_id, Label.AUDIT, AUDIT, {
        "case_id": CASE, "actor": "Kairos deterministic synthetic workflow",
        "event": "source_superseded_and_dependents_revalidated",
        "source_before": OLD_SOURCE, "source_after": NEW_SOURCE, "decision_id": DECISION,
        "impacted_ids": [item.node_id for item in paths], "action_status": action_status,
        "conditions_hold": all_hold,
        "prior_revision": first_revision["graph_revision"],
        "current_revision": current_revision["graph_revision"],
        "approval_matches_current": approval_matches,
        "chain_hash": stable_hash({"case": CASE, "change": CHANGE, "paths": [item.as_dict() for item in paths],
                                    "prior_revision": first_revision["graph_revision"],
                                    "current_revision": current_revision["graph_revision"]}),
        "recorded_at": created_at, "synthetic": True,
    })

    statuses = {}
    for node_id in (OLD_SOURCE, NEW_SOURCE, OLD_CLAIM, NEW_CLAIM, MEMORY, DECISION, PLAN, ACTION):
        node = store.read_node(site_id, node_id)
        statuses[node_id] = node["properties"].get("status") if node else "MISSING"
    return {
        "case_id": CASE,
        "scenario": "synthetic_only",
        "authority_verdict": authority_verdict.value,
        "source_before": OLD_SOURCE,
        "source_after": NEW_SOURCE,
        "impact_paths": [item.as_dict() for item in paths],
        "condition_results": [item.as_dict() for item in condition_results],
        "decision_status": current_status,
        "decision_revision": {
            "previous_revision_id": DECISION_REVISION_1,
            "previous_graph_revision": first_revision["graph_revision"],
            "current_revision_id": DECISION_REVISION_2,
            "current_graph_revision": current_revision["graph_revision"],
        },
        "human_review": {
            "approval_id": APPROVAL,
            "approved_revision_id": DECISION_REVISION_1,
            "approval_status": "VALID_FOR_PRIOR_REVISION",
            "matches_current_revision": approval_matches,
        },
        "agent_focus_trace": [
            {"agent_id": CURATOR, "session_id": CURATOR_SESSION,
             "focus_level": focus_plan["focus_level"],
             "scope": f"source curator: {focus_plan['focus_scope']}", "trace_kind": "synthetic_demo"},
            {"agent_id": INVESTIGATOR, "session_id": INVESTIGATOR_SESSION,
             "focus_level": focus_plan["focus_level"],
             "scope": f"decision investigator: {focus_plan['focus_scope']}", "trace_kind": "synthetic_demo"},
        ],
        "focus_plan": focus_plan,
        "action_eligibility": "APPROVED" if action_status == ActionStatus.APPROVED.value else "SUSPENDED",
        "statuses": statuses,
        "audit_chain_hash": stable_hash({"case": CASE, "change": CHANGE, "paths": [item.as_dict() for item in paths],
                                          "prior_revision": first_revision["graph_revision"],
                                          "current_revision": current_revision["graph_revision"]}),
        "external_actions_executed": False,
    }
