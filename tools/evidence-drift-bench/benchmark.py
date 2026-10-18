"""Validate fixture oracles and benchmark isolated FalkorDB traversals."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import statistics
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from adapters.http_json import HttpJsonEvidenceDriftAdapter
from generate_fixtures import write_fixtures
from graph_client import FalkorGraphRunner, connect_falkordb
from oracle import validate_fixture_document

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_FIXTURE_PATH = PACKAGE_DIR / "fixtures" / "scenarios.json"
DEFAULT_REPORT_PATH = PACKAGE_DIR / "reports" / "benchmark-latest.json"
GRAPH_PREFIX = "EDB_TEST_"


def _score_decisions(
    scenarios: list[dict[str, Any]], actual_by_id: dict[str, set[str]]
) -> dict[str, Any]:
    true_positive = 0
    false_positive = 0
    false_negative = 0
    true_negative = 0
    decision_count = 0
    for scenario in scenarios:
        expected = set(scenario["expected_affected_decisions"])
        unaffected = set(scenario["expected_unaffected_decisions"])
        actual = actual_by_id[scenario["scenario_id"]]
        true_positive += len(actual & expected)
        false_positive += len(actual - expected)
        false_negative += len(expected - actual)
        true_negative += len(unaffected - actual)
        decision_count += len(expected | unaffected)
    predicted_positive = true_positive + false_positive
    actual_positive = true_positive + false_negative
    return {
        "correctly_identified_impacted_decisions": true_positive,
        "missed_invalidations": false_negative,
        "false_invalidations": false_positive,
        "true_negative_decisions": true_negative,
        "decision_count": decision_count,
        "precision": true_positive / predicted_positive if predicted_positive else 1.0,
        "recall": true_positive / actual_positive if actual_positive else 1.0,
    }


def _latency_summary(samples_ms: list[float]) -> dict[str, float | int]:
    if not samples_ms:
        return {"sample_count": 0, "mean_ms": 0.0, "p50_ms": 0.0, "p95_ms": 0.0, "max_ms": 0.0}
    ordered = sorted(samples_ms)
    p95_index = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * 0.95 + 0.5)))
    return {
        "sample_count": len(ordered),
        "mean_ms": round(statistics.fmean(ordered), 4),
        "p50_ms": round(statistics.median(ordered), 4),
        "p95_ms": round(ordered[p95_index], 4),
        "max_ms": round(ordered[-1], 4),
    }


def _score_memories(scenarios: list[dict[str, Any]], results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    correct = sum(
        results[scenario["scenario_id"]]["memory_valid"] is scenario["expected_memory_valid"]
        for scenario in scenarios
    )
    return {
        "correct": correct,
        "incorrect": len(scenarios) - correct,
        "scenario_count": len(scenarios),
        "accuracy": correct / len(scenarios) if scenarios else 1.0,
    }


def _cross_tenant_summary(
    scenarios: list[dict[str, Any]], results: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    checks = []
    for scenario in scenarios:
        if scenario["scenario_type"] != "cross_tenant_isolation":
            continue
        nodes = {node["id"]: node for node in scenario["nodes"]}
        foreign_ids = {
            decision_id
            for decision_id in scenario["expected_unaffected_decisions"]
            if nodes[decision_id]["tenant_id"] != scenario["tenant_id"]
        }
        leaked = foreign_ids & set(results[scenario["scenario_id"]]["affected_decisions"])
        checks.append({"scenario_id": scenario["scenario_id"], "isolated": not leaked, "leaked_decisions": sorted(leaked)})
    passed = sum(check["isolated"] for check in checks)
    return {"status": "PASS" if passed == len(checks) else "FAIL", "passed": passed, "checked": len(checks), "cases": checks}


def _memory_summary(scenarios: list[dict[str, Any]], actual_results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return _score_memories(scenarios, actual_results)


def _api_summary(scenarios: list[dict[str, Any]], adapter: HttpJsonEvidenceDriftAdapter) -> dict[str, Any]:
    results: dict[str, set[str]] = {}
    normalized: dict[str, dict[str, Any]] = {}
    latencies: list[float] = []
    for scenario in scenarios:
        started = time.perf_counter_ns()
        result = adapter.evaluate(scenario)
        latencies.append((time.perf_counter_ns() - started) / 1_000_000)
        results[scenario["scenario_id"]] = set(result.affected_decisions)
        normalized[scenario["scenario_id"]] = {"memory_valid": result.memory_valid}
    return {
        "status": "PASS",
        "decision_metrics": _score_decisions(scenarios, results),
        "memory_metrics": _memory_summary(scenarios, normalized),
        "request_latency_ms": _latency_summary(latencies),
    }


def _load_fixture(path: Path, regenerate: bool, seed: int, count: int) -> dict[str, Any]:
    if regenerate:
        return write_fixtures(path, count=count, seed=seed)
    return json.loads(path.read_text(encoding="utf-8"))


def _graph_run(
    scenarios: list[dict[str, Any]],
    uri: str | None,
    graph_name: str | None,
    allow_remote: bool,
    keep_graph: bool,
) -> dict[str, Any]:
    if not uri:
        return {
            "status": "BLOCKED",
            "reason": "No FalkorDB URL was configured; set --falkordb-url or FALKORDB_URL.",
            "graph_name": None,
            "engine_evaluation": "NOT_RUN",
        }

    selected_name = graph_name or f"{GRAPH_PREFIX}{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:8]}"
    if not selected_name.startswith(GRAPH_PREFIX) or not selected_name.replace("_", "").isalnum():
        return {
            "status": "BLOCKED",
            "reason": f"Graph name must contain only letters, numbers, underscores and start with {GRAPH_PREFIX}.",
            "graph_name": selected_name,
            "engine_evaluation": "NOT_RUN",
        }

    client = None
    graph = None
    runner = None
    safe_to_cleanup = False
    evaluation: dict[str, dict[str, Any]] = {}
    latencies: list[float] = []
    graph_counts: dict[str, int] = {}
    cleanup_status = "not_created"
    try:
        client = connect_falkordb(uri, allow_remote=allow_remote)
        if selected_name in client.list_graphs():
            return {
                "status": "BLOCKED",
                "reason": "The requested graph already exists; refusing to write to an existing graph.",
                "graph_name": selected_name,
                "engine_evaluation": "NOT_RUN",
            }
        safe_to_cleanup = True
        server_info = client.connection.info("server")
        graph = client.select_graph(selected_name)
        runner = FalkorGraphRunner(graph)
        runner.load_scenarios(scenarios)
        graph_counts = runner.graph_counts()
        for scenario in scenarios:
            started = time.perf_counter_ns()
            evaluation[scenario["scenario_id"]] = runner.evaluate_scenario(scenario)
            latencies.append((time.perf_counter_ns() - started) / 1_000_000)

        duplicates = [scenario for scenario in scenarios if scenario["scenario_type"] == "duplicate_events"]
        counts_before_replay = runner.graph_counts()
        duplicate_results = []
        for scenario in duplicates:
            before = evaluation[scenario["scenario_id"]]
            runner.load_scenarios([scenario])
            after = runner.evaluate_scenario(scenario)
            duplicate_results.append(before == after)
            evaluation[scenario["scenario_id"]] = after
        counts_after_replay = runner.graph_counts()
        duplicate_stable = all(duplicate_results) and counts_before_replay == counts_after_replay

        decision_metrics = _score_decisions(
            scenarios,
            {scenario_id: set(result["affected_decisions"]) for scenario_id, result in evaluation.items()},
        )
        memory_metrics = _memory_summary(scenarios, evaluation)
        tenant_metrics = _cross_tenant_summary(scenarios, evaluation)
        graph_ok = (
            decision_metrics["missed_invalidations"] == 0
            and decision_metrics["false_invalidations"] == 0
            and memory_metrics["incorrect"] == 0
            and tenant_metrics["status"] == "PASS"
            and duplicate_stable
        )
        report = {
            "status": "PASS" if graph_ok else "FAIL",
            "graph_name": selected_name,
            "server_version": server_info.get("redis_version"),
            "graph_nodes": graph_counts["nodes"],
            "graph_relationships": graph_counts["relationships"],
            "decision_metrics": decision_metrics,
            "memory_metrics": memory_metrics,
            "graph_traversal_latency_ms": _latency_summary(latencies),
            "duplicate_event_stability": {
                "status": "PASS" if duplicate_stable else "FAIL",
                "stable_scenarios": sum(duplicate_results),
                "checked_scenarios": len(duplicates),
                "graph_counts_unchanged_after_replay": counts_before_replay == counts_after_replay,
            },
            "cross_tenant_isolation": tenant_metrics,
            "engine_evaluation": "NOT_RUN",
            "cleanup": "pending",
        }
    except Exception as exc:  # noqa: BLE001 - convert driver failures into an explicit blocked result.
        report = {
            "status": "BLOCKED",
            "reason": f"{type(exc).__name__}: FalkorDB connection or query did not complete.",
            "graph_name": selected_name,
            "engine_evaluation": "NOT_RUN",
            "graph_nodes": None,
            "graph_relationships": None,
        }
    finally:
        if client is not None:
            try:
                if safe_to_cleanup and selected_name in client.list_graphs():
                    if keep_graph:
                        cleanup_status = "kept_by_request"
                    else:
                        client.select_graph(selected_name).delete()
                        cleanup_status = "deleted"
            except Exception:  # noqa: BLE001 - report cleanup failure without hiding measured results.
                cleanup_status = "failed"
        if "report" in locals():
            report["cleanup"] = cleanup_status
            if cleanup_status == "failed" and report["status"] == "PASS":
                report["status"] = "FAIL"

    if "report" not in locals():
        return {"status": "BLOCKED", "reason": "FalkorDB did not return a result.", "graph_name": selected_name}
    return report


def run_benchmark(args: argparse.Namespace) -> dict[str, Any]:
    """Run fixture validation, graph measurements, and optional API evaluation."""
    fixture_path = args.fixtures
    document = _load_fixture(fixture_path, args.regenerate_fixtures, args.seed, args.count)
    scenarios = document["scenarios"]
    reference_validation = validate_fixture_document(document)
    if reference_validation["status"] != "PASS":
        raise ValueError(f"Fixture oracle validation failed: {reference_validation}")

    uri = args.falkordb_url or os.environ.get("FALKORDB_URL")
    graph_report = _graph_run(scenarios, uri, args.graph_name, args.allow_remote_test_db, args.keep_graph)
    adapter_report: dict[str, Any]
    if args.kairos_api_url:
        adapter = HttpJsonEvidenceDriftAdapter(
            args.kairos_api_url,
            bearer_token=os.environ.get("KAIROS_BENCH_BEARER_TOKEN"),
            timeout_seconds=args.api_timeout,
        )
        try:
            adapter_report = _api_summary(scenarios, adapter)
        except (RuntimeError, TypeError, ValueError, OSError) as exc:
            adapter_report = {
                "status": "BLOCKED",
                "reason": f"{type(exc).__name__}: configured Evidence Drift API did not complete.",
            }
    else:
        adapter_report = {"status": "NOT_RUN", "reason": "No Kairos API endpoint was configured."}

    statuses = (reference_validation["status"], graph_report["status"])
    overall_status = "PASS" if all(status == "PASS" for status in statuses) else (
        "FAIL" if "FAIL" in statuses else "BLOCKED"
    )
    if adapter_report["status"] not in {"NOT_RUN", "PASS"}:
        overall_status = "FAIL" if adapter_report["status"] == "FAIL" else "BLOCKED"
    return {
        "benchmark": "evidence-drift-bench",
        "status": overall_status,
        "run_timestamp_utc": datetime.now(UTC).isoformat(),
        "fixture_seed": document["seed"],
        "scenario_count": len(scenarios),
        "scenario_types": sorted({scenario["scenario_type"] for scenario in scenarios}),
        "runtime": {
            "python": platform.python_version(),
            "falkordb_client": importlib.metadata.version("falkordb"),
        },
        "fixture_reference_validation": reference_validation,
        "falkordb": graph_report,
        "kairos_engine": adapter_report,
        "evaluation_scope": "Fixture traversal correctness is separate from actual Kairos engine evaluation.",
    }


def _print_summary(report: dict[str, Any], report_path: Path) -> None:
    graph = report["falkordb"]
    sys.stdout.write(f"Benchmark status: {report['status']}\n")
    sys.stdout.write(
        f"Fixture oracle: {report['fixture_reference_validation']['status']} "
        f"({report['fixture_reference_validation']['scenario_checks_passed']}/{report['scenario_count']} scenarios)\n"
    )
    sys.stdout.write(f"FalkorDB: {graph['status']}\n")
    if graph.get("decision_metrics"):
        metrics = graph["decision_metrics"]
        latency = graph["graph_traversal_latency_ms"]
        sys.stdout.write(
            "Graph decisions: "
            f"correct={metrics['correctly_identified_impacted_decisions']} "
            f"missed={metrics['missed_invalidations']} false={metrics['false_invalidations']} "
            f"precision={metrics['precision']:.3f} recall={metrics['recall']:.3f}\n"
        )
        sys.stdout.write(
            f"Graph size: {graph['graph_nodes']} nodes, {graph['graph_relationships']} relationships; "
            f"traversal mean={latency['mean_ms']:.3f}ms p95={latency['p95_ms']:.3f}ms\n"
        )
        sys.stdout.write(
            f"Duplicate stability: {graph['duplicate_event_stability']['status']}; "
            f"tenant isolation: {graph['cross_tenant_isolation']['status']}\n"
        )
    elif graph.get("reason"):
        sys.stdout.write(f"FalkorDB detail: {graph['reason']}\n")
    sys.stdout.write(f"Kairos engine API: {report['kairos_engine']['status']}\n")
    sys.stdout.write(f"Report: {report_path}\n")


def main() -> int:
    """Parse command-line arguments and run the benchmark."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURE_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--regenerate-fixtures", action="store_true")
    parser.add_argument("--seed", type=int, default=98)
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--falkordb-url", help="Dedicated test instance URL; loopback only unless --allow-remote-test-db is set")
    parser.add_argument("--graph-name", help=f"Optional fresh graph name with required {GRAPH_PREFIX} prefix")
    parser.add_argument("--allow-remote-test-db", action="store_true", help="Allow a dedicated remote test FalkorDB instance")
    parser.add_argument("--keep-graph", action="store_true", help="Keep the newly created namespaced graph after the run")
    parser.add_argument("--kairos-api-url", help="Optional full URL for a compatible Kairos Evidence Drift JSON endpoint")
    parser.add_argument("--api-timeout", type=float, default=10.0)
    args = parser.parse_args()

    report = run_benchmark(args)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    _print_summary(report, args.report)
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
