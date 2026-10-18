"""Compare measured direct FalkorDB results with verified Kairos API traversal results."""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from adapters.kairos_api import (
    HTTPTransport,
    KairosAPIAdapter,
    KairosAPIError,
    compatibility,
)
from graph_client import connect_falkordb, validate_test_uri
from oracle import validate_fixture_document

from benchmark import (
    DEFAULT_FIXTURE_PATH,
    DEFAULT_REPORT_PATH,
    _latency_summary,
    _score_decisions,
    run_benchmark,
)

BASE = Path(__file__).resolve().parent
DEFAULT_API_REPORT = BASE / "reports" / "kairos-api-evaluation.json"
DEFAULT_COMPARISON = BASE / "reports" / "comparison.md"


def _empty_api(reason: str, scenarios: list[dict[str, Any]], status: str = "BLOCKED") -> dict[str, Any]:
    return {
        "status": status, "reason": reason, "scenarios_executed": 0,
        "decision_metrics": None, "request_latency_ms": None,
        "memory_validity": {"status": "UNSUPPORTED", "correct": None, "checked": 0},
        "tenant_isolation": {"status": "NOT_RUN", "checked": 0},
        "scenario_results": [
            {"scenario_id": item["scenario_id"], "scenario_type": item["scenario_type"],
             **compatibility(item), "executed": False}
            for item in scenarios
        ],
    }


def _run_api(args: argparse.Namespace, scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    if not args.api_base_url:
        return _empty_api("A dedicated local Kairos API origin, site-bound test token, EDB_BENCH_ site, and disposable graph store were not configured.", scenarios)
    try:
        transport = HTTPTransport(args.api_base_url, args.api_timeout)
    except ValueError as exc:
        return _empty_api(str(exc), scenarios)
    token = os.environ.get(args.api_token_env)
    if not token or not args.api_site_id:
        return _empty_api(f"Set {args.api_token_env} and --api-site-id for the site-bound test identity.", scenarios)
    try:
        adapter = KairosAPIAdapter(transport, token, args.api_site_id)
        identity = adapter.preflight()
    except (KairosAPIError, ValueError) as exc:
        return _empty_api(f"API preflight failed: {exc}", scenarios)
    if not args.execute_local_test:
        report = _empty_api("Authenticated contract preflight succeeded; writes require --execute-local-test and dedicated-local-test gate.", scenarios, "DRY_RUN")
        report["verified_test_identity"] = identity
        return report
    if not args.dedicated_local_test or os.environ.get("KAIROS_BENCH_DEDICATED_LOCAL_TEST") != "YES":
        return _empty_api("Write gate requires --dedicated-local-test and KAIROS_BENCH_DEDICATED_LOCAL_TEST=YES.", scenarios)
    if not args.api_falkordb_url or not args.api_graph_prefix:
        return _empty_api("Write gate requires the API's dedicated local FalkorDB URL and configured graph prefix.", scenarios)
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", args.api_graph_prefix):
        return _empty_api("API graph prefix is invalid.", scenarios)
    try:
        validate_test_uri(args.api_falkordb_url)
    except ValueError as exc:
        return _empty_api(str(exc), scenarios)

    graph_name = f"{args.api_graph_prefix}__{args.api_site_id}"
    client = None
    graph_was_absent = False
    report = _empty_api("Kairos evaluation did not finish.", scenarios)
    actual: dict[str, set[str]] = {}
    try:
        client = connect_falkordb(args.api_falkordb_url)
        baseline = set(client.list_graphs())
        if baseline:
            raise KairosAPIError("Dedicated local FalkorDB contains existing graphs; refusing writes")
        graph_was_absent = graph_name not in baseline
        eligible = [item for item in scenarios if compatibility(item)["status"] == "SUPPORTED_IMPACT_ONLY"]
        latencies: list[float] = []
        impacts: dict[str, Any] = {}
        for scenario in eligible:
            known = adapter.load_scenario(scenario)
            graphs_now = set(client.list_graphs())
            if graphs_now != {graph_name}:
                raise KairosAPIError("API wrote to a graph other than the declared dedicated test graph")
            result = adapter.evaluate(scenario, known)
            actual[scenario["scenario_id"]] = set(result.affected_decisions)
            latencies.append(result.latency_ms)
            impacts[scenario["scenario_id"]] = result
        decision_metrics = _score_decisions(eligible, actual)
        duplicate_cases = [item for item in eligible if item["scenario_type"] == "duplicate_events"]
        stable = 0
        for item in duplicate_cases:
            graph = client.select_graph(graph_name)
            counts_before = (
                graph.ro_query("MATCH (n) RETURN count(n)").result_set[0][0],
                graph.ro_query("MATCH ()-[r]->() RETURN count(r)").result_set[0][0],
            )
            known = adapter.load_scenario(item)  # replay the same upserts, not just a read
            repeated = adapter.evaluate(item, known)
            counts_after = (
                graph.ro_query("MATCH (n) RETURN count(n)").result_set[0][0],
                graph.ro_query("MATCH ()-[r]->() RETURN count(r)").result_set[0][0],
            )
            stable += counts_before == counts_after and repeated.affected_decisions == impacts[item["scenario_id"]].affected_decisions
        tenant = {"status": "NOT_RUN", "checked": 0, "reason": "Second site-bound test token not supplied."}
        foreign_token = os.environ.get(args.foreign_token_env)
        if foreign_token:
            denied = adapter.check_foreign_site_denial(foreign_token)
            tenant = {"status": "PASS" if denied else "FAIL", "checked": 1, "foreign_site_denied": denied}
        decision_ok = decision_metrics["missed_invalidations"] == decision_metrics["false_invalidations"] == 0
        report = {
            "status": "PARTIAL" if decision_ok and stable == len(duplicate_cases) and tenant["status"] != "FAIL" else "FAIL",
            "reason": "Only generic impact reachability is comparable; Kairos does not expose arbitrary fixture validity states.",
            "verified_test_identity": identity, "site_id": args.api_site_id,
            "scenarios_executed": len(eligible), "decision_metrics": decision_metrics,
            "request_latency_ms": _latency_summary(latencies),
            "memory_validity": {"status": "UNSUPPORTED", "correct": None, "checked": 0},
            "tenant_isolation": tenant,
            "duplicate_stability": {"scope": "generic graph upsert replay, not evidence-event idempotency",
                                    "status": "PASS" if stable == len(duplicate_cases) else "FAIL",
                                    "stable": stable, "checked": len(duplicate_cases)},
            "scenario_results": [
                {"scenario_id": item["scenario_id"], "scenario_type": item["scenario_type"],
                 **compatibility(item), "executed": item["scenario_id"] in actual,
                 "affected_decisions": sorted(actual[item["scenario_id"]]) if item["scenario_id"] in actual else None}
                for item in scenarios
            ],
        }
    except (KairosAPIError, ValueError, OSError, TimeoutError) as exc:
        report = _empty_api(f"Local API evaluation stopped: {exc}", scenarios)
        report["scenarios_executed"] = len(actual)
        for item in report["scenario_results"]:
            item["executed"] = item["scenario_id"] in actual
    finally:
        if client is not None and graph_was_absent:
            try:
                remaining = set(client.list_graphs())
                if graph_name in remaining:
                    client.select_graph(graph_name).delete()
                    report["cleanup"] = "deleted_benchmark_graph"
                else:
                    report["cleanup"] = "graph_not_created"
                unknown = sorted(remaining - {graph_name})
                if unknown:
                    report["cleanup"] = "unknown_graph_left_untouched"
                    report["status"] = "FAIL"
                    report["reason"] += " Unexpected graph appeared in dedicated store and was left untouched."
            except Exception as exc:  # noqa: BLE001 - preserve cleanup failure in report
                report["cleanup"] = f"FAILED: {type(exc).__name__}"
                report["status"] = "FAIL"
        elif client is not None:
            report["cleanup"] = "no_owned_graph"
    return report


def _metric(value: Any) -> str:
    if value is None:
        return "—"
    return f"{value:.4f}" if isinstance(value, float) else str(value)


def comparison_markdown(report: dict[str, Any]) -> str:
    direct, api = report["direct_falkordb"], report["kairos_api"]
    dm, am = direct.get("decision_metrics") or {}, api.get("decision_metrics") or {}
    dl, al = direct.get("graph_traversal_latency_ms") or {}, api.get("request_latency_ms") or {}
    memory = direct.get("memory_metrics") or {}
    tenant = direct.get("cross_tenant_isolation") or {}
    memory_display = f"{memory['correct']}/{memory['scenario_count']}" if "correct" in memory else None
    tenant_display = f"{tenant['status']} ({tenant['passed']}/{tenant['checked']})" if "checked" in tenant else None
    rows = [
        ("Scenarios executed", direct.get("scenarios_executed"), api.get("scenarios_executed")),
        ("Correct invalidations / impact candidates", dm.get("correctly_identified_impacted_decisions"), am.get("correctly_identified_impacted_decisions")),
        ("Missed invalidations / impact candidates", dm.get("missed_invalidations"), am.get("missed_invalidations")),
        ("False invalidations / impact candidates", dm.get("false_invalidations"), am.get("false_invalidations")),
        ("Precision", dm.get("precision"), am.get("precision")),
        ("Recall", dm.get("recall"), am.get("recall")),
        ("p95 latency (ms)", dl.get("p95_ms"), al.get("p95_ms")),
        ("Memory validity", memory_display, None),
        ("Tenant isolation", tenant_display, (api.get("tenant_isolation") or {}).get("status")),
    ]
    table = "\n".join(f"| {name} | {_metric(left)} | {_metric(right)} |" for name, left, right in rows)
    supported = sum(item["status"] == "SUPPORTED_IMPACT_ONLY" for item in api["scenario_results"])
    return (
        "# Evidence Drift engine comparison\n\n"
        f"Generated from actual report data at {report['run_timestamp_utc']}. "
        f"Direct FalkorDB: **{direct['status']}**. Kairos API: **{api['status']}**.\n\n"
        "| Metric | Direct FalkorDB benchmark | Kairos actual API |\n|---|---:|---:|\n" + table + "\n\n"
        f"{supported} of {len(api['scenario_results'])} fixtures have a generic impact mapping. "
        "Kairos impact results are dependent reachability, not persisted decision invalidation. "
        "Memory and approval validity are unavailable for arbitrary fixtures.\n\n"
        f"API run detail: {api['reason']}\n"
    )


def run_comparison(args: argparse.Namespace) -> dict[str, Any]:
    document = json.loads(args.fixtures.read_text(encoding="utf-8"))
    validation = validate_fixture_document(document)
    if validation["status"] != "PASS":
        raise ValueError("Fixture oracle validation failed")
    if args.run_direct:
        direct_full = run_benchmark(argparse.Namespace(
            fixtures=args.fixtures, regenerate_fixtures=False, seed=document["seed"], count=len(document["scenarios"]),
            falkordb_url=args.falkordb_url, graph_name=None, allow_remote_test_db=False,
            keep_graph=False, kairos_api_url=None, api_timeout=args.api_timeout,
        ))
        args.direct_report.write_text(json.dumps(direct_full, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    elif args.direct_report.exists():
        direct_full = json.loads(args.direct_report.read_text(encoding="utf-8"))
    else:
        direct_full = {"falkordb": {"status": "BLOCKED", "reason": "No measured direct FalkorDB report exists."}}
    direct = dict(direct_full["falkordb"])
    if direct.get("status") == "PASS" and (direct_full.get("fixture_seed") != document["seed"] or direct_full.get("scenario_count") != len(document["scenarios"])):
        direct = {"status": "BLOCKED", "reason": "Direct report fixture seed/count differs from current fixtures."}
    direct["scenarios_executed"] = len(document["scenarios"]) if direct["status"] == "PASS" else 0
    api = _run_api(args, document["scenarios"])
    return {"run_timestamp_utc": datetime.now(UTC).isoformat(), "fixture_seed": document["seed"],
            "fixture_count": len(document["scenarios"]), "fixture_validation": validation["status"],
            "direct_falkordb": direct, "kairos_api": api,
            "scope": "Direct graph benchmark and actual Kairos API are separate measurements."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURE_PATH)
    parser.add_argument("--direct-report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--api-report", type=Path, default=DEFAULT_API_REPORT)
    parser.add_argument("--comparison", type=Path, default=DEFAULT_COMPARISON)
    parser.add_argument("--run-direct", action="store_true", help="Measure direct FalkorDB afresh")
    parser.add_argument("--falkordb-url", help="Dedicated local direct-benchmark instance")
    parser.add_argument("--api-base-url", help="Bare local Kairos origin, for example http://127.0.0.1:8000")
    parser.add_argument("--api-site-id", help="Pre-provisioned EDB_BENCH_ site assigned to test identity")
    parser.add_argument("--api-token-env", default="KAIROS_BENCH_TEST_TOKEN")
    parser.add_argument("--foreign-token-env", default="KAIROS_BENCH_FOREIGN_TEST_TOKEN")
    parser.add_argument("--api-timeout", type=float, default=10.0)
    parser.add_argument("--execute-local-test", action="store_true", help="Enable API fixture writes after safety preflight")
    parser.add_argument("--dedicated-local-test", action="store_true", help="Affirm API and DB are disposable local services")
    parser.add_argument("--api-falkordb-url", help="Exact dedicated local FalkorDB URL configured in Kairos API")
    parser.add_argument("--api-graph-prefix", help="Exact FALKORDB_GRAPH_PREFIX configured in Kairos API")
    args = parser.parse_args()
    report = run_comparison(args)
    args.api_report.parent.mkdir(parents=True, exist_ok=True)
    args.comparison.parent.mkdir(parents=True, exist_ok=True)
    args.api_report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    args.comparison.write_text(comparison_markdown(report), encoding="utf-8", newline="\n")
    print(f"Direct FalkorDB: {report['direct_falkordb']['status']}; Kairos API: {report['kairos_api']['status']}")
    print(f"Scenarios: {report['fixture_count']}; Kairos executed: {report['kairos_api']['scenarios_executed']}")
    print(f"Reports: {args.api_report} and {args.comparison}")
    return 1 if report["kairos_api"]["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
