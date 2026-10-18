"""Status and scoring behavior for benchmark summaries."""

from __future__ import annotations

from benchmark import _graph_run, _score_decisions


def test_missing_falkordb_configuration_is_reported_as_blocked() -> None:
    result = _graph_run([], None, None, allow_remote=False, keep_graph=False)

    assert result["status"] == "BLOCKED"
    assert result["graph_name"] is None
    assert result["engine_evaluation"] == "NOT_RUN"
    assert "No FalkorDB URL" in result["reason"]


def test_decision_metrics_count_misses_and_false_invalidations() -> None:
    scenario = {
        "scenario_id": "scenario-test",
        "expected_affected_decisions": ["d-expected", "d-missed"],
        "expected_unaffected_decisions": ["d-safe"],
    }

    result = _score_decisions([scenario], {"scenario-test": {"d-expected", "d-safe"}})

    assert result["correctly_identified_impacted_decisions"] == 1
    assert result["missed_invalidations"] == 1
    assert result["false_invalidations"] == 1
    assert result["precision"] == 0.5
    assert result["recall"] == 0.5
