"""FalkorDB access for the consumer graph: opening it, writing cases, reading the evidence revision.

Nothing here falls back to another database. If FalkorDB is unreachable, open_store raises
GraphUnavailable and the engine returns a GRAPH_UNAVAILABLE result instead of a decision.
"""
import hashlib
import json
import os
import uuid

from api.services.consumer.store import GraphStore

CONSUMER_GRAPH = os.getenv("CONSUMER_GRAPH", "resolve_consumer")
SIM_PREFIX = "resolve_sim_"

# Relationship types that can change a verdict. Only these may be dropped by the demo mutation endpoint.
DECISION_EDGE_TYPES = ["INCLUDES", "REFUNDS", "CONTRADICTS", "REQUIRES_EVIDENCE", "GOVERNED_BY",
                       "CITES", "CONCERNS", "REQUIRES", "CLAIMS_RECOVERY_FOR", "PROPOSES"]


class GraphUnavailable(RuntimeError):
    """Raised when FalkorDB cannot be reached. Callers must not substitute another store."""


def _guard_name(graph_name: str) -> str:
    if not graph_name.startswith("resolve_"):
        raise ValueError(f"refusing to touch non-consumer graph '{graph_name}'")
    return graph_name


def open_store(graph_name: str = CONSUMER_GRAPH, url: str | None = None) -> GraphStore:
    _guard_name(graph_name)
    try:
        store = GraphStore(url=url or os.getenv("FALKORDB_URL", "redis://localhost:6379"), graph_name=graph_name)
    except Exception as exc:
        raise GraphUnavailable(f"FalkorDB unreachable: {type(exc).__name__}") from exc
    if not store.ping():
        raise GraphUnavailable("FalkorDB ping failed")
    return store


def write_case(store: GraphStore, case: dict) -> dict:
    """Replace the contents of this consumer graph with `case`. Only resolve_* graphs are allowed."""
    _guard_name(store.graph_name)
    store.reset_synthetic_graph()
    by_label: dict[str, list[dict]] = {}
    for label, props in case["nodes"]:
        by_label.setdefault(label, []).append(props)
    for label, rows in by_label.items():
        store.query(f"UNWIND $rows AS r CREATE (n:{label}) SET n = r", {"rows": rows})
    by_key: dict[tuple, list[dict]] = {}
    for sl, sid, rel, dl, did in case["edges"]:
        by_key.setdefault((sl, rel, dl), []).append({"a": sid, "b": did})
    for (sl, rel, dl), rows in by_key.items():
        store.query(
            f"UNWIND $rows AS r MATCH (a:{sl} {{id: r.a}}) MATCH (b:{dl} {{id: r.b}}) CREATE (a)-[:{rel}]->(b)",
            {"rows": rows})
    return {"nodes": len(case["nodes"]), "edges": len(case["edges"])}


def compute_revision(store: GraphStore) -> dict:
    """Hash of every fact a verdict depends on. An approval is bound to this value."""
    evidence = store.query("MATCH (e:Evidence) RETURN e.id, e.status, e.amount ORDER BY e.id")
    sources = store.query("MATCH (s:Source) RETURN s.id, s.verified, s.effective_date, s.excerpt ORDER BY s.id")
    claims = store.query("MATCH (c:Claim) RETURN c.id, c.amount, c.status ORDER BY c.id")
    edges = store.query(
        "MATCH (a)-[r]->(b) WHERE type(r) IN $types RETURN a.id, type(r), b.id ORDER BY a.id, type(r), b.id",
        {"types": DECISION_EDGE_TYPES})
    payload = json.dumps({"evidence": evidence, "sources": sources, "claims": claims, "edges": edges},
                         sort_keys=True, default=str)
    return {"revision": hashlib.sha256(payload.encode()).hexdigest()[:16],
            "evidence_count": len(evidence), "edge_count": len(edges)}


def set_evidence_status(store: GraphStore, evidence_id: str, status: str) -> None:
    if status not in ("PRESENT", "MISSING", "PENDING"):
        raise ValueError("status must be PRESENT, MISSING or PENDING")
    store.query("MATCH (e:Evidence {id: $id}) SET e.status = $s", {"id": evidence_id, "s": status})


def set_source_verified(store: GraphStore, source_id: str, verified: bool) -> None:
    store.query("MATCH (s:Source {id: $id}) SET s.verified = $v", {"id": source_id, "v": verified})


def drop_decision_edge(store: GraphStore, src_label: str, src_id: str, rel: str,
                       dst_label: str, dst_id: str) -> int:
    if rel not in DECISION_EDGE_TYPES:
        raise ValueError(f"relationship {rel} is not a decision relationship")
    match = f"(a:{src_label} {{id: $a}})-[r:{rel}]->(b:{dst_label} {{id: $b}})"
    found = store.query(f"MATCH {match} RETURN count(r)", {"a": src_id, "b": dst_id})
    count = found[0][0] if found else 0
    if count:
        store.query(f"MATCH {match} DELETE r", {"a": src_id, "b": dst_id})
    return count


def new_sim_name() -> str:
    return f"{SIM_PREFIX}{uuid.uuid4().hex[:10]}"
