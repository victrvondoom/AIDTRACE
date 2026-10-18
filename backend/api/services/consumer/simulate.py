"""What-if verification in isolated graphs.

A hypothesis is applied to a fresh resolve_sim_* graph that starts from the LIVE state of the consumer
graph. The sim graph is deleted afterwards. The live graph is never changed by a simulation.
"""
from api.services.consumer import case_data, graphdb, verifier

DECISION_TYPES = set(graphdb.DECISION_EDGE_TYPES)


def live_state(store) -> dict:
    """Read the live graph back as build_case() overrides, so a sim starts from exactly what the user sees."""
    ev_status = {r[0]: r[1] for r in store.query("MATCH (e:Evidence) RETURN e.id, e.status")}
    src_verified = {r[0]: bool(r[1]) for r in store.query("MATCH (s:Source) RETURN s.id, s.verified")}
    live_edges = {(r[0], r[1], r[2], r[3], r[4]) for r in store.query(
        "MATCH (a)-[r]->(b) WHERE type(r) IN $types "
        "RETURN labels(a)[0], a.id, type(r), labels(b)[0], b.id",
        {"types": graphdb.DECISION_EDGE_TYPES})}
    base_decision = [e for e in case_data.build_case({"add_sources": True})["edges"] if e[2] in DECISION_TYPES]
    dropped = [list(e) for e in base_decision if e not in live_edges]
    overrides = {"evidence_status": ev_status, "source_verified": src_verified, "drop_edges": dropped}
    if "SRC-7" in src_verified:
        overrides["add_sources"] = True
    return overrides


def merge(base: dict, change: dict) -> dict:
    merged = {"evidence_status": {**base.get("evidence_status", {}), **change.get("evidence_status", {})},
              "source_verified": {**base.get("source_verified", {}), **change.get("source_verified", {})},
              "drop_edges": base.get("drop_edges", []) + change.get("drop_edges", [])}
    if base.get("add_sources") or change.get("add_sources"):
        merged["add_sources"] = True
    return merged


def run_hypothesis(store, change: dict) -> list[dict]:
    """Verdicts after applying `change` to the live state, computed in a temporary isolated graph."""
    overrides = merge(live_state(store), change)
    sim = graphdb.open_store(graph_name=graphdb.new_sim_name(), url=store.url)
    try:
        graphdb.write_case(sim, case_data.build_case(overrides))
        return verifier.verify_all(verifier.load_facts(sim))
    finally:
        sim.reset_synthetic_graph()


def evidence_gap_ranking(store, live_verdicts: list[dict]) -> list[dict]:
    """Rank missing evidence and unverified sources by how many verdicts each would change."""
    live = {v["strategy_id"]: v for v in live_verdicts}
    candidates = [("evidence", r[0], r[1], {"evidence_status": {r[0]: "PRESENT"}})
                  for r in store.query("MATCH (e:Evidence) WHERE e.status <> 'PRESENT' RETURN e.id, e.type")]
    candidates += [("source", r[0], r[1], {"source_verified": {r[0]: True}})
                   for r in store.query("MATCH (s:Source) WHERE s.verified = false RETURN s.id, s.title")]
    ranked = []
    for kind, item_id, label, change in candidates:
        sim = {v["strategy_id"]: v for v in run_hypothesis(store, change)}
        changes = [{"strategy_id": sid, "from": live[sid]["verdict"], "to": sim[sid]["verdict"],
                    "domains": sim[sid]["domains"]}
                   for sid in sorted(live) if live[sid]["verdict"] != sim[sid]["verdict"]]
        note = []
        if kind == "source" and not changes:
            # Explain why verifying this source changed nothing: the reasons tied to its rules.
            note = [f"{v['strategy_id']}: {r}" for v in sim.values() for r in v["reasons"]
                    if any(r.startswith(f"{rid}:") for rid in v["unverified_rules"])][:3]
        domains = sorted({d for c in changes for d in c["domains"]})
        gain = sum(1 for c in changes if c["to"] == verifier.VERIFIED)
        ranked.append({"item_id": item_id, "kind": kind, "label": label, "changes": changes,
                       "verified_gain": gain, "domains": domains, "note": note})
    ranked.sort(key=lambda g: (-g["verified_gain"], -len(g["domains"]), g["item_id"]))
    return ranked
