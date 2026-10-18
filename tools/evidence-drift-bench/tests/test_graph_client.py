"""Safety and query-shape tests for the FalkorDB adapter."""

from __future__ import annotations

import os
import uuid

import pytest
from generate_fixtures import generate_fixtures
from graph_client import (
    IMPACT_QUERY,
    FalkorGraphRunner,
    connect_falkordb,
    validate_test_uri,
)

from benchmark import _score_decisions


def test_loopback_falkordb_urls_are_accepted() -> None:
    validate_test_uri("redis://127.0.0.1:6379")
    validate_test_uri("rediss://localhost:6380")


def test_remote_falkordb_url_requires_explicit_test_database_override() -> None:
    with pytest.raises(ValueError, match="Remote FalkorDB is blocked"):
        validate_test_uri("redis://graph.example.test:6379")
    validate_test_uri("redis://graph.example.test:6379", allow_remote=True)


def test_falkordb_url_rejects_unknown_schemes() -> None:
    with pytest.raises(ValueError, match="redis:// or rediss://"):
        validate_test_uri("http://localhost:6379")


def test_impact_query_uses_parameters_and_tenant_ownership() -> None:
    assert "$tenant_node_id" in IMPACT_QUERY
    assert "$source_id" in IMPACT_QUERY
    assert "$traversable_kinds" in IMPACT_QUERY
    assert "OWNS" in IMPACT_QUERY
    assert "BenchmarkNode" in IMPACT_QUERY


@pytest.mark.integration
def test_falkordb_traverses_real_fixture_graph_when_local_instance_is_configured() -> None:
    """Use an isolated EDB_TEST graph only when a local test server is configured."""
    uri = os.environ.get("FALKORDB_URL")
    if not uri:
        pytest.skip("FALKORDB_URL is not configured")
    validate_test_uri(uri)
    client = connect_falkordb(uri)
    graph_name = f"EDB_TEST_PYTEST_{uuid.uuid4().hex[:10]}"
    assert graph_name not in client.list_graphs()
    scenarios = generate_fixtures(count=50, seed=98)["scenarios"]
    graph = client.select_graph(graph_name)
    try:
        runner = FalkorGraphRunner(graph)
        runner.load_scenarios(scenarios)
        results = {scenario["scenario_id"]: runner.evaluate_scenario(scenario) for scenario in scenarios}
        metrics = _score_decisions(
            scenarios,
            {scenario_id: set(result["affected_decisions"]) for scenario_id, result in results.items()},
        )
        assert metrics["missed_invalidations"] == 0
        assert metrics["false_invalidations"] == 0
        assert all(
            results[scenario["scenario_id"]]["memory_valid"] is scenario["expected_memory_valid"]
            for scenario in scenarios
        )
    finally:
        if graph_name in client.list_graphs():
            client.select_graph(graph_name).delete()
