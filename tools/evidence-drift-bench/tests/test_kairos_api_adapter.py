"""Deterministic contracts for source-verified Kairos HTTP integration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import pytest
from adapters.kairos_api import (
    HTTPTransport,
    KairosAPIAdapter,
    KairosAPIError,
    build_impact_graph,
    compatibility,
    parse_impact,
    require_loopback,
)
from compare_engines import _empty_api, comparison_markdown, run_comparison
from generate_fixtures import generate_fixtures

from benchmark import _score_decisions

SITE = "EDB_BENCH_TEST01"
SCENARIOS = generate_fixtures()["scenarios"]


def scenario(kind: str) -> dict:
    return next(item for item in SCENARIOS if item["scenario_type"] == kind)


def fake_transport(method: str, path: str, payload: dict | None, token: str) -> dict:
    if token == "denied":
        raise KairosAPIError("HTTP 401", 401)
    if path == "/auth/me":
        return {"user_id": "test-user", "role": "engineer", "site_id": "EDB_BENCH_FOREIGN" if token == "foreign" else SITE}
    if path == "/drift/health":
        return {"reachable": True, "site_graph_exists": False}
    if token == "foreign":
        raise KairosAPIError("HTTP 403", 403)
    if "/nodes/" in path:
        return {"node_id": payload["node_id"], "label": payload["label"], "status": "created"}
    if "/edges/" in path:
        return {"source_id": payload["source_id"], "target_id": payload["target_id"],
                "relationship": payload["relationship"], "status": "linked"}
    if "/impact/" in path:
        return {"site_id": SITE, "traversal_limited": False, "impacted": []}
    raise AssertionError(path)


def test_contract_coverage_is_explicit() -> None:
    states = [compatibility(item)["status"] for item in SCENARIOS]
    assert len(states) == 50
    assert set(states) == {"SUPPORTED_IMPACT_ONLY", "UNSUPPORTED"}
    assert compatibility(scenario("independently_supported_conclusion"))["status"] == "UNSUPPORTED"
    assert compatibility(scenario("approval_invalidation"))["status"] == "UNSUPPORTED"


def test_graph_translation_uses_kairos_dependency_direction() -> None:
    item = scenario("multi_hop_dependency_invalidation")
    nodes, edges = build_impact_graph(item)
    assert any(node["label"] == "Claim" for node in nodes)
    assert any(edge["relationship"] == "SUPPORTED_BY" for edge in edges)
    first = f"{item['scenario_id']}:decision:root"
    second = f"{item['scenario_id']}:decision:dependent-1"
    assert any(edge["source_id"] == second and edge["target_id"] == first for edge in edges)
    assert all(edge["kind"] == "logical" for edge in edges)


def test_preflight_auth_rejection_and_bypass_rejection() -> None:
    assert KairosAPIAdapter(fake_transport, "good", SITE).preflight()["identity_verified"] is True
    with pytest.raises(KairosAPIError) as denied:
        KairosAPIAdapter(fake_transport, "denied", SITE).preflight()
    assert denied.value.status_code == 401

    def admin(method: str, path: str, payload: dict | None, token: str) -> dict:
        result = fake_transport(method, path, payload, token)
        if path == "/auth/me":
            result["role"] = "admin"
        return result

    with pytest.raises(KairosAPIError, match="admin and bypass"):
        KairosAPIAdapter(admin, "good", SITE).preflight()


def test_preflight_rejects_existing_graph_and_wrong_site() -> None:
    def wrong(method: str, path: str, payload: dict | None, token: str) -> dict:
        result = fake_transport(method, path, payload, token)
        if path == "/drift/health":
            result["site_graph_exists"] = True
        return result

    with pytest.raises(KairosAPIError, match="absent"):
        KairosAPIAdapter(wrong, "good", SITE).preflight()
    with pytest.raises(KairosAPIError, match="site-bound"):
        KairosAPIAdapter(fake_transport, "foreign", SITE).preflight()


def test_parse_impact_deduplicates_and_validates_paths() -> None:
    root, dependent = "source", "decision"
    row = {"node_id": dependent, "depth": 1, "path": [root, dependent]}
    response = {"site_id": SITE, "traversal_limited": False, "impacted": [row, dict(row)]}
    assert parse_impact(response, SITE, {root, dependent}, root) == {dependent}
    for broken in (
        {**response, "site_id": "OTHER"}, {**response, "impacted": None},
        {**response, "impacted": [{"node_id": "unknown", "depth": 1, "path": [root, "unknown"]}]},
        {**response, "impacted": [{"node_id": dependent, "depth": 2, "path": [root, dependent]}]},
    ):
        with pytest.raises(KairosAPIError):
            parse_impact(broken, SITE, {root, dependent}, root)


def test_missing_data_and_stale_memory_impact_is_not_validity() -> None:
    item = scenario("stale_agent_memory")
    adapter = KairosAPIAdapter(fake_transport, "good", SITE)
    known = adapter.load_scenario(item)
    result = adapter.evaluate(item, known)
    assert result.impacted_memories == frozenset()
    assert not hasattr(result, "memory_valid")
    assert result.unaffected_decisions == set(item["expected_affected_decisions"] + item["expected_unaffected_decisions"])

    memory = item["expected_memory_ids"][0]
    claim = item["source_evidence_id"].replace(":evidence:", ":claim:")

    def impacted(method: str, path: str, payload: dict | None, token: str) -> dict:
        if "/impact/" not in path:
            return fake_transport(method, path, payload, token)
        return {"site_id": SITE, "traversal_limited": False, "impacted": [
            {"node_id": claim, "depth": 1, "path": [item["source_evidence_id"], claim]},
            {"node_id": memory, "depth": 2, "path": [item["source_evidence_id"], claim, memory]},
        ]}

    stale = KairosAPIAdapter(impacted, "good", SITE).evaluate(item, known)
    assert stale.impacted_memories == {memory}


def test_tenant_isolation_denial() -> None:
    adapter = KairosAPIAdapter(fake_transport, "good", SITE)
    assert adapter.check_foreign_site_denial("foreign") is True
    with pytest.raises(KairosAPIError, match="Foreign test token"):
        adapter.check_foreign_site_denial("good")


def test_oracle_comparison_detects_missing_and_false_impacts() -> None:
    item = scenario("direct_decision_invalidation")
    metrics = _score_decisions([item], {item["scenario_id"]: set()})
    assert metrics["missed_invalidations"] == len(item["expected_affected_decisions"])
    unrelated = item["expected_unaffected_decisions"]
    if unrelated:
        metrics = _score_decisions([item], {item["scenario_id"]: set(item["expected_affected_decisions"] + unrelated)})
        assert metrics["false_invalidations"] == len(unrelated)


def test_report_generation_has_no_fabricated_api_metrics() -> None:
    api = _empty_api("No API", SCENARIOS)
    assert api["scenarios_executed"] == 0 and api["decision_metrics"] is None
    report = {"run_timestamp_utc": "2026-10-18T00:00:00+00:00",
              "direct_falkordb": {"status": "PASS", "scenarios_executed": 50}, "kairos_api": api}
    markdown = comparison_markdown(report)
    assert "Kairos actual API" in markdown and "BLOCKED" in markdown
    assert "50" in markdown


def test_dry_run_report_uses_real_fixture_and_never_sends_http(tmp_path: Path) -> None:
    fixture_path = tmp_path / "fixtures.json"
    fixture_path.write_text(json.dumps(generate_fixtures()), encoding="utf-8")
    args = argparse.Namespace(fixtures=fixture_path, direct_report=tmp_path / "missing.json", run_direct=False,
                              api_base_url=None, api_timeout=1.0, api_token_env="NO_TOKEN",
                              api_site_id=None, execute_local_test=False)
    report = run_comparison(args)
    assert report["fixture_count"] == 50
    assert report["direct_falkordb"]["status"] == "BLOCKED"
    assert report["kairos_api"]["status"] == "BLOCKED"
    assert report["kairos_api"]["scenarios_executed"] == 0


def test_network_failure_timeout_invalid_json_and_http_rejection() -> None:
    transport = HTTPTransport("http://127.0.0.1:8000", 0.1)
    for failure in (URLError("offline"), TimeoutError("slow"), HTTPError("url", 401, "denied", {}, None)):
        with patch.object(transport._opener, "open", side_effect=failure), pytest.raises(KairosAPIError):
            transport("GET", "/auth/me", None, "test-token")

    class BadResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b"not-json"

    with patch.object(transport._opener, "open", return_value=BadResponse()), pytest.raises(KairosAPIError, match="invalid JSON"):
        transport("GET", "/auth/me", None, "test-token")


def test_remote_api_origin_rejected() -> None:
    for url in ("https://127.0.0.1:8000", "http://example.com", "http://127.0.0.1:8000/admin"):
        with pytest.raises(ValueError):
            require_loopback(url)
