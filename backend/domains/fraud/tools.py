"""Graph tools shared by the investigator agent, the HTTP API and the MCP server.

Read tools return plain dicts. The only write is `propose_freeze`, which creates a PROPOSED
Action node; it never freezes anything. Execution happens later, after a human approves it
(see app/agent/actions.py).
"""
import json
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from domains.fraud import config, policy
from domains.fraud.store import GraphStore

Recorder = Callable[[dict], None]

# Shared device or card = strong evidence of the same operator. Shared IP = weak (households, NAT, ISPs).
STRONG_RELS = "USED_DEVICE|OWNS_CARD"


def _now() -> str:
    return datetime.now(UTC).isoformat()


class GraphTools:
    def __init__(self, store: GraphStore, recorder: Recorder | None = None):
        self.store = store
        self.recorder = recorder

    def _q(self, cypher: str, params: dict | None = None) -> list:
        started = time.perf_counter()
        rows = self.store.query(cypher, params)
        ms = round((time.perf_counter() - started) * 1000, 1)
        if self.recorder:
            self.recorder({"cypher": " ".join(cypher.split()), "params": params or {},
                           "ms": ms, "rows": len(rows), "at": _now()})
        return rows

    # ---------- read tools ----------

    def flagged_transactions(self) -> list[dict]:
        rows = self._q("MATCH (t:Transaction {flagged: true})-[:FROM]->(a:Account) "
                       "RETURN t.id, t.amount, t.ts, a.id ORDER BY t.ts")
        return [{"transaction_id": r[0], "amount": r[1], "ts": r[2], "account_id": r[3]} for r in rows]

    def account_profile(self, account_id: str) -> dict:
        rows = self._q(
            "MATCH (a:Account {id: $id}) "
            "OPTIONAL MATCH (a)-[:USED_DEVICE]->(d:Device) "
            "OPTIONAL MATCH (a)-[:OWNS_CARD]->(c:Card) "
            "OPTIONAL MATCH (a)-[:LOGGED_FROM]->(i:IP) "
            "RETURN a.id, a.name, a.status, collect(DISTINCT d.id), collect(DISTINCT c.id), "
            "collect(DISTINCT i.addr)",
            {"id": account_id})
        if not rows:
            return {"error": f"unknown account {account_id}"}
        r = rows[0]
        return {"account_id": r[0], "name": r[1], "status": r[2],
                "devices": r[3], "cards": r[4], "ips": r[5]}

    def ring_members(self, account_id: str) -> list[dict]:
        """Accounts linked to `account_id` through shared DEVICE or CARD nodes, up to MAX_RING_RELS hops.

        Each member keeps its shortest path, so the explanation is a concrete chain of nodes.
        """
        rows = self._q(
            f"MATCH p=(a:Account {{id: $id}})-[:{STRONG_RELS}*2..{config.MAX_RING_RELS}]-(b:Account) "
            "WHERE b.id <> $id "
            "RETURN b.id, [n IN nodes(p) | coalesce(n.id, n.addr)], [x IN relationships(p) | type(x)], "
            "[n IN nodes(p) | labels(n)[0]]",
            {"id": account_id})
        best: dict[str, dict] = {}
        for member_id, ids, rels, labels in rows:
            hops = len(rels) // 2
            if member_id not in best or hops < best[member_id]["hops"]:
                best[member_id] = {
                    "account_id": member_id,
                    "hops": hops,
                    "path": [{"label": node_label, "id": node_id} for node_label, node_id in zip(labels, ids)],
                    "rels": rels,
                }
        return sorted(best.values(), key=lambda m: (m["hops"], m["account_id"]))

    def weak_links(self, account_id: str) -> list[dict]:
        """Accounts that share only an IP with `account_id`. Reported, never used for a freeze."""
        # Written as an explicit two-hop pattern: FalkorDB returned no rows for a variable-length
        # LOGGED_FROM*2..2 with a filter, so this avoids that path shape.
        rows = self._q(
            "MATCH (a:Account {id: $id})-[:LOGGED_FROM]-(i:IP)-[:LOGGED_FROM]-(b:Account) "
            "WHERE b.id <> $id RETURN DISTINCT b.id, i.addr ORDER BY b.id",
            {"id": account_id})
        return [{"account_id": r[0], "shared_ip": r[1]} for r in rows]

    def neighborhood(self, account_id: str) -> dict:
        """Two-hop subgraph around an account, for the UI graph view."""
        rows = self._q(
            "MATCH (a:Account {id: $id})-[r1]-(n) "
            "OPTIONAL MATCH (n)-[r2]-(m) WHERE m <> a "
            "RETURN labels(n)[0], coalesce(n.id, n.addr), type(r1), "
            "labels(m)[0], coalesce(m.id, m.addr), type(r2)",
            {"id": account_id})
        nodes, edges = {}, set()
        nodes[f"Account:{account_id}"] = {"id": f"Account:{account_id}", "label": "Account", "name": account_id}
        for n_label, n_id, r1, m_label, m_id, r2 in rows:
            n_key = f"{n_label}:{n_id}"
            nodes.setdefault(n_key, {"id": n_key, "label": n_label, "name": n_id})
            edges.add((f"Account:{account_id}", n_key, r1))
            if m_id is not None:
                m_key = f"{m_label}:{m_id}"
                nodes.setdefault(m_key, {"id": m_key, "label": m_label, "name": m_id})
                edges.add((n_key, m_key, r2))
        return {
            "nodes": list(nodes.values()),
            "edges": [{"source": s, "target": t, "type": ty} for s, t, ty in sorted(edges)],
        }

    def list_actions(self) -> list[dict]:
        rows = self._q(
            "MATCH (x:Action) OPTIONAL MATCH (x)-[:TARGETS]->(a:Account) "
            "RETURN x.id, x.type, x.status, x.rule, x.created_at, x.evidence, x.receipt, collect(a.id)"
            " ORDER BY x.created_at DESC")
        return [_action_row(r) for r in rows]

    # ---------- the one write tool the agent can call ----------

    def propose_freeze(self, account_id: str, run_id: str = "manual") -> dict:
        """Derive the freeze set from the graph and create a PROPOSED Action. Code decides, not the model.

        Returns {"proposed": action} or {"rejected": reason}.
        """
        members = self.ring_members(account_id)
        decision = policy.decide_freeze(account_id, members)
        if decision is None:
            return {"rejected": "ring too small or no strong-link evidence", "members": len(members)}
        action_id = f"ACT-{uuid.uuid4().hex[:8]}"
        evidence = json.dumps(decision["evidence"], separators=(",", ":"))
        self._q(
            "CREATE (x:Action {id: $id, type: 'FREEZE_ACCOUNTS', status: 'PROPOSED', rule: $rule, "
            "run_id: $run, created_at: $ts, evidence: $evidence})",
            {"id": action_id, "rule": decision["rule"], "run": run_id, "ts": _now(), "evidence": evidence})
        self._q(
            "MATCH (x:Action {id: $id}) UNWIND $targets AS t MATCH (a:Account {id: t}) "
            "CREATE (x)-[:TARGETS]->(a)",
            {"id": action_id, "targets": decision["targets"]})
        return {"proposed": _action_row(self._q(
            "MATCH (x:Action {id: $id}) OPTIONAL MATCH (x)-[:TARGETS]->(a:Account) "
            "RETURN x.id, x.type, x.status, x.rule, x.created_at, x.evidence, x.receipt, collect(a.id)",
            {"id": action_id})[0])}


def _action_row(r: list) -> dict:
    return {"action_id": r[0], "type": r[1], "status": r[2], "rule": r[3], "created_at": r[4],
            "evidence": json.loads(r[5]) if r[5] else [], "receipt": r[6],
            "targets": sorted(t for t in r[7] if t is not None)}
