"""Scenario evaluation: RESOLVE AI (graph) versus the checklist baseline, on synthetic cases.

Run:  python -m app.consumer.evaluate          (writes ../docs/evaluation.json and prints a table)

Expected outcomes are written by hand from the fixture rules. They are NOT copied from the verifier,
so a wrong verifier shows up as a mismatch here. Numbers are whatever this run produces; nothing is
pre-filled or estimated.
"""
import json
import time
from pathlib import Path

from api.services.consumer import baseline, case_data, engine, graphdb

EVAL_GRAPH = "resolve_eval"
OUT = Path(__file__).resolve().parents[3] / "docs" / "evaluation.json"

A, B, C, D = "STR-A", "STR-B", "STR-C", "STR-D"
V, R, I = "VERIFIED", "REJECTED", "INSUFFICIENT_EVIDENCE"  # noqa: E741

SCENARIOS = [
    {"id": "S1", "title": "Base case: carrier cancellation notice missing",
     "overrides": {}, "expected": {A: R, B: I, C: I, D: I},
     "expected_plan": "NO_VERIFIED_STRATEGY", "expected_draft": None, "expected_conflicts": 1},
    {"id": "S2", "title": "Notice attached (EVD-2 present)",
     "overrides": {"evidence_status": {"EVD-2": "PRESENT"}}, "expected": {A: R, B: V, C: I, D: V},
     "expected_plan": "NEEDS_USER_DECISION", "expected_draft": B, "expected_conflicts": 1},
    # B is REJECTED here, not VERIFIED: without the REFUNDS link, the amended claim (460) is also
    # contradicted, because the graph now expects 700. The first label written for this case was wrong.
    {"id": "S3", "title": "Data error: REFUNDS link from refund statement to ticket removed",
     "overrides": {"evidence_status": {"EVD-2": "PRESENT"},
                   "drop_edges": [["Evidence", "EVD-3", "REFUNDS", "Evidence", "EVD-1"]]},
     "expected": {A: V, B: R, C: I, D: V},
     "expected_plan": "NEEDS_USER_DECISION", "expected_draft": A, "expected_conflicts": 1},
    {"id": "S4", "title": "Contradictory verified insurer FAQ added",
     "overrides": {"evidence_status": {"EVD-2": "PRESENT"}, "add_sources": True},
     "expected": {A: R, B: I, C: I, D: V},
     "expected_plan": "READY_FOR_REVIEW", "expected_draft": D, "expected_conflicts": 1},
    {"id": "S5", "title": "Airline source flagged verified, but its excerpt is a placeholder",
     "overrides": {"evidence_status": {"EVD-2": "PRESENT"}, "source_verified": {"SRC-4": True}},
     "expected": {A: R, B: V, C: I, D: V},
     "expected_plan": "NEEDS_USER_DECISION", "expected_draft": B, "expected_conflicts": 1},
]


def _graph_scenario(sc: dict) -> tuple[dict, dict]:
    store = graphdb.open_store(graph_name=EVAL_GRAPH)
    try:
        graphdb.write_case(store, case_data.build_case(sc["overrides"]))
        ours = engine.analyze(store, run_id=f"EVAL-{sc['id']}")
        base = baseline.run(store)
    finally:
        store.reset_synthetic_graph()
    return ours, base


def _score(sc: dict, ours: dict, base: dict) -> dict:
    expected = sc["expected"]
    our_pred = {v["strategy_id"]: v["verdict"] for v in ours["verdicts"]}
    base_pred = {s: (V if s in base["recommended"] else "NOT_RECOMMENDED") for s in expected}
    surfaced = set(ours["plan"]["verified"])
    unsupported_base = [s for s in base["recommended"] if expected[s] != V]
    return {
        "verdicts": our_pred,
        "plan_status": ours["plan"]["status"],
        "draft": ours["plan"]["draft_strategy_id"],
        "ours": {
            "verdict_accuracy": sum(our_pred[s] == expected[s] for s in expected) / len(expected),
            "plan_matches_expected": ours["plan"]["status"] == sc["expected_plan"]
                                     and ours["plan"]["draft_strategy_id"] == sc["expected_draft"],
            "unsupported_recommendations": sum(1 for s in surfaced if expected[s] != V),
            "conflicts_found": len(ours["cross_domain"]["conflicts"]),
            "conflicts_expected": sc["expected_conflicts"],
            "evidence_gaps_ranked": len(ours["evidence_gaps"]),
            "shared_cross_domain_evidence": len(ours["cross_domain"]["shared_evidence"]),
            "independent_check_agrees": ours["independent_check"]["agrees"],
            "elapsed_ms": ours["elapsed_ms"],
        },
        "baseline": {
            "recommended": base["recommended"],
            "verdict_accuracy": sum((base_pred[s] == V) == (expected[s] == V) for s in expected) / len(expected),
            "unsupported_recommendations": len(unsupported_base),
            "unsupported_blocked_by_graph": sum(1 for s in unsupported_base if s not in surfaced),
            "conflicts_found": base["conflicts_found"],
            "evidence_gaps_ranked": base["evidence_gaps_ranked"],
        },
    }


def _unavailable_scenario() -> dict:
    started = time.perf_counter()
    try:
        graphdb.open_store(graph_name=EVAL_GRAPH, port=6399)
        status = "UNEXPECTED: store opened"
    except graphdb.GraphUnavailable:
        status = "GRAPH_UNAVAILABLE"
    return {"id": "S6", "title": "FalkorDB unreachable",
            "ours": {"status": status, "decision": None,
                     "elapsed_ms": round((time.perf_counter() - started) * 1000, 1)},
            "baseline": {"output": "not run: the checklist also reads the graph, so there is no output"}}


def main() -> None:
    rows, detail = [], []
    for sc in SCENARIOS:
        ours, base = _graph_scenario(sc)
        score = _score(sc, ours, base)
        detail.append({"id": sc["id"], "title": sc["title"], "expected_verdicts": sc["expected"],
                       "expected_plan": sc["expected_plan"], "expected_draft": sc["expected_draft"],
                       **score})
        rows.append((sc["id"], score["ours"]["verdict_accuracy"], score["baseline"]["verdict_accuracy"],
                     score["ours"]["plan_matches_expected"], score["ours"]["unsupported_recommendations"],
                     score["baseline"]["unsupported_recommendations"], score["ours"]["conflicts_found"],
                     score["baseline"]["conflicts_found"], score["ours"]["evidence_gaps_ranked"],
                     score["ours"]["elapsed_ms"]))
    detail.append(_unavailable_scenario())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"scenarios": detail}, indent=2, default=str))

    header = ("id", "acc graph", "acc checklist", "plan ok", "unsup graph", "unsup checklist",
              "conflicts graph", "conflicts checklist", "gaps graph", "ms graph")
    print(" | ".join(header))
    for r in rows:
        print(" | ".join(f"{x:.2f}" if isinstance(x, float) else str(x) for x in r))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
