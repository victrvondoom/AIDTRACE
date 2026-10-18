"""Unit tests for deterministic fixtures and the independent oracle."""

from __future__ import annotations

from generate_fixtures import SCENARIO_TYPES, generate_fixtures
from oracle import reference_impact, reference_memory_valid, validate_fixture_document


def test_default_fixture_set_is_deterministic_and_covers_required_scenarios() -> None:
    first = generate_fixtures(count=50, seed=98)
    second = generate_fixtures(count=50, seed=98)

    assert first == second
    assert first["scenario_count"] == 50
    assert set(SCENARIO_TYPES) <= {scenario["scenario_type"] for scenario in first["scenarios"]}


def test_every_fixture_has_graph_evidence_expectations_and_explanation() -> None:
    document = generate_fixtures(count=50, seed=98)

    for scenario in document["scenarios"]:
        assert scenario["nodes"]
        assert scenario["relationships"]
        assert scenario["original_evidence"]["id"] == scenario["source_evidence_id"]
        assert scenario["updated_evidence"]["id"] == scenario["updated_evidence_id"]
        assert scenario["events"]
        assert isinstance(scenario["expected_memory_valid"], bool)
        assert scenario["explanation"].strip()


def test_independent_reference_traversal_matches_declared_oracle() -> None:
    document = generate_fixtures(count=50, seed=98)

    assert validate_fixture_document(document)["status"] == "PASS"
    for scenario in document["scenarios"]:
        assert reference_impact(scenario) == set(scenario["expected_affected_decisions"])
        assert reference_memory_valid(scenario) is scenario["expected_memory_valid"]


def test_duplicate_event_fixture_repeats_the_same_event_identifier() -> None:
    scenarios = generate_fixtures(count=50, seed=98)["scenarios"]
    duplicate = next(s for s in scenarios if s["scenario_type"] == "duplicate_events")

    assert len(duplicate["events"]) == 2
    assert duplicate["events"][0] == duplicate["events"][1]
    assert duplicate["events"][0]["event_id"] == duplicate["events"][1]["event_id"]
