"""Algorithm registry and synthetic scenarios for Graph Lab.

`sources` lists the research repositories whose README *describes* the same mechanism (a requirement
hypothesis, not a verified claim). Kairos implements each mechanism once, as a clean-room standard
algorithm in `algorithms.py`; nothing is copied from those repositories.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from . import algorithms as alg


@dataclass(frozen=True)
class Param:
    name: str
    kind: str  # node | nodes | int | number | select | datetime | tags
    label: str
    default: Any = None
    options: tuple[str, ...] = ()
    required: bool = False


@dataclass(frozen=True)
class Algorithm:
    id: str
    title: str
    summary: str
    run: Callable[[alg.Graph, dict], dict]
    params: tuple[Param, ...]
    sources: tuple[str, ...]
    test: str = "backend/tests/test_graphlab_algorithms.py"

    def spec(self) -> dict:
        return {"id": self.id, "title": self.title, "summary": self.summary, "test": self.test, "sources": list(self.sources),
                "params": [{"name": p.name, "kind": p.kind, "label": p.label, "default": p.default,
                            "options": list(p.options), "required": p.required} for p in self.params]}


_SRC_DST = (Param("sources", "nodes", "Entry points (sources)", required=True), Param("targets", "nodes", "Protected assets (targets)", required=True))

ALGORITHMS: dict[str, Algorithm] = {a.id: a for a in (
    Algorithm("blast_radius", "Blast radius & evidence drift",
              "Find every record that depends on a changed record, separating definite impact from possible impact (maybe-edges).",
              alg.blast_radius,
              (Param("changed", "nodes", "Changed records", required=True), Param("direction", "select", "Direction", "reverse", ("reverse", "forward")),
               Param("max_depth", "int", "Max depth", 12)),
              ("986036734/blastradius", "pintu544/blastradius", "Rakesh9742/blast-radius", "NishaadG/blastradius", "kushalkumarcs372/blast-radius",
               "sevenhiremath/blastradius", "AgentAhmed/blast-radius", "sahilposwal35-wq/patchpilot", "Shivansh1824/ExploitReach",
               "DevAnuragT/reachable", "Reet24-del/supply-chain-blast-radius", "estatic-coder/Graph_Hacks", "Suchit-2004/RepoSageAI",
               "HIZMALI/rippleproof-ai", "nightmoose/lineagegate", "KHARSHAVARDHAN-eng/CausalTrace-GraphHacks", "ProthamD/graph-hacks",
               "MaybeSomeone-arc18/patchpath", "kaushikkannan2/exploit-path")),
    Algorithm("min_cut", "Minimum-cost containment cut",
              "Cheapest edges or nodes to sever so no entry point reaches a protected asset, then verified by independent reachability.",
              alg.min_cut, (*_SRC_DST, Param("mode", "select", "Cut", "edges", ("edges", "nodes"))),
              ("YashSoni998265/interdict", "vivekonkarnathbharati/BreachGraph", "humidyfier/Fjord-Agent", "Aadrit555/we-make-devs-GRAPH_HACKS",
               "adiroy28852/PathGuard", "kishorekanth-blackhole/aegisgraph", "SaswatSRoy/ThreatPath", "sdkharade12/blast-shield-graph-hacks",
               "CARLEELTECH0/scout-falkordb", "murthyroshan/LastLift", "Manasi-Choudhari/Graph_Hacks")),
    Algorithm("chokepoints", "Chokepoints",
              "Single nodes that lie on every path from entry points to protected assets; fix or patch these first.",
              alg.chokepoints, _SRC_DST,
              ("kaushikkannan2/exploit-path", "adiroy28852/PathGuard", "Aadrit555/we-make-devs-GRAPH_HACKS", "SaswatSRoy/ThreatPath")),
    Algorithm("cycles", "Circular flows & rings",
              "Enumerate bounded loops (round-tripping money, swap loops) and strongly connected rings.",
              alg.cycles, (Param("max_length", "int", "Max loop length", 5), Param("min_length", "int", "Min loop length", 2)),
              ("akachi11/fraud-graph", "Manasa-L-Hegde/RingWatch", "ShaktiEighteen/Financial_Crime_Agent", "abhishiv17/Graph-hacks",
               "Mihir-Rabari/ledgerlens", "gagan-gag/FraudTrace-AI")),
    Algorithm("communities", "Communities, hubs & bridges",
              "Unlabeled community structure, PageRank hubs and bridge nodes for triage.",
              alg.communities, (),
              ("Manasi-Choudhari/Graph_Hacks", "priyanshu499/Scam-Graph-AI-", "Mike-Demo/gaming-multiverse-reasoner", "Sandeep-Hipparagi/NexusGraph",
               "jeeva5655/falkor-nexus", "Akshat-mohanty/Graph-Hacks")),
    Algorithm("as_of", "As-of time travel",
              "See which relationships were valid at a past moment, and who owned what then.",
              alg.as_of, (Param("at", "datetime", "As of"),),
              ("Noah-zipit/timetrace", "mahesh-mettireddy/FalkorTrace")),
    Algorithm("decision_gate", "Decision gate",
              "PROCEED / HOLD / REVIEW / INSUFFICIENT_EVIDENCE from the evidence a decision rests on; absence of evidence never proceeds.",
              alg.decision_gate, (Param("decision", "node", "Decision", required=True), Param("required_types", "tags", "Required evidence types")),
              ("Bhav-ikkk/GraphHacks", "kanchan0505/GraphHacks", "SharanyaRamSR/heatpath-hackathon", "maitreyaaaaa/official", "pinectar/clearance",
               "HusseinAdeiza/graphhacks-refusal-agent", "dharmikchandel/lineage", "AjaySingh-a/firstdomino", "adarsh-bhati/Safecortex",
               "manav-Mnv/hound-aml", "PranavRaam/rewire-falkordb-agent")),
    Algorithm("contamination", "Retraction contamination",
              "How much of each record rests on retracted evidence, weighted by dependence.",
              alg.contamination, (Param("retracted", "nodes", "Retracted records", required=True), Param("flag_at", "number", "Flag at", 0.25)),
              ("aryangorde6/shaky-ground", "ibnweb3/bedrock")),
    Algorithm("claim_verdict", "Claim verdict",
              "SUPPORTED / REFUTED / CONTESTED / UNVERIFIED from authority-weighted supporting and refuting evidence.",
              alg.claim_verdict, (Param("claim", "node", "Claim", required=True),),
              ("Sourabh-Kumar04/graph-hacks-verdict", "sivaratrisrinivas/pathflip", "divyashy20-boop/graph-hacks-2026")),
    Algorithm("route", "Disruption-aware routing",
              "Cheapest route that avoids disrupted nodes, with detour cost against the undisrupted baseline.",
              alg.route, (Param("source", "node", "From", required=True), Param("target", "node", "To", required=True), Param("avoid", "nodes", "Avoid")),
              ("london160771/StepFree", "aggarmoksh/GraphDispatch", "harshitdeora/lastmile", "mirah227/walletrace")),
)}


def run_algorithm(algorithm_id: str, graph: alg.Graph, params: dict) -> dict:
    if algorithm_id not in ALGORITHMS:
        raise alg.GraphError(f"unknown algorithm: {algorithm_id}")
    return ALGORITHMS[algorithm_id].run(graph, params if isinstance(params, dict) else {})


# ------------------------------------------------------------------------------------ scenarios
def N(id_: str, type_: str, label: str | None = None, **props: Any) -> dict:
    return {"id": id_, "type": type_, "label": label or id_, "props": props}


def E(source: str, target: str, rel: str = "LINKS", w: float = 1, **extra: Any) -> dict:
    return {"source": source, "target": target, "rel": rel, "weight": w, **extra}


def _supply_chain() -> dict:
    return {
        "nodes": [N("CVE-2026-1001", "advisory", "CVE-2026-1001 (parser RCE)", status="CONFIRMED", severity=9.8),
                  N("lib-parse", "package", "lib-parse 2.3.1", version="2.3.1", verification="VERIFIED"), N("lib-http", "package"),
                  N("lib-core", "package"), N("svc-gateway", "service", criticality=5), N("svc-billing", "service", criticality=5),
                  N("svc-reports", "service", criticality=2), N("svc-admin-ui", "service"), N("job-nightly", "job", "Nightly export job"),
                  N("team-platform", "team"), N("team-payments", "team"),
                  N("supplier-northstar", "supplier", "Northstar Components", verification="VERIFIED", lead_days=8),
                  N("supplier-altair", "supplier", "Altair Components", verification="VERIFIED", lead_days=5),
                  N("part-controller", "part", "Controller module", criticality=5),
                  N("po-204", "purchase_order", "PO-204 · 100 units", quantity=100, status="CURRENT"),
                  N("receipt-204", "receipt", "Receipt · 60 units", quantity=60, status="CURRENT", verification="VERIFIED"),
                  N("promise-204", "promise", "Supplier promise · 90 units", quantity=90, status="DISPUTED", verification="PENDING"),
                  N("alt-stock-88", "inventory", "Altair available stock · 50 units", quantity=50, status="CURRENT", verification="VERIFIED"),
                  N("plant-line-1", "plant", "Assembly line 1", criticality=5), N("incident-shortfall", "incident", "Controller shortfall", status="OPEN"),
                  N("decision-settle", "decision", "Settle PO-204"), N("decision-recover", "decision", "Recover line 1 supply"),
                  N("control-review", "control", "Human procurement approval", status="CURRENT", verification="VERIFIED")],
        "edges": [E("lib-parse", "CVE-2026-1001", "AFFECTED_BY"), E("lib-http", "lib-parse", "DEPENDS_ON"), E("lib-core", "lib-parse", "DEPENDS_ON"),
                  E("svc-gateway", "lib-http", "DEPENDS_ON"), E("svc-billing", "lib-core", "DEPENDS_ON"),
                  E("svc-reports", "lib-core", "DEPENDS_ON", certainty="maybe"), E("svc-admin-ui", "svc-gateway", "CALLS"),
                  E("job-nightly", "svc-reports", "CALLS"),
                  E("team-platform", "svc-gateway", "OWNS", at="2025-01-01T00:00:00Z"), E("team-payments", "svc-billing", "OWNS", at="2025-01-01T00:00:00Z"),
                  E("team-platform", "svc-reports", "OWNS", at="2024-06-01T00:00:00Z"), E("team-payments", "svc-reports", "OWNS", at="2026-02-01T00:00:00Z"),
                  E("part-controller", "supplier-northstar", "SOURCED_FROM"), E("part-controller", "supplier-altair", "ALTERNATE_SOURCE"),
                  E("po-204", "supplier-northstar", "ORDERED_FROM"), E("po-204", "part-controller", "ORDERS"),
                  E("receipt-204", "po-204", "RECEIVED_AGAINST"), E("promise-204", "po-204", "PROMISES_AGAINST"),
                  E("alt-stock-88", "supplier-altair", "HELD_BY"), E("supplier-altair", "alt-stock-88", "HAS_STOCK"),
                  E("alt-stock-88", "part-controller", "AVAILABLE_FOR"), E("part-controller", "plant-line-1", "FEEDS"),
                  E("incident-shortfall", "po-204", "TRIGGERED_BY"), E("incident-shortfall", "part-controller", "DISRUPTS"),
                  E("incident-shortfall", "receipt-204", "SUPPORTED_BY"), E("incident-shortfall", "promise-204", "CONFLICTS_WITH"),
                  E("decision-settle", "po-204", "RESOLVES"), E("decision-settle", "receipt-204", "RELIES_ON"),
                  E("decision-settle", "promise-204", "RELIES_ON"), E("decision-recover", "incident-shortfall", "RESOLVES"),
                  E("decision-recover", "alt-stock-88", "RELIES_ON"), E("decision-recover", "supplier-altair", "ROUTES_TO"),
                  E("decision-recover", "control-review", "REQUIRES_APPROVAL")],
    }


def _cloud_attack() -> dict:
    return {
        "nodes": [N("internet", "entry"), N("phished-user", "identity"), N("vpn-gw", "host"), N("web-vm", "host"), N("build-agent", "host"),
                  N("iam-role-app", "role", cost=3), N("iam-role-ci", "role", cost=2), N("secrets-store", "data", cost=4),
                  N("customer-db", "data", "Customer database"), N("audit-bucket", "data")],
        "edges": [E("internet", "web-vm", "EXPOSES", 4), E("internet", "vpn-gw", "EXPOSES", 6), E("phished-user", "vpn-gw", "LOGS_IN", 2),
                  E("vpn-gw", "build-agent", "REACHES", 3), E("web-vm", "iam-role-app", "ASSUMES", 2), E("build-agent", "iam-role-ci", "ASSUMES", 2),
                  E("iam-role-ci", "iam-role-app", "CAN_ASSUME", 5), E("iam-role-app", "secrets-store", "READS", 3),
                  E("secrets-store", "customer-db", "UNLOCKS", 2), E("iam-role-app", "customer-db", "READS", 6), E("build-agent", "audit-bucket", "WRITES", 1)],
    }


def _fraud_ring() -> dict:
    ring = ["acct-101", "acct-102", "acct-103", "acct-104"]
    return {
        "nodes": [N(a, "account") for a in [*ring, "acct-201", "acct-202", "acct-203", "acct-300", "acct-301", "acct-401", "acct-402", "acct-403"]],
        "edges": [E(ring[i], ring[(i + 1) % 4], "TRANSFER", [9.5, 9.4, 9.3, 9.2][i]) for i in range(4)]
                 + [E("acct-201", "acct-300", "TRANSFER", 4.9), E("acct-202", "acct-300", "TRANSFER", 4.8), E("acct-203", "acct-300", "TRANSFER", 4.9),
                    E("acct-300", "acct-301", "TRANSFER", 14.3), E("acct-301", "acct-101", "TRANSFER", 2.1),
                    E("acct-401", "acct-402", "TRANSFER", 0.4), E("acct-402", "acct-401", "TRANSFER", 0.3), E("acct-402", "acct-403", "TRANSFER", 0.2)],
    }


def _plant_evidence() -> dict:
    return {
        "nodes": [N("sop-v1", "document", "SOP rev 1", status="SUPERSEDED", version=1), N("sop-v2", "document", "SOP rev 2", status="CURRENT", version=2, verification="VERIFIED"),
                  N("claim-torque-v1", "claim", "Torque 40 Nm (rev 1)", status="SUPERSEDED"), N("claim-torque-v2", "claim", "Torque 55 Nm (rev 2)", status="CURRENT", verification="VERIFIED"),
                  N("memory-seal-history", "memory", "Agent memory: seal history"),
                  N("cal-cert-old", "calibration", "Torque wrench cert (expired)", expires_at="2026-01-01T00:00:00Z", status="CURRENT", verification="VERIFIED"),
                  N("cal-cert-new", "calibration", "Torque wrench cert (current)", expires_at="2027-06-01T00:00:00Z", status="CURRENT", verification="VERIFIED"),
                  N("inspection-17", "inspection", "Inspection report 17", status="CURRENT", verification="UNVERIFIED"),
                  N("decision-restart-pump", "decision", "Restart pump P-101"), N("plan-inspect", "plan", "Inspection plan"), N("action-open-valve", "action", "Open isolation valve"),
                  N("decision-isolate-line", "decision", "Isolate line 4", reviewed_digest="outdated-review")],
        "edges": [E("claim-torque-v1", "sop-v1", "EXTRACTED_FROM", at="2025-03-01T00:00:00Z", until="2026-03-01T00:00:00Z"),
                  E("claim-torque-v2", "sop-v2", "EXTRACTED_FROM", at="2026-03-01T00:00:00Z"),
                  E("memory-seal-history", "claim-torque-v1", "REMEMBERS", at="2025-04-01T00:00:00Z"),
                  E("decision-restart-pump", "memory-seal-history", "RELIES_ON", at="2025-05-01T00:00:00Z"), E("decision-restart-pump", "claim-torque-v1", "RELIES_ON", at="2025-05-01T00:00:00Z"),
                  E("decision-restart-pump", "cal-cert-old", "RELIES_ON", at="2025-05-01T00:00:00Z"), E("plan-inspect", "decision-restart-pump", "IMPLEMENTS", at="2025-05-02T00:00:00Z"),
                  E("action-open-valve", "plan-inspect", "EXECUTES", at="2025-05-03T00:00:00Z"),
                  E("decision-isolate-line", "claim-torque-v2", "RELIES_ON", at="2026-03-02T00:00:00Z"), E("decision-isolate-line", "inspection-17", "RELIES_ON", at="2026-03-02T00:00:00Z"),
                  E("decision-isolate-line", "cal-cert-new", "RELIES_ON", at="2026-03-02T00:00:00Z")],
    }


def _claim_graph() -> dict:
    return {
        "nodes": [N("paper-A", "paper", "Paper A (retracted)", status="RETRACTED"), N("paper-B", "paper"), N("paper-C", "paper"), N("paper-D", "paper"), N("paper-E", "paper"),
                  N("paper-F", "paper"), N("claim-X", "claim", "Compound X lowers blood pressure"),
                  N("study-1", "study", authority=90, status="CURRENT"), N("study-2", "study", authority=70, status="CURRENT"),
                  N("study-3", "study", authority=85, status="RETRACTED"), N("study-4", "study", authority=60, status="CURRENT")],
        "edges": [E("paper-B", "paper-A", "CITES", 3), E("paper-B", "paper-C", "CITES", 1), E("paper-D", "paper-B", "CITES", 2), E("paper-D", "paper-E", "CITES", 2),
                  E("paper-F", "paper-D", "CITES", 1), E("paper-F", "paper-E", "CITES", 3),
                  E("study-1", "claim-X", "SUPPORTS", 1), E("study-2", "claim-X", "SUPPORTS", 1), E("study-3", "claim-X", "REFUTES", 1), E("study-4", "claim-X", "REFUTES", 1)],
    }


def _transit() -> dict:
    stops = ["north", "market", "library", "stadium", "campus", "airport"]
    return {
        "nodes": [N(f"stn-{s}", "station", s.title(), disrupted=(s == "market")) for s in stops],
        "edges": [E("stn-north", "stn-market", "TRAIN", 4), E("stn-market", "stn-airport", "TRAIN", 6), E("stn-north", "stn-library", "TRAIN", 6),
                  E("stn-library", "stn-campus", "TRAIN", 5), E("stn-campus", "stn-airport", "TRAIN", 7), E("stn-market", "stn-stadium", "TRAIN", 3),
                  E("stn-stadium", "stn-airport", "BUS", 9)],
    }


SCENARIOS: dict[str, dict] = {
    "supply_chain": {"title": "Software supply chain", "description": "A vulnerable package, its dependents, uncertain links and accountable owners.",
                     "graph": _supply_chain(), "recommended": [
                         {"algorithm": "blast_radius", "params": {"changed": ["CVE-2026-1001"], "direction": "reverse"}},
                         {"algorithm": "as_of", "params": {"at": "2025-06-01T00:00:00Z"}}]},
    "cloud_attack": {"title": "Cloud attack paths", "description": "Identities and hosts that can reach a customer database; weights are the cost to sever a link.",
                     "graph": _cloud_attack(), "recommended": [
                         {"algorithm": "min_cut", "params": {"sources": ["internet", "phished-user"], "targets": ["customer-db"], "mode": "edges"}},
                         {"algorithm": "chokepoints", "params": {"sources": ["internet", "phished-user"], "targets": ["customer-db"]}}]},
    "fraud_ring": {"title": "Transfer network", "description": "Round-tripping accounts, a mule fan-in and an innocent pair; weights are amounts.",
                   "graph": _fraud_ring(), "recommended": [{"algorithm": "cycles", "params": {"max_length": 5}}, {"algorithm": "communities", "params": {}}]},
    "plant_evidence": {"title": "Plant evidence & decisions", "description": "SOP revisions, extracted claims, agent memory, decisions and a pending action.",
                       "graph": _plant_evidence(), "recommended": [
                           {"algorithm": "blast_radius", "params": {"changed": ["sop-v1"], "direction": "reverse"}},
                           {"algorithm": "decision_gate", "params": {"decision": "decision-restart-pump", "required_types": ["claim", "calibration"], "now": "2026-10-18T00:00:00Z"}},
                           {"algorithm": "decision_gate", "params": {"decision": "decision-isolate-line", "required_types": ["claim", "inspection"], "now": "2026-10-18T00:00:00Z"}}]},
    "claim_graph": {"title": "Citations & claims", "description": "A retracted paper with citing papers, and a claim with supporting and refuting studies.",
                    "graph": _claim_graph(), "recommended": [
                        {"algorithm": "contamination", "params": {"retracted": ["paper-A"], "flag_at": 0.25}},
                        {"algorithm": "claim_verdict", "params": {"claim": "claim-X"}}]},
    "transit": {"title": "Accessible transit", "description": "Stations with one disrupted interchange; weights are minutes.",
                "graph": _transit(), "recommended": [{"algorithm": "route", "params": {"source": "stn-north", "target": "stn-airport"}}]},
}


def evaluate_supply_chain() -> dict[str, Any]:
    """Run the integrated synthetic supply-chain evaluation with evidence and counterfactual receipts."""
    scenario = SCENARIOS["supply_chain"]
    graph = alg.normalize_graph(scenario["graph"])
    cases = []

    def record(case_id: str, expected: Any, actual: Any, receipt: dict[str, Any]) -> None:
        cases.append({"id": case_id, "expected": expected, "actual": actual, "pass": expected == actual, "receipt": receipt})

    impact = alg.blast_radius(graph, {"changed": ["CVE-2026-1001"], "direction": "reverse"})
    impacted = {row["node"]: row["certainty"] for row in impact["findings"]}
    record("vulnerability_reachability", {"svc-gateway": "definite", "svc-billing": "definite", "svc-reports": "possible"},
           {node: impacted.get(node) for node in ("svc-gateway", "svc-billing", "svc-reports")},
           {"engine": "blast_radius", "paths": impact["findings"], "hotspots": impact["hotspots"]})

    shortfall = graph.nodes["po-204"]["props"]["quantity"] - graph.nodes["receipt-204"]["props"]["quantity"]
    disputed = graph.nodes["promise-204"]["props"]["status"] == "DISPUTED"
    record("settlement_conflict", {"shortfall_units": 40, "hold_settlement": True},
           {"shortfall_units": shortfall, "hold_settlement": disputed},
           {"nodes": ["po-204", "receipt-204", "promise-204"], "relationships": ["ORDERS", "RECEIVED_AGAINST", "PROMISES_AGAINST", "CONFLICTS_WITH"]})

    route = alg.route(graph, {"source": "incident-shortfall", "target": "plant-line-1"})
    record("disruption_path", True, route["summary"]["reachable"], {"engine": "route", "summary": route["summary"], "path": route["findings"]})

    recovery = alg.route(graph, {"source": "supplier-altair", "target": "plant-line-1"})
    record("alternate_supplier_path", True, recovery["summary"]["reachable"],
           {"engine": "route", "summary": recovery["summary"], "path": recovery["findings"], "stock_receipt": "alt-stock-88"})

    gate = alg.decision_gate(graph, {"decision": "decision-settle", "required_types": ["purchase_order", "receipt", "promise"]})
    record("evidence_gated_settlement", "HOLD", gate["summary"]["verdict"], {"engine": "decision_gate", **gate})

    cut = alg.min_cut(graph, {"sources": ["supplier-northstar"], "targets": ["plant-line-1"], "mode": "edges"})
    record("counterfactual_supplier_isolation", False, cut["summary"].get("residual_path_exists"),
           {"engine": "min_cut", "summary": cut["summary"], "cut": cut["findings"]})

    passed = sum(case["pass"] for case in cases)
    return {"workflow": "kairos_supply_chain_evaluation", "scenario": "supply_chain", "data_class": "synthetic",
            "summary": {"cases": len(cases), "passed": passed, "failed": len(cases) - passed,
                        "accuracy": round(passed / len(cases), 4) if cases else 0, "verdict": "PASS" if passed == len(cases) else "REVIEW"},
            "cases": cases, "graph": graph.public(),
            "method": "Deterministic graph algorithms and explicit evidence rules; no model-generated labels or external writes."}


def scenario_list() -> list[dict]:
    return [{"id": k, "title": v["title"], "description": v["description"], "nodes": len(v["graph"]["nodes"]),
             "edges": len(v["graph"]["edges"]), "recommended": v["recommended"]} for k, v in SCENARIOS.items()]
