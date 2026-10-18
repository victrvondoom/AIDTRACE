from __future__ import annotations

import pytest

from api.services.drift.model import (
    ContractError,
    AgentFocusLevel,
    EvidenceStrength,
    InputModality,
    Verdict,
    Verification,
    build_agent_focus_plan,
    parse_conditions,
    resolve_authority,
)


def test_condition_parser_rejects_invalid_json_and_non_boolean_material() -> None:
    with pytest.raises(ContractError, match="valid JSON"):
        parse_conditions("not-json")
    with pytest.raises(ContractError, match="material"):
        parse_conditions([{"key": "pressure", "op": "<", "value": 10, "material": "false"}])


def test_condition_evaluation_fails_closed_for_missing_value() -> None:
    condition = parse_conditions([{"key": "pressure", "op": "<", "value": 10}])[0]

    assert condition.holds(None) is False
    assert condition.holds("unknown") is False
    assert condition.holds(9) is True


def test_quarantined_or_low_confidence_evidence_cannot_replace() -> None:
    incumbent = EvidenceStrength(2, Verification.VERIFIED.value, 0.99)

    assert resolve_authority(incumbent, EvidenceStrength(1, Verification.VERIFIED.value, 0.69)) == Verdict.REJECT
    assert resolve_authority(incumbent, EvidenceStrength(1, Verification.QUARANTINED.value, 0.99)) == Verdict.REJECT


def test_weaker_evidence_contests_and_equal_authority_verified_evidence_replaces() -> None:
    incumbent = EvidenceStrength(2, Verification.VERIFIED.value, 0.99)

    assert resolve_authority(incumbent, EvidenceStrength(3, Verification.VERIFIED.value, 0.95)) == Verdict.CONTEST
    assert resolve_authority(incumbent, EvidenceStrength(2, Verification.VERIFIED.value, 0.95)) == Verdict.REPLACE


def test_focus_plan_records_requested_media_without_claiming_processing() -> None:
    plan = build_agent_focus_plan(
        AgentFocusLevel.HYPERFOCUS,
        [InputModality.DOCUMENT, InputModality.VOICE, InputModality.IMAGE],
    )

    assert plan["focus_scope"] == "one changed source through its transitive decision-to-action path"
    assert plan["scenario_modalities"] == ["DOCUMENT", "TEXT"]
    assert plan["unconnected_modalities"] == ["IMAGE", "VOICE"]
    assert plan["media_processing_connected"] is False
    assert "Complete bounded impact traversal" in plan["focus_policy"]
    capabilities = {item["modality"]: item for item in plan["modality_capabilities"]}
    assert capabilities["IMAGE"]["status"] == "KAIROS_PIPELINE_NOT_CASE_LINKED"
    assert capabilities["VOICE"]["entrypoint"] == "POST /elicitation/{work_order_id}/voice"
    assert capabilities["VIDEO"]["status"] == "NO_PROCESSOR_CONNECTED"
    assert capabilities["TELEMETRY"]["status"] == "KAIROS_PIPELINE_NOT_CASE_LINKED"


@pytest.mark.parametrize(
    ("authority_level", "verification_status", "confidence"),
    [
        (0, Verification.VERIFIED.value, 1.0),
        (2, "MAYBE", 0.9),
        (2, Verification.VERIFIED.value, 1.1),
    ],
)
def test_evidence_strength_contract_rejects_invalid_values(
    authority_level: int, verification_status: str, confidence: float
) -> None:
    with pytest.raises(ContractError):
        EvidenceStrength(authority_level, verification_status, confidence)
