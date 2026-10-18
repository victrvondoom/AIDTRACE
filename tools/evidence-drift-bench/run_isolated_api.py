"""Measure the actual Kairos drift routes via in-process ASGI and a fresh test graph."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from adapters.kairos_api import KairosAPIAdapter, KairosAPIError, compatibility
from compare_engines import comparison_markdown
from graph_client import connect_falkordb, validate_test_uri
from oracle import validate_fixture_document

from benchmark import (
    DEFAULT_FIXTURE_PATH,
    DEFAULT_REPORT_PATH,
    _latency_summary,
    _score_decisions,
)

BASE = Path(__file__).resolve().parent
DEFAULT_BACKEND = BASE.parent.parent.parent / "kairos-main" / "backend"
LIVE_REPORT = BASE / "reports" / "kairos-api-live-results.json"
EVALUATION_REPORT = BASE / "reports" / "kairos-api-evaluation.json"
COMPARISON_REPORT = BASE / "reports" / "real-api-comparison.md"
COMPARISON_LATEST = BASE / "reports" / "comparison.md"
SOURCE_FILES = (
    "api/routers/drift.py", "api/services/drift/store.py",
    "api/services/drift/engine.py", "api/services/drift/model.py",
)


def _source_hashes(backend: Path) -> dict[str, str]:
    return {name: hashlib.sha256((backend / name).read_bytes()).hexdigest() for name in SOURCE_FILES}


def _scenario_metrics(scenario: dict[str, Any], actual: set[str]) -> dict[str, Any]:
    expected = set(scenario["expected_affected_decisions"])
    tp, fp, fn = len(actual & expected), len(actual - expected), len(expected - actual)
    return {
        "true_positives": tp, "false_positives": fp, "false_negatives": fn,
        "precision": tp / (tp + fp) if tp + fp else (1.0 if not expected else 0.0),
        "recall": tp / (tp + fn) if tp + fn else 1.0,
    }


def _base_results(scenarios: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{
        "scenario_id": item["scenario_id"], "scenario_type": item["scenario_type"],
        "expected_impacts": item["expected_affected_decisions"],
        "expected_unaffected": item["expected_unaffected_decisions"],
        **compatibility(item), "compatibility_status": compatibility(item)["status"],
        "executed": False, "actual_api_impacts": None,
        "http_status": None, "latency_ms": None, "error": None,
        "true_positives": None, "false_positives": None, "false_negatives": None,
        "precision": None, "recall": None, "repeat_consistent": None,
    } for item in scenarios]


def run_live(fixtures: Path, backend: Path, db_url: str) -> dict[str, Any]:
    """Run source-verified handlers; retain per-case failures without inventing scores."""
    document = json.loads(fixtures.read_text(encoding="utf-8"))
    if document["seed"] != 98 or len(document["scenarios"]) != 50:
        raise ValueError("Live run requires the fixed 50-scenario seed-98 fixture")
    validation = validate_fixture_document(document)
    if validation["status"] != "PASS":
        raise ValueError("Independent fixture oracle validation failed")
    validate_test_uri(db_url)
    backend = backend.resolve()
    source_before = _source_hashes(backend)
    # Import after validating the test target; imported Kairos code is never edited.
    from adapters.kairos_asgi import (
        ASGIKairosTransport,
        create_isolated_app,
        new_isolated_names,
    )

    prefix, site, token = new_isolated_names()
    graph_name = f"{prefix}__{site}"
    scenarios = document["scenarios"]
    outcomes = _base_results(scenarios)
    by_id = {entry["scenario_id"]: entry for entry in outcomes}
    eligible = [item for item in scenarios if compatibility(item)["status"] == "SUPPORTED_IMPACT_ONLY"]
    actual_by_id: dict[str, set[str]] = {}
    latencies: list[float] = []
    repeat_passes = 0
    cleanup = "not_created"
    probe: dict[str, Any] = {}
    error: str | None = None
    nodes = edges = None
    client = connect_falkordb(db_url)
    if graph_name in client.list_graphs():
        raise RuntimeError("Fresh benchmark graph already exists; refusing to reuse it")
    try:
        app = create_isolated_app(backend, db_url, prefix, site, token)
        with ASGIKairosTransport(app) as transport:
            adapter = KairosAPIAdapter(transport, token, site)
            health = transport("GET", "/drift/health", None, token)
            probe["health"] = {"http_status": transport.last_status_code, **health}
            if health != {"reachable": True, "site_graph_exists": False}:
                raise KairosAPIError("Site graph must be absent and FalkorDB reachable before loading")
            # The source route order determines whether /impact/pure is reachable.
            pure = transport.client.post("/drift/impact/pure", json={"changed_ids": ["probe"]},
                                         headers={"Authorization": f"Bearer {token}"})
            probe["pure_impact"] = {"http_status": pure.status_code,
                                    "fixture_compatible": False,
                                    "reason": "Route accepts no fixture edges; /impact/{site_id} currently shadows /impact/pure."}
            denied = transport.client.post(f"/drift/impact/{site}", json={"changed_ids": []})
            foreign = transport.client.post("/drift/impact/EDB_BENCH_FOREIGN", json={"changed_ids": []},
                                            headers={"Authorization": f"Bearer {token}"})
            probe["authentication"] = {"without_token_status": denied.status_code,
                                       "foreign_site_status": foreign.status_code,
                                       "passed": denied.status_code == 401 and foreign.status_code == 403}
            empty = transport("POST", f"/drift/impact/{site}", {"changed_ids": ["EDB_BENCH_MISSING"]}, token)
            probe["empty_impact"] = {"http_status": transport.last_status_code,
                                     "passed": empty.get("impacted") == []}
            known_by_id: dict[str, set[str]] = {}
            for scenario in eligible:
                outcome = by_id[scenario["scenario_id"]]
                try:
                    known_by_id[scenario["scenario_id"]] = adapter.load_scenario(scenario)
                except (KairosAPIError, ValueError, OSError) as exc:
                    outcome.update(status="FAILED", http_status=transport.last_status_code, error=str(exc))
            if graph_name not in client.list_graphs():
                raise KairosAPIError("Expected benchmark-owned graph was not created")
            graph = client.select_graph(graph_name)
            nodes = int(graph.ro_query("MATCH (n) RETURN count(n)").result_set[0][0])
            edges = int(graph.ro_query("MATCH ()-[r]->() RETURN count(r)").result_set[0][0])
            for scenario in eligible:
                scenario_id = scenario["scenario_id"]
                if scenario_id not in known_by_id:
                    continue
                outcome = by_id[scenario_id]
                try:
                    result = adapter.evaluate(scenario, known_by_id[scenario_id])
                    actual = set(result.affected_decisions)
                    score = _scenario_metrics(scenario, actual)
                    outcome.update(status="PASSED" if score["false_positives"] == score["false_negatives"] == 0 else "FAILED",
                                   executed=True, actual_api_impacts=sorted(actual),
                                   http_status=transport.last_status_code,
                                   latency_ms=round(result.latency_ms, 4),
                                   **score)
                    if outcome["status"] == "FAILED":
                        outcome["error"] = "Impact set differs from independent fixture oracle"
                    actual_by_id[scenario_id] = actual
                    latencies.append(result.latency_ms)
                except (KairosAPIError, ValueError, OSError) as exc:
                    outcome.update(status="FAILED", http_status=transport.last_status_code, error=str(exc))
                    continue
                try:
                    repeated = adapter.evaluate(scenario, known_by_id[scenario_id])
                    consistent = repeated.affected_decisions == result.affected_decisions
                    outcome["repeat_consistent"] = consistent
                    repeat_passes += consistent
                    if not consistent:
                        outcome.update(status="FAILED", error="Repeated impact response changed")
                    if scenario["scenario_type"] == "duplicate_events":
                        before_counts = (nodes, edges)
                        adapter.load_scenario(scenario)
                        after_counts = (
                            int(graph.ro_query("MATCH (n) RETURN count(n)").result_set[0][0]),
                            int(graph.ro_query("MATCH ()-[r]->() RETURN count(r)").result_set[0][0]),
                        )
                        outcome["duplicate_link_stable"] = before_counts == after_counts
                        if before_counts != after_counts:
                            outcome.update(status="FAILED", error="Duplicate graph upsert changed counts")
                except (KairosAPIError, ValueError, OSError) as exc:
                    outcome.update(status="FAILED", repeat_consistent=False, error=f"Repeat or duplicate replay: {exc}")
    except (KairosAPIError, ImportError, OSError, RuntimeError, ValueError) as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            if graph_name in client.list_graphs():
                client.select_graph(graph_name).delete()
                cleanup = "deleted_benchmark_owned_graph"
        except Exception as exc:  # noqa: BLE001 - cleanup must be visible
            cleanup = f"FAILED: {type(exc).__name__}"

    executed = [item for item in eligible if item["scenario_id"] in actual_by_id]
    metrics = _score_decisions(executed, actual_by_id) if executed else None
    source_after = _source_hashes(backend)
    source_stable = source_before == source_after
    for entry in outcomes:
        if entry["status"] == "SUPPORTED_IMPACT_ONLY":
            entry.update(status="BLOCKED", error=error or "Compatible scenario was not reached")
    failed = sum(entry["status"] == "FAILED" for entry in outcomes)
    blocked = sum(entry["status"] == "BLOCKED" for entry in outcomes)
    status = "FAILED" if failed and not executed else "BLOCKED" if not executed else (
        "PASSED" if not failed and not blocked and metrics["missed_invalidations"] == metrics["false_invalidations"] == 0
        and repeat_passes == len(executed) and cleanup == "deleted_benchmark_owned_graph"
        and source_stable and all(check.get("passed", True) for check in probe.values()) else "FAILED"
    )
    return {
        "status": status, "reason": error,
        "evaluation_scope": "Actual Kairos drift router/store/engine impact reachability only; no decision, memory, or approval validity evaluation.",
        "transport": "in_process_ASGI_real_Kairos_router", "kairos_backend": str(backend),
        "source_sha256": source_before, "source_stable": source_stable,
        "fixture_seed": 98, "fixture_count": 50,
        "compatible_scenarios": len(eligible), "scenarios_executed": len(executed),
        "blocked_scenarios": blocked, "failed_scenarios": failed,
        "unsupported_scenarios": len(scenarios) - len(eligible),
        "decision_metrics": metrics, "request_latency_ms": _latency_summary(latencies) if latencies else None,
        "repeat_consistency": {"consistent": repeat_passes, "checked": len(executed),
                               "status": "PASSED" if repeat_passes == len(executed) and executed else "NOT_TESTED" if not executed else "FAILED"},
        "memory_validity": {"status": "UNSUPPORTED", "checked": 0},
        "approval_validity": {"status": "UNSUPPORTED", "checked": 0},
        "tenant_isolation": {"status": "PASSED" if probe.get("authentication", {}).get("passed") else "NOT_TESTED",
                             "scope": "router site_scope with in-process test identity; Supabase JWT and OPA middleware not evaluated",
                             "checked": 1 if probe.get("authentication") else 0},
        "graph_nodes": nodes, "graph_relationships": edges,
        "probes": probe, "cleanup": cleanup, "scenario_results": outcomes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURE_PATH)
    parser.add_argument("--kairos-backend", type=Path, default=DEFAULT_BACKEND)
    parser.add_argument("--falkordb-url", required=True, help="Local dedicated FalkorDB test instance")
    parser.add_argument("--direct-report", type=Path, default=DEFAULT_REPORT_PATH)
    args = parser.parse_args()
    api = run_live(args.fixtures, args.kairos_backend, args.falkordb_url)
    if args.direct_report.exists():
        prior = json.loads(args.direct_report.read_text(encoding="utf-8"))
        direct = dict(prior["falkordb"])
        if prior.get("fixture_seed") != 98 or prior.get("scenario_count") != 50:
            direct = {"status": "BLOCKED", "reason": "Direct report has different fixtures"}
        direct["scenarios_executed"] = 50 if direct.get("status") == "PASS" else 0
    else:
        direct = {"status": "BLOCKED", "scenarios_executed": 0, "reason": "No direct benchmark report"}
    report = {"run_timestamp_utc": datetime.now(UTC).isoformat(), "fixture_seed": 98,
              "fixture_count": 50, "direct_falkordb": direct, "kairos_api": api,
              "scope": "Actual Kairos impact API measurements are separate from direct FalkorDB traversal."}
    blob = json.dumps(report, indent=2, sort_keys=True) + "\n"
    for path in (LIVE_REPORT, EVALUATION_REPORT):
        path.write_text(blob, encoding="utf-8", newline="\n")
    markdown = comparison_markdown(report).replace("# Evidence Drift engine comparison", "# Real Kairos API comparison")
    for path in (COMPARISON_REPORT, COMPARISON_LATEST):
        path.write_text(markdown, encoding="utf-8", newline="\n")
    print(f"Kairos API: {api['status']}; executed {api['scenarios_executed']}/{api['compatible_scenarios']} compatible scenarios")
    print(f"Direct FalkorDB: {direct['status']}; cleanup: {api['cleanup']}")
    print(f"Report: {LIVE_REPORT}")
    return 0 if api["status"] == "PASSED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
