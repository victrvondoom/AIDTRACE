"""Graph Lab algorithm tests: oracle comparisons, determinism and fail-closed behaviour."""
from __future__ import annotations

from itertools import combinations

import pytest

from api.services.drift.engine import DependencyEdge, find_impacted_dependents
from api.services.graphlab import algorithms as alg
from api.services.graphlab.registry import ALGORITHMS, SCENARIOS, E, N, evaluate_supply_chain, run_algorithm


def graph(name: str) -> alg.Graph:
    return alg.normalize_graph(SCENARIOS[name]["graph"])


def test_every_scenario_preset_runs_and_is_deterministic() -> None:
    for scenario in SCENARIOS.values():
        g = alg.normalize_graph(scenario["graph"])
        for preset in scenario["recommended"]:
            first = run_algorithm(preset["algorithm"], g, preset["params"])
            assert first == run_algorithm(preset["algorithm"], g, preset["params"])
            assert first["summary"] and "node_marks" in first and "edge_marks" in first


def test_supply_chain_evaluation_crosses_software_supplier_and_evidence_domains() -> None:
    first = evaluate_supply_chain()
    second = evaluate_supply_chain()
    assert first == second
    assert first["summary"] == {"cases": 6, "passed": 6, "failed": 0, "accuracy": 1.0, "verdict": "PASS"}
    cases = {case["id"]: case for case in first["cases"]}
    assert cases["settlement_conflict"]["actual"] == {"shortfall_units": 40, "hold_settlement": True}
    assert cases["evidence_gated_settlement"]["actual"] == "HOLD"
    assert cases["alternate_supplier_path"]["actual"] is True
    assert cases["counterfactual_supplier_isolation"]["actual"] is False
    assert cases["counterfactual_supplier_isolation"]["receipt"]["summary"]["verified"] is True


def test_blast_radius_matches_drift_engine_closure() -> None:
    g = graph("plant_evidence")
    result = run_algorithm("blast_radius", g, {"changed": ["sop-v1"], "direction": "reverse"})
    edges = [DependencyEdge(e["source"], e["target"], "logical") for e in g.edges]
    expected = {p.node_id: p.depth for p in find_impacted_dependents(["sop-v1"], edges)}
    assert {r["node"]: r["depth"] for r in result["findings"]} == expected
    assert "action-open-valve" in expected  # the pending action is reached through claim -> memory -> decision -> plan


def test_blast_radius_separates_definite_from_possible() -> None:
    marks = run_algorithm("blast_radius", graph("supply_chain"), {"changed": ["CVE-2026-1001"]})["node_marks"]
    assert marks["svc-gateway"] == marks["svc-billing"] == marks["team-payments"] == "impacted"
    assert marks["svc-reports"] == marks["job-nightly"] == "possible"  # reachable only through a 'maybe' edge


def brute_min_cut(g: alg.Graph, sources: list[str], targets: list[str]) -> float:
    ids = [i for i, e in enumerate(g.edges) if not e["disabled"]]
    best = float("inf")
    for k in range(len(ids) + 1):
        for subset in combinations(ids, k):
            cost = sum(g.edges[i]["weight"] for i in subset)
            if cost < best and not alg._reaches(g, sources, set(targets), set(subset), set()):
                best = cost
    return best


def test_min_cut_equals_brute_force_oracle_and_is_verified() -> None:
    g = graph("cloud_attack")
    sources, targets = ["internet", "phished-user"], ["customer-db"]
    result = run_algorithm("min_cut", g, {"sources": sources, "targets": targets})
    assert result["summary"]["verified"] is True and result["summary"]["residual_path_exists"] is False
    assert result["summary"]["cut_cost"] == pytest.approx(brute_min_cut(g, sources, targets))
    cut = {int(i) for i in result["edge_marks"]}
    assert not alg._reaches(g, sources, set(targets), cut, set())


def test_min_cut_node_mode_and_uncuttable_direct_link() -> None:
    g = graph("cloud_attack")
    nodes = run_algorithm("min_cut", g, {"sources": ["internet"], "targets": ["customer-db"], "mode": "nodes"})
    assert nodes["summary"]["verified"] is True and nodes["summary"]["cut_cost"] <= 3
    direct = alg.normalize_graph({"nodes": [N("a", "x"), N("b", "x")], "edges": [E("a", "b")]})
    out = run_algorithm("min_cut", direct, {"sources": ["a"], "targets": ["b"], "mode": "nodes"})
    assert out["summary"]["cut_possible"] is False and out["summary"]["verified"] is False


def test_min_cut_reports_already_isolated_and_rejects_overlap() -> None:
    g = graph("cloud_attack")
    assert run_algorithm("min_cut", g, {"sources": ["customer-db"], "targets": ["internet"]})["summary"]["already_isolated"] is True
    with pytest.raises(alg.GraphError):
        run_algorithm("min_cut", g, {"sources": ["internet"], "targets": ["internet"]})


def test_chokepoint_is_the_single_node_on_every_path() -> None:
    found = run_algorithm("chokepoints", graph("cloud_attack"), {"sources": ["internet", "phished-user"], "targets": ["customer-db"]})
    assert [f["node"] for f in found["findings"]] == ["iam-role-app"]


def test_cycles_find_the_ring_and_the_innocent_pair() -> None:
    result = run_algorithm("cycles", graph("fraud_ring"), {"max_length": 5})
    by_nodes = {tuple(r["nodes"]): r for r in result["findings"]}
    assert by_nodes[("acct-101", "acct-102", "acct-103", "acct-104")]["min_weight"] == pytest.approx(9.2)
    assert by_nodes[("acct-401", "acct-402")]["min_weight"] == pytest.approx(0.3)
    assert sorted(len(r) for r in result["rings"]) == [2, 4]
    assert not any("acct-300" in r["nodes"] for r in result["findings"])


def test_communities_group_the_ring_and_rank_hubs() -> None:
    result = run_algorithm("communities", graph("fraud_ring"), {})
    marks = result["node_marks"]
    assert len({marks[a] for a in ("acct-101", "acct-102", "acct-103", "acct-104")}) == 1
    assert marks["acct-401"] != marks["acct-101"]
    assert sum(result["node_metric"].values()) == pytest.approx(1.0, abs=1e-3)


def test_as_of_reconstructs_historical_ownership() -> None:
    g = graph("supply_chain")
    past = run_algorithm("as_of", g, {"at": "2025-06-01T00:00:00Z"})
    now = run_algorithm("as_of", g, {"at": "2026-06-01T00:00:00Z"})
    owner = lambda r: {f["asset"]: f["owner"] for f in r["findings"]}["svc-reports"]  # noqa: E731
    assert owner(past) == "team-platform" and owner(now) == "team-payments"
    assert past["summary"]["hidden_edges"] == 1


def test_decision_gate_never_proceeds_without_evidence() -> None:
    g = graph("plant_evidence")
    now = "2026-10-18T00:00:00Z"
    hold = run_algorithm("decision_gate", g, {"decision": "decision-restart-pump", "required_types": ["claim"], "now": now})
    blocker_nodes = {finding["node"] for finding in hold["findings"] if "node" in finding}
    assert hold["summary"]["verdict"] == "HOLD" and blocker_nodes >= {"claim-torque-v1", "cal-cert-old"}
    review = run_algorithm("decision_gate", g, {"decision": "decision-isolate-line", "required_types": ["claim", "inspection"], "now": now})
    assert review["summary"]["verdict"] == "REVIEW"
    missing = run_algorithm("decision_gate", g, {"decision": "decision-isolate-line", "required_types": ["witness"], "now": now})
    assert missing["summary"]["verdict"] == "INSUFFICIENT_EVIDENCE"
    bare = alg.normalize_graph({"nodes": [N("d", "decision")], "edges": []})
    assert run_algorithm("decision_gate", bare, {"decision": "d"})["summary"]["verdict"] == "INSUFFICIENT_EVIDENCE"


def test_decision_gate_proceeds_only_when_everything_is_current_and_verified() -> None:
    g = alg.normalize_graph({"nodes": [N("d", "decision"), N("e", "claim", status="CURRENT", verification="VERIFIED")], "edges": [E("d", "e")]})
    assert run_algorithm("decision_gate", g, {"decision": "d", "required_types": ["claim"]})["summary"]["verdict"] == "PROCEED"
    stale = alg.normalize_graph({"nodes": [N("d", "decision"), N("e", "claim", status="SUPERSEDED")], "edges": [E("d", "e")]})
    assert run_algorithm("decision_gate", stale, {"decision": "d"})["summary"]["verdict"] == "HOLD"


def test_contamination_weights_dependence() -> None:
    result = run_algorithm("contamination", graph("claim_graph"), {"retracted": ["paper-A"], "flag_at": 0.25})
    scores = {r["node"]: r["contamination"] for r in result["findings"]}
    assert scores["paper-B"] == pytest.approx(0.75) and scores["paper-D"] == pytest.approx(0.375) and scores["paper-F"] == pytest.approx(0.0938, abs=1e-3)
    assert result["summary"]["flagged"] == 2 and "paper-C" not in scores


def test_claim_verdict_ignores_retracted_evidence() -> None:
    g = graph("claim_graph")
    result = run_algorithm("claim_verdict", g, {"claim": "claim-X"})
    assert result["summary"]["verdict"] == "SUPPORTED" and result["summary"]["support"] == pytest.approx(1.6)
    assert result["summary"]["refute"] == pytest.approx(0.6)
    assert run_algorithm("claim_verdict", g, {"claim": "paper-A"})["summary"]["verdict"] == "UNVERIFIED"


def test_route_detours_around_disruption_and_never_guesses() -> None:
    result = run_algorithm("route", graph("transit"), {"source": "stn-north", "target": "stn-airport"})
    assert result["summary"]["baseline_cost"] == 10 and result["summary"]["cost"] == 18 and result["summary"]["detour_cost"] == 8
    blocked = run_algorithm("route", graph("transit"), {"source": "stn-north", "target": "stn-airport", "avoid": ["stn-campus"]})
    assert blocked["summary"]["reachable"] is False and blocked["summary"]["cost"] is None


@pytest.mark.parametrize("payload", [
    {"nodes": [{"id": "a"}, {"id": "a"}], "edges": []},
    {"nodes": [{"id": "a"}], "edges": [{"source": "a", "target": "missing"}]},
    {"nodes": [{"id": "../etc"}], "edges": []},
    {"nodes": [{"id": "a"}], "edges": [{"source": "a", "target": "a", "certainty": "sure"}]},
    {"nodes": [{"id": "a"}], "edges": [{"source": "a", "target": "a", "weight": -1}]},
    {"nodes": [{"id": "a"}], "edges": [{"source": "a", "target": "a", "at": "yesterday"}]},
    {"nodes": [{"id": f"n{i}"} for i in range(alg.MAX_NODES + 1)], "edges": []},
    "not a graph",
])
def test_normalize_rejects_untrusted_input(payload) -> None:
    with pytest.raises(alg.GraphError):
        alg.normalize_graph(payload)


def test_registry_is_complete() -> None:
    assert len(ALGORITHMS) == 10
    for spec in (a.spec() for a in ALGORITHMS.values()):
        assert spec["sources"] and spec["summary"]
    with pytest.raises(alg.GraphError):
        run_algorithm("nope", graph("transit"), {})
