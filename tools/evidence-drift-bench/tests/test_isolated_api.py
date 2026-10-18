"""Integration checks call Kairos's genuine drift router and local FalkorDB."""

from __future__ import annotations

import os

import pytest
from adapters.kairos_api import compatibility
from compare_engines import comparison_markdown
from generate_fixtures import generate_fixtures
from run_isolated_api import DEFAULT_BACKEND, _scenario_metrics, run_live


def test_case_scoring_does_not_mask_false_or_missed_impacts() -> None:
    item = next(case for case in generate_fixtures()["scenarios"]
                if case["scenario_type"] == "multi_hop_dependency_invalidation")
    expected = set(item["expected_affected_decisions"])
    metrics = _scenario_metrics(item, expected - {next(iter(expected))})
    assert metrics["false_negatives"] == 1 and metrics["recall"] < 1
    metrics = _scenario_metrics(item, expected | {"unrelated-decision"})
    assert metrics["false_positives"] == 1 and metrics["precision"] < 1


@pytest.mark.integration
def test_real_kairos_router_executes_compatible_fixtures_and_cleans_graph() -> None:
    db_url = os.environ.get("FALKORDB_URL")
    if not db_url:
        pytest.skip("FALKORDB_URL is required for real Kairos ASGI integration")
    from benchmark import DEFAULT_FIXTURE_PATH

    result = run_live(DEFAULT_FIXTURE_PATH, DEFAULT_BACKEND, db_url)
    assert result["transport"] == "in_process_ASGI_real_Kairos_router"
    assert result["status"] == "PASSED", result.get("reason")
    assert result["compatible_scenarios"] == result["scenarios_executed"] == 31
    assert result["unsupported_scenarios"] == 19
    assert result["decision_metrics"]["missed_invalidations"] == 0
    assert result["decision_metrics"]["false_invalidations"] == 0
    assert result["repeat_consistency"]["consistent"] == 31
    assert result["probes"]["authentication"]["passed"] is True
    assert result["probes"]["empty_impact"]["passed"] is True
    assert result["probes"]["pure_impact"]["fixture_compatible"] is False
    assert result["probes"]["pure_impact"]["http_status"] == 403
    assert result["cleanup"] == "deleted_benchmark_owned_graph"
    assert result["source_stable"] is True
    assert all(case["http_status"] == 200 for case in result["scenario_results"] if case["executed"])
    assert all(case["duplicate_link_stable"] for case in result["scenario_results"] if case["scenario_type"] == "duplicate_events")
    assert sum(compatibility(case)["status"] == "SUPPORTED_IMPACT_ONLY" for case in generate_fixtures()["scenarios"]) == 31


def test_real_report_markdown_counts_executed_compatibility() -> None:
    item = {"scenario_id": "s", "scenario_type": "direct_decision_invalidation", "status": "PASSED",
            "compatibility_status": "SUPPORTED_IMPACT_ONLY"}
    report = {"run_timestamp_utc": "2026-10-18T00:00:00Z", "direct_falkordb": {"status": "PASS"},
              "kairos_api": {"status": "PASSED", "scenario_results": [item], "evaluation_scope": "impact only"}}
    markdown = comparison_markdown(report)
    assert "1 of 1 fixtures" in markdown
    assert "Mean latency" in markdown
