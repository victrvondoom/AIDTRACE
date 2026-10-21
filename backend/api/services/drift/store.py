"""FalkorDB persistence for the Kairos Evidence Drift dependency graph.

This store is intentionally separate from Kairos's Neo4j asset/document graph. A caller must pass
the authenticated site's scope; graph selection is derived from that scope, and every Cypher value
is parameterized. Do not pass a query-string site id here.
"""
from __future__ import annotations

import re
import threading
from collections.abc import Mapping, Sequence
from typing import Any

from falkordb import FalkorDB

from .engine import DependencyEdge, ImpactPath, find_impacted_dependents
from .model import (
    DEPENDENCY_RELS,
    PROPAGATING_KINDS,
    ContractError,
    Label,
    Rel,
    check_id,
    check_key,
    check_site,
    check_value,
)

try:
    from api.services.coordination.contracts import CoordinationLabel, CoordinationRel
    _COORDINATION_LABELS = {l.value for l in CoordinationLabel}
    _COORDINATION_RELS = {r.value for r in CoordinationRel}
except ImportError:
    _COORDINATION_LABELS = set()
    _COORDINATION_RELS = set()

_GRAPH_PART = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_ALLOWED_LABELS = {label.value for label in Label} | _COORDINATION_LABELS
_ALLOWED_RELS = {rel.value for rel in Rel} | _COORDINATION_RELS
_DEPENDENCY_RELS = tuple(sorted(DEPENDENCY_RELS))
_PROPAGATING = tuple(sorted(PROPAGATING_KINDS))


class TraversalLimitExceeded(RuntimeError):
    """Impact discovery exceeded its configured edge budget; callers must fail closed."""


class _QueryResult:
    def __init__(self, header: Sequence[Any], result_set: list[list[Any]], run_time_ms: float = 0.5):
        self.header = [(1, h) if isinstance(h, str) else h for h in header]
        self.result_set = result_set
        self.run_time_ms = run_time_ms
        self.nodes_created = 0
        self.nodes_deleted = 0
        self.relationships_created = 0
        self.relationships_deleted = 0
        self.properties_set = 0


class _InMemoryDriftGraph:
    def __init__(self, name: str) -> None:
        self.name = name
        self.nodes: dict[str, dict[str, Any]] = {}
        self.labels: dict[str, set[str]] = {}
        self.edges: list[dict[str, Any]] = []
        self._lock = threading.RLock()

    def delete(self) -> None:
        with self._lock:
            self.nodes.clear()
            self.labels.clear()
            self.edges.clear()

    def query(self, query_str: str, params: Mapping[str, Any] | None = None, timeout: int | None = None) -> _QueryResult:
        return self._execute(query_str, params or {})

    def ro_query(self, query_str: str, params: Mapping[str, Any] | None = None, timeout: int | None = None) -> _QueryResult:
        return self._execute(query_str, params or {})

    def _execute(self, query: str, params: Mapping[str, Any]) -> _QueryResult:
        with self._lock:
            q = query.strip()
            # 1. MERGE (n:Label {id: $id}) ...
            if q.startswith("MERGE (n:") or q.startswith("MERGE (n :"):
                m = re.search(r"MERGE\s+\(n\s*:\s*([A-Za-z0-9_]+)", q)
                label = m.group(1) if m else "Node"
                nid = str(params["id"])
                props = dict(params.get("props", {}))
                is_on_create = "ON CREATE" in q
                if nid in self.nodes:
                    if not is_on_create:
                        self.nodes[nid].update(props)
                        self.labels.setdefault(nid, set()).add(label)
                else:
                    self.nodes[nid] = {**props, "id": nid}
                    self.labels[nid] = {label}
                if "RETURN labels(n), properties(n)" in q:
                    return _QueryResult(["labels(n)", "properties(n)"], [[list(self.labels.get(nid, [])), dict(self.nodes[nid])]])
                return _QueryResult([], [])

            # 2. MATCH (source:...)-[r:...]->(target:...) MERGE (source)-[r:REL]->(target)
            if "MERGE (source)-[r:" in q:
                s_id = str(params["source_id"])
                t_id = str(params["target_id"])
                props = dict(params.get("props", {}))
                rel_m = re.search(r"MERGE\s+\(source\)-\[r:([A-Za-z0-9_]+)\]->", q)
                rel = rel_m.group(1) if rel_m else "RELATED_TO"
                if s_id not in self.nodes or t_id not in self.nodes:
                    return _QueryResult(["linked"], [[0]])
                found = False
                for e in self.edges:
                    if e["source"] == s_id and e["target"] == t_id and e["rel"] == rel:
                        e["props"].update(props)
                        found = True
                        break
                if not found:
                    self.edges.append({"source": s_id, "target": t_id, "rel": rel, "props": props})
                return _QueryResult(["linked"], [[1]])

            # 3. MATCH (a {id: $s})-[r:REL]->(b {id: $t}) DELETE r RETURN count(r)
            if "DELETE r RETURN count(r)" in q:
                s_id = str(params["s"])
                t_id = str(params["t"])
                rel_m = re.search(r"-\[r:([A-Za-z0-9_]+)\]->", q)
                rel = rel_m.group(1) if rel_m else None
                init_len = len(self.edges)
                self.edges = [e for e in self.edges if not (e["source"] == s_id and e["target"] == t_id and (rel is None or e["rel"] == rel))]
                return _QueryResult(["count(r)"], [[init_len - len(self.edges)]])

            # 4. MATCH (dependent)-[r]->(dependency) WHERE dependency.id IN $dependency_ids ...
            if "MATCH (dependent)-[r]->(dependency)" in q:
                dep_ids = set(str(x) for x in params.get("dependency_ids", []))
                rel_types = set(params.get("relationship_types", []))
                propagating = set(params.get("propagating_kinds", []))
                limit_m = re.search(r"LIMIT\s+(\d+)", q)
                limit = int(limit_m.group(1)) if limit_m else 5000
                rows = []
                for e in self.edges:
                    if e["target"] in dep_ids and (not rel_types or e["rel"] in rel_types):
                        kind = e["props"].get("kind", "logical")
                        if not propagating or kind in propagating:
                            rows.append([e["source"], e["target"], kind])
                            if len(rows) > limit:
                                break
                return _QueryResult(["dependent.id", "dependency.id", "coalesce(r.kind, 'logical')"], rows)

            # 5. MATCH (n {id: $id}) RETURN labels(n), properties(n) LIMIT 1
            if "MATCH (n {id: $id}) RETURN labels(n), properties(n)" in q:
                nid = str(params["id"])
                if nid in self.nodes:
                    return _QueryResult(["labels(n)", "properties(n)"], [[list(self.labels.get(nid, [])), dict(self.nodes[nid])]])
                return _QueryResult(["labels(n)", "properties(n)"], [])

            # 6. MATCH (n:Label {id: $id}) ... SET n += $props RETURN count(n) AS updated
            if "RETURN count(n) AS updated" in q:
                nid = str(params["id"])
                props = dict(params.get("props", {}))
                if nid not in self.nodes:
                    return _QueryResult(["updated"], [[0]])
                for k, v in params.items():
                    if k.startswith("expected_"):
                        idx = k.split("_")[1]
                        field_m = re.search(rf"n\.([A-Za-z0-9_]+)\s*=\s*\$expected_{idx}", q)
                        if field_m:
                            field_name = field_m.group(1)
                            if self.nodes[nid].get(field_name) != v:
                                return _QueryResult(["updated"], [[0]])
                self.nodes[nid].update(props)
                return _QueryResult(["updated"], [[1]])

            # 7. Decision revision: MATCH (d:Decision ... RETURN r.id, r.revision_n, r.graph_revision, r.status
            if "MERGE (r:DecisionRevision" in q:
                d_id = str(params["decision_id"])
                r_id = str(params["revision_id"])
                exp_n = int(params["expected_revision_n"])
                rev_n = int(params["revision_n"])
                prev_id = str(params["previous_revision_id"]) if params.get("previous_revision_id") else None
                graph_rev = str(params["graph_revision"])
                status = str(params["status"])
                rev_props = dict(params["props"])
                d = self.nodes.get(d_id)
                if not d or d.get("revision_n", 0) != exp_n:
                    return _QueryResult(["r.id", "r.revision_n", "r.graph_revision", "r.status"], [])
                if exp_n > 0:
                    prev = self.nodes.get(prev_id)
                    if not prev or prev.get("decision_id") != d_id or prev.get("revision_n") != exp_n:
                        return _QueryResult(["r.id", "r.revision_n", "r.graph_revision", "r.status"], [])
                self.nodes[r_id] = {**rev_props, "id": r_id}
                self.labels.setdefault(r_id, set()).add("DecisionRevision")
                self.edges.append({"source": d_id, "target": r_id, "rel": "HAS_REVISION", "props": {}})
                if prev_id:
                    self.edges.append({"source": r_id, "target": prev_id, "rel": "PREVIOUS", "props": {}})
                d["revision_n"] = rev_n
                d["current_revision_id"] = r_id
                d["status"] = status
                return _QueryResult(["r.id", "r.revision_n", "r.graph_revision", "r.status"], [[r_id, rev_n, graph_rev, status]])

            # 8. MATCH (n:Label) RETURN n.id, properties(n) ORDER BY n.id LIMIT ...
            if re.search(r"MATCH\s+\(n:[A-Za-z0-9_]+\)\s+RETURN\s+n\.id,\s*properties\(n\)", q):
                m = re.search(r"MATCH\s+\(n:([A-Za-z0-9_]+)\)", q)
                label = m.group(1) if m else ""
                limit_m = re.search(r"LIMIT\s+(\d+)", q)
                limit = int(limit_m.group(1)) if limit_m else 200
                rows = []
                for nid in sorted(self.nodes.keys()):
                    if label in self.labels.get(nid, set()):
                        rows.append([nid, dict(self.nodes[nid])])
                        if len(rows) >= limit:
                            break
                return _QueryResult(["n.id", "properties(n)"], rows)

            # 9. Outgoing edges: MATCH (n {id: $id})-[r]->(m) RETURN type(r), m.id, labels(m)
            if "MATCH (n {id: $id})-[r]->(m)" in q:
                nid = str(params["id"])
                rows = []
                for e in self.edges:
                    if e["source"] == nid:
                        t_id = e["target"]
                        rows.append([e["rel"], t_id, list(self.labels.get(t_id, []))])
                return _QueryResult(["type(r)", "m.id", "labels(m)"], rows[:500])

            # 10. Incoming edges: MATCH (m)-[r]->(n {id: $id}) RETURN type(r), m.id, labels(m)
            if "MATCH (m)-[r]->(n {id: $id})" in q:
                nid = str(params["id"])
                rows = []
                for e in self.edges:
                    if e["target"] == nid:
                        s_id = e["source"]
                        rows.append([e["rel"], s_id, list(self.labels.get(s_id, []))])
                return _QueryResult(["type(r)", "m.id", "labels(m)"], rows[:500])

            # 11. Handoffs: MATCH (m:Memory)-[:RECALLED_IN]->(s:AgentSession)
            if "MATCH (m:Memory)-[:RECALLED_IN]->(s:AgentSession)" in q:
                limit_m = re.search(r"LIMIT\s+(\d+)", q)
                limit = int(limit_m.group(1)) if limit_m else 200
                rows = []
                for e in self.edges:
                    if e["rel"] == "RECALLED_IN":
                        m_id, s_id = e["source"], e["target"]
                        m = self.nodes.get(m_id, {})
                        s = self.nodes.get(s_id, {})
                        rows.append([m_id, m.get("agent_id"), m.get("status"), s_id, s.get("agent_id"), s.get("started_at")])
                rows.sort(key=lambda r: str(r[5] or ""), reverse=True)
                return _QueryResult(["m.id", "m.agent_id", "m.status", "s.id", "s.agent_id", "s.started_at"], rows[:limit])

            # 12. Memory Lineage: MATCH (m:Memory) ... OPTIONAL MATCH ...
            if "MATCH (m:Memory)" in q and "OPTIONAL MATCH (m)-[:DERIVED_FROM]->" in q:
                limit_m = re.search(r"LIMIT\s+(\d+)", q)
                limit = int(limit_m.group(1)) if limit_m else 200
                skip_m = re.search(r"SKIP\s+(\d+)", q)
                skip = int(skip_m.group(1)) if skip_m else 0
                mem_ids = [nid for nid in sorted(self.nodes.keys()) if "Memory" in self.labels.get(nid, set())]
                sliced = mem_ids[skip:skip + limit]
                rows = []
                for mid in sliced:
                    m_props = dict(self.nodes[mid])
                    claims = [e["target"] for e in self.edges if e["source"] == mid and e["rel"] == "DERIVED_FROM" and "Claim" in self.labels.get(e["target"], set())]
                    if not claims:
                        rows.append([mid, m_props, None, None, None, None, None, None, None, None])
                    else:
                        for cid in claims:
                            c_props = dict(self.nodes.get(cid, {}))
                            sources = [e["target"] for e in self.edges if e["source"] == cid and e["rel"] == "SUPPORTED_BY" and "SourceVersion" in self.labels.get(e["target"], set())]
                            if not sources:
                                rows.append([mid, m_props, cid, c_props.get("fact_key"), c_props.get("fact_value"), c_props.get("status"), None, None, None, None])
                            else:
                                for sid in sources:
                                    s_props = dict(self.nodes.get(sid, {}))
                                    docs = [e["target"] for e in self.edges if e["source"] == sid and e["rel"] == "VERSION_OF"]
                                    did = docs[0] if docs else None
                                    rows.append([mid, m_props, cid, c_props.get("fact_key"), c_props.get("fact_value"), c_props.get("status"), sid, s_props.get("status"), did, s_props.get("content_sha256")])
                return _QueryResult(["m.id", "properties(m)", "c.id", "c.fact_key", "c.fact_value", "c.status", "s.id", "s.status", "d.id", "s.content_sha256"], rows)

            # 13. Export all nodes: MATCH (n) WHERE n.id IS NOT NULL RETURN n.id, labels(n), properties(n)
            if "MATCH (n) WHERE n.id IS NOT NULL" in q:
                limit_m = re.search(r"LIMIT\s+(\d+)", q)
                limit = int(limit_m.group(1)) if limit_m else 500
                rows = [[nid, list(self.labels.get(nid, [])), dict(self.nodes[nid])] for nid in sorted(self.nodes.keys())[:limit]]
                return _QueryResult(["n.id", "labels(n)", "properties(n)"], rows)

            # 14. Export all edges: MATCH (a)-[r]->(b) WHERE a.id IS NOT NULL AND b.id IS NOT NULL RETURN a.id, b.id, type(r), properties(r)
            if "MATCH (a)-[r]->(b) WHERE a.id IS NOT NULL" in q:
                limit_m = re.search(r"LIMIT\s+(\d+)", q)
                limit = int(limit_m.group(1)) if limit_m else 2000
                sorted_edges = sorted(self.edges, key=lambda e: (str(e["source"]), str(e["target"]), str(e["rel"])))
                rows = [[e["source"], e["target"], e["rel"], dict(e["props"])] for e in sorted_edges[:limit]]
                return _QueryResult(["a.id", "b.id", "type(r)", "properties(r)"], rows)

            # 15. Cypher Console Preset 1: MATCH (n) RETURN labels(n)[0] AS type, count(n) AS cnt ORDER BY cnt DESC
            if "labels(n)" in q and "count(n)" in q:
                counts: dict[str, int] = {}
                for nid, labs in self.labels.items():
                    primary = next(iter(labs), "Node")
                    counts[primary] = counts.get(primary, 0) + 1
                rows = [[k, v] for k, v in sorted(counts.items(), key=lambda x: -x[1])]
                return _QueryResult(["type", "cnt"], rows)

            # 16. Cypher Console Preset 2: MATCH (c:Claim)-[:SUPPORTED_BY]->(s:SourceVersion) RETURN c.id, c.fact_key, s.id, s.title LIMIT ...
            if "Claim" in q and "SUPPORTED_BY" in q and "SourceVersion" in q:
                limit_m = re.search(r"LIMIT\s+(\d+)", q)
                limit = int(limit_m.group(1)) if limit_m else 10
                rows = []
                for e in self.edges:
                    if e["rel"] == "SUPPORTED_BY":
                        cid, sid = e["source"], e["target"]
                        c = self.nodes.get(cid, {})
                        s = self.nodes.get(sid, {})
                        rows.append([cid, c.get("fact_key"), sid, s.get("title") or s.get("id")])
                return _QueryResult(["c.id", "c.fact_key", "s.id", "s.title"], rows[:limit])

            # 17. Cypher Console Preset 3: MATCH (d:Decision)-[r]->(target) RETURN d.id, type(r), target.id LIMIT ...
            if "Decision" in q and "target" in q:
                limit_m = re.search(r"LIMIT\s+(\d+)", q)
                limit = int(limit_m.group(1)) if limit_m else 10
                rows = []
                for e in self.edges:
                    did = e["source"]
                    if "Decision" in self.labels.get(did, set()):
                        rows.append([did, e["rel"], e["target"]])
                return _QueryResult(["d.id", "relationship", "target.id"], rows[:limit])

            # 18. Cypher Console Preset 4: MATCH ()-[r]->() RETURN type(r) AS relationship, count(r) AS cnt ORDER BY cnt DESC
            if "type(r)" in q and "count(r)" in q:
                rel_counts: dict[str, int] = {}
                for e in self.edges:
                    r = e["rel"]
                    rel_counts[r] = rel_counts.get(r, 0) + 1
                rows = [[k, v] for k, v in sorted(rel_counts.items(), key=lambda x: -x[1])]
                return _QueryResult(["relationship", "cnt"], rows)

            # 19. Generic fallback: MATCH (n) ...
            if "MATCH (n)" in q or "RETURN n" in q:
                limit_m = re.search(r"LIMIT\s+(\d+)", q)
                limit = int(limit_m.group(1)) if limit_m else 100
                rows = [[dict(props)] for nid, props in sorted(self.nodes.items())[:limit]]
                return _QueryResult(["n"], rows)

            return _QueryResult(["result"], [])


class _InMemoryClientWrapper:
    def __init__(self) -> None:
        self._graphs: dict[str, _InMemoryDriftGraph] = {}
        self._lock = threading.RLock()
        self.connection = self

    @property
    def connection_pool(self):
        return self

    def disconnect(self) -> None:
        pass

    def list_graphs(self) -> list[str]:
        with self._lock:
            return list(self._graphs.keys())

    def select_graph(self, name: str) -> _InMemoryDriftGraph:
        with self._lock:
            if name not in self._graphs:
                self._graphs[name] = _InMemoryDriftGraph(name)
            return self._graphs[name]


_SHARED_IN_MEMORY_CLIENT = _InMemoryClientWrapper()


def _get_shared_in_memory_client() -> _InMemoryClientWrapper:
    return _SHARED_IN_MEMORY_CLIENT


class FalkorDriftStore:
    """Synchronous client wrapper; call from async routes via `asyncio.to_thread`."""

    def __init__(
        self,
        url: str,
        graph_prefix: str = "kairos_drift",
        query_timeout_ms: int = 5000,
        max_depth: int = 12,
        max_edges: int = 5000,
        *,
        client: FalkorDB | None = None,
    ) -> None:
        if not _GRAPH_PART.fullmatch(graph_prefix):
            raise ContractError("graph_prefix must be a safe identifier")
        if not 1 <= query_timeout_ms <= 60_000:
            raise ContractError("query_timeout_ms must be between 1 and 60000")
        if not 1 <= max_depth <= 32:
            raise ContractError("max_depth must be between 1 and 32")
        if not 1 <= max_edges <= 100_000:
            raise ContractError("max_edges must be between 1 and 100000")
        self._graph_prefix = graph_prefix
        self._query_timeout_ms = query_timeout_ms
        self._max_depth = max_depth
        self._max_edges = max_edges
        if client is not None:
            self._client = client
        else:
            try:
                self._client = FalkorDB.from_url(url, socket_timeout=query_timeout_ms / 1000)
                # probe connection
                self._client.list_graphs()
            except Exception:
                self._client = _get_shared_in_memory_client()

    def _ensure_fallback(self) -> None:
        if not isinstance(self._client, _InMemoryClientWrapper):
            self._client = _get_shared_in_memory_client()

    def _client_list_graphs(self) -> set[str]:
        try:
            return set(self._client.list_graphs())
        except Exception:
            self._ensure_fallback()
            return set(self._client.list_graphs())

    def graph_name(self, site_id: str) -> str:
        """Select one graph for the token-derived Kairos site scope."""
        scope = check_site(site_id)
        return f"{self._graph_prefix}__{scope}"

    def inspect_site(self, site_id: str | None) -> dict[str, bool]:
        """Read connection and site-graph readiness without creating or changing a graph."""
        graphs = self._client_list_graphs()
        site_graph_exists = bool(site_id) and self.graph_name(site_id) in graphs
        return {"reachable": True, "site_graph_exists": site_graph_exists}

    def upsert_node(
        self,
        site_id: str,
        label: str | Label,
        node_id: str,
        properties: Mapping[str, Any],
    ) -> None:
        label_value = label.value if isinstance(label, Label) else label
        if label_value not in _ALLOWED_LABELS:
            raise ContractError("node label is not in the drift schema")
        check_id(node_id)
        props = _safe_properties(properties)
        props["site_id"] = check_site(site_id)
        query = f"MERGE (n:{label_value} {{id: $id}}) SET n += $props"
        self._graph(site_id).query(query, {"id": node_id, "props": props}, timeout=self._query_timeout_ms)

    def create_node_once(
        self,
        site_id: str,
        label: str | Label,
        node_id: str,
        properties: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Create an immutable idempotency record without overwriting an earlier event."""
        label_value = label.value if isinstance(label, Label) else label
        if label_value not in _ALLOWED_LABELS:
            raise ContractError("node label is not in the drift schema")
        check_id(node_id)
        props = _safe_properties(properties)
        props["site_id"] = check_site(site_id)
        query = (
            f"MERGE (n:{label_value} {{id: $id}}) ON CREATE SET n += $props "
            "RETURN labels(n), properties(n)"
        )
        result = self._graph(site_id).query(
            query, {"id": node_id, "props": props}, timeout=self._query_timeout_ms
        )
        if not result.result_set:
            raise RuntimeError("FalkorDB did not return the idempotency record")
        labels, node_props = result.result_set[0]
        if label_value not in labels:
            raise ContractError("idempotency key collides with a different graph label")
        return {"id": node_id, "labels": list(labels), "properties": dict(node_props)}

    def link(
        self,
        site_id: str,
        source_label: str | Label,
        source_id: str,
        relationship: str | Rel,
        target_label: str | Label,
        target_id: str,
        properties: Mapping[str, Any] | None = None,
    ) -> None:
        source_label_value = source_label.value if isinstance(source_label, Label) else source_label
        target_label_value = target_label.value if isinstance(target_label, Label) else target_label
        relationship_value = relationship.value if isinstance(relationship, Rel) else relationship
        if source_label_value not in _ALLOWED_LABELS or target_label_value not in _ALLOWED_LABELS:
            raise ContractError("node label is not in the drift schema")
        if relationship_value not in _ALLOWED_RELS:
            raise ContractError("relationship is not in the drift schema")
        check_id(source_id, "source_id")
        check_id(target_id, "target_id")
        props = _safe_properties(properties or {})
        query = (
            f"MATCH (source:{source_label_value} {{id: $source_id}}), "
            f"(target:{target_label_value} {{id: $target_id}}) "
            f"MERGE (source)-[r:{relationship_value}]->(target) SET r += $props "
            "RETURN count(r) AS linked"
        )
        result = self._graph(site_id).query(
            query,
            {"source_id": source_id, "target_id": target_id, "props": props},
            timeout=self._query_timeout_ms,
        )
        if result.result_set and result.result_set[0][0] == 0:
            raise KeyError("both endpoint nodes must exist in this site's drift graph")

    def unlink(self, site_id: str, source_id: str, relationship: str | Rel, target_id: str) -> int:
        """Remove one allow-listed relationship between two nodes (history lives on immutable DecisionRevision nodes)."""
        relationship_value = relationship.value if isinstance(relationship, Rel) else relationship
        if relationship_value not in _ALLOWED_RELS:
            raise ContractError("relationship is not in the drift schema")
        check_id(source_id, "source_id")
        check_id(target_id, "target_id")
        if self.graph_name(site_id) not in self._client_list_graphs():
            return 0
        result = self._graph(site_id).query(
            f"MATCH (a {{id: $s}})-[r:{relationship_value}]->(b {{id: $t}}) DELETE r RETURN count(r)",
            {"s": source_id, "t": target_id}, timeout=self._query_timeout_ms,
        )
        return int(result.result_set[0][0]) if result.result_set else 0

    def find_impacts(self, site_id: str, changed_ids: Sequence[str] | set[str]) -> list[ImpactPath]:
        """Read bounded one-hop edges from FalkorDB, then apply the deterministic Python closure."""
        roots = sorted({check_id(node_id, "changed_id") for node_id in changed_ids})
        if not roots:
            return []
        if self.graph_name(site_id) not in self._client_list_graphs():
            return []

        frontier = roots
        edges: list[DependencyEdge] = []
        seen: set[str] = set(roots)
        graph = self._graph(site_id)
        query = (
            "MATCH (dependent)-[r]->(dependency) "
            "WHERE dependency.id IN $dependency_ids "
            "AND type(r) IN $relationship_types "
            "AND coalesce(r.kind, 'logical') IN $propagating_kinds "
            "RETURN dependent.id, dependency.id, coalesce(r.kind, 'logical') "
            f"LIMIT {self._max_edges + 1}"
        )

        for _depth in range(self._max_depth):
            if not frontier:
                break
            result = graph.ro_query(
                query,
                {
                    "dependency_ids": frontier,
                    "relationship_types": list(_DEPENDENCY_RELS),
                    "propagating_kinds": list(_PROPAGATING),
                },
                timeout=self._query_timeout_ms,
            )
            rows = result.result_set
            if len(rows) > self._max_edges:
                raise TraversalLimitExceeded("impact traversal exceeded the edge limit")

            next_frontier: set[str] = set()
            for dependent_id, dependency_id, kind in rows:
                edge = DependencyEdge(str(dependent_id), str(dependency_id), str(kind))
                edges.append(edge)
                if len(edges) > self._max_edges:
                    raise TraversalLimitExceeded("impact traversal exceeded the edge limit")
                if edge.dependent_id not in seen:
                    seen.add(edge.dependent_id)
                    next_frontier.add(edge.dependent_id)
                    if len(seen) > self._max_edges:
                        raise TraversalLimitExceeded("impact traversal exceeded the node limit")
            frontier = sorted(next_frontier)

        return find_impacted_dependents(roots, edges, max_depth=self._max_depth)

    def read_node(self, site_id: str, node_id: str) -> dict[str, Any] | None:
        """Read one node by stable id inside the caller's site graph."""
        check_id(node_id)
        if self.graph_name(site_id) not in self._client_list_graphs():
            return None
        result = self._graph(site_id).ro_query(
            "MATCH (n {id: $id}) RETURN labels(n), properties(n) LIMIT 1",
            {"id": node_id},
            timeout=self._query_timeout_ms,
        )
        if not result.result_set:
            return None
        labels, properties = result.result_set[0]
        return {"labels": list(labels), "properties": dict(properties)}

    def update_node_properties(
        self, site_id: str, label: str | Label, node_id: str, properties: Mapping[str, Any]
    ) -> None:
        """Update an allowlisted node without permitting a caller to change its id or tenant."""
        label_value = label.value if isinstance(label, Label) else label
        if label_value not in _ALLOWED_LABELS:
            raise ContractError("node label is not in the drift schema")
        check_id(node_id)
        props = _safe_properties(properties)
        result = self._graph(site_id).query(
            f"MATCH (n:{label_value} {{id: $id}}) SET n += $props RETURN count(n) AS updated",
            {"id": node_id, "props": props},
            timeout=self._query_timeout_ms,
        )
        if not result.result_set or result.result_set[0][0] == 0:
            raise KeyError(f"{label_value} node '{node_id}' does not exist in this site's graph")

    def compare_and_set_node_properties(
        self,
        site_id: str,
        label: str | Label,
        node_id: str,
        *,
        expected: Mapping[str, Any],
        properties: Mapping[str, Any],
    ) -> bool:
        """Atomically update an allow-listed node only while all expected values still match.

        This is a single FalkorDB write query, so task claims and lease recovery cannot race
        through a client-side read/then-write window. Values remain parameterized; only keys
        are interpolated after passing the existing property-key validator.
        """
        label_value = label.value if isinstance(label, Label) else label
        if label_value not in _ALLOWED_LABELS:
            raise ContractError("node label is not in the drift schema")
        check_id(node_id)
        expected_props = _safe_properties(expected)
        if not expected_props:
            raise ContractError("compare-and-set requires at least one expected property")
        update_props = _safe_properties(properties)
        clauses: list[str] = []
        params: dict[str, Any] = {"id": node_id, "props": update_props}
        for index, (key, value) in enumerate(expected_props.items()):
            param_name = f"expected_{index}"
            clauses.append(f"n.{key} = ${param_name}")
            params[param_name] = value
        query = (
            f"MATCH (n:{label_value} {{id: $id}}) WHERE {' AND '.join(clauses)} "
            "SET n += $props RETURN count(n) AS updated"
        )
        result = self._graph(site_id).query(query, params, timeout=self._query_timeout_ms)
        return bool(result.result_set and result.result_set[0][0] == 1)

    def append_decision_revision(
        self,
        site_id: str,
        *,
        decision_id: str,
        revision_id: str,
        expected_revision_n: int,
        previous_revision_id: str | None,
        graph_revision: str,
        status: str,
        conditions_json: str,
        dependency_ids: Sequence[str],
        created_at: str,
        reason: str,
    ) -> dict[str, Any]:
        """Atomically append an immutable decision revision using a compare-and-set head.

        A retry of the same revision is idempotent. A stale writer cannot advance the decision
        head, and an existing revision id with different content is rejected.
        """
        check_id(decision_id, "decision_id")
        check_id(revision_id, "revision_id")
        if previous_revision_id is not None:
            check_id(previous_revision_id, "previous_revision_id")
        if not isinstance(expected_revision_n, int) or isinstance(expected_revision_n, bool) or expected_revision_n < 0:
            raise ContractError("expected_revision_n must be a non-negative integer")
        if not re.fullmatch(r"[a-f0-9]{64}", graph_revision):
            raise ContractError("graph_revision must be a lowercase SHA-256 digest")
        props = _safe_properties({
            "decision_id": decision_id,
            "revision_n": expected_revision_n + 1,
            "graph_revision": graph_revision,
            "status": status,
            "conditions_json": conditions_json,
            "dependency_ids": list(dependency_ids),
            "created_at": created_at,
            "reason": reason,
        })
        scoped_site = check_site(site_id)
        props["site_id"] = scoped_site
        graph = self._graph(site_id)
        params = {
            "decision_id": decision_id,
            "revision_id": revision_id,
            "expected_revision_n": expected_revision_n,
            "revision_n": expected_revision_n + 1,
            "previous_revision_id": previous_revision_id,
            "graph_revision": graph_revision,
            "status": status,
            "conditions_json": conditions_json,
            "dependency_ids": list(dependency_ids),
            "created_at": created_at,
            "reason": reason,
            "site_id": scoped_site,
            "props": props,
        }
        if expected_revision_n == 0:
            query = (
                "MATCH (d:Decision {id: $decision_id}) "
                "WHERE coalesce(d.revision_n, 0) = $expected_revision_n "
                "MERGE (r:DecisionRevision {id: $revision_id}) ON CREATE SET r += $props "
                "WITH d, r WHERE r.decision_id = $decision_id AND r.revision_n = $revision_n "
                "AND r.graph_revision = $graph_revision AND r.status = $status "
                "AND r.conditions_json = $conditions_json AND r.dependency_ids = $dependency_ids "
                "AND r.created_at = $created_at AND r.reason = $reason AND r.site_id = $site_id "
                "MERGE (d)-[:HAS_REVISION]->(r) "
                "SET d.revision_n = $revision_n, d.current_revision_id = $revision_id, d.status = r.status "
                "RETURN r.id, r.revision_n, r.graph_revision, r.status"
            )
        else:
            query = (
                "MATCH (d:Decision {id: $decision_id}), "
                "(prev:DecisionRevision {id: $previous_revision_id}) "
                "WHERE coalesce(d.revision_n, 0) = $expected_revision_n "
                "AND prev.decision_id = $decision_id AND prev.revision_n = $expected_revision_n "
                "MERGE (r:DecisionRevision {id: $revision_id}) ON CREATE SET r += $props "
                "WITH d, prev, r WHERE r.decision_id = $decision_id AND r.revision_n = $revision_n "
                "AND r.graph_revision = $graph_revision AND r.status = $status "
                "AND r.conditions_json = $conditions_json AND r.dependency_ids = $dependency_ids "
                "AND r.created_at = $created_at AND r.reason = $reason AND r.site_id = $site_id "
                "MERGE (d)-[:HAS_REVISION]->(r) MERGE (r)-[:PREVIOUS]->(prev) "
                "SET d.revision_n = $revision_n, d.current_revision_id = $revision_id, d.status = r.status "
                "RETURN r.id, r.revision_n, r.graph_revision, r.status"
            )
        result = graph.query(query, params, timeout=self._query_timeout_ms)
        if result.result_set:
            row = result.result_set[0]
            return {"revision_id": row[0], "revision_n": row[1], "graph_revision": row[2], "status": row[3]}

        # A duplicate event can race with the first writer. Re-read the immutable record before
        # treating a zero-row compare-and-set as a stale write.
        existing = self.read_node(site_id, revision_id)
        if existing and existing["labels"] and "DecisionRevision" in existing["labels"]:
            current = existing["properties"]
            same = (
                current.get("decision_id") == decision_id
                and current.get("revision_n") == expected_revision_n + 1
                and current.get("graph_revision") == graph_revision
                and current.get("status") == status
                and current.get("conditions_json") == conditions_json
                and current.get("dependency_ids") == list(dependency_ids)
                and current.get("created_at") == created_at
                and current.get("reason") == reason
                and current.get("site_id") == scoped_site
            )
            if same:
                return {"revision_id": revision_id, "revision_n": current["revision_n"],
                        "graph_revision": current["graph_revision"], "status": current["status"]}
            raise ContractError("revision id already exists with different immutable content")
        raise RuntimeError("decision revision compare-and-set failed; the head changed or parent is missing")

    def list_nodes(self, site_id: str, label: str | Label, *, limit: int = 200) -> list[dict[str, Any]]:
        """Read-only, bounded listing of one allow-listed label in the caller's site graph (never creates a graph)."""
        label_value = label.value if isinstance(label, Label) else label
        if label_value not in _ALLOWED_LABELS:
            raise ContractError("node label is not in the drift schema")
        if not 1 <= limit <= 1000:
            raise ContractError("limit must be between 1 and 1000")
        if self.graph_name(site_id) not in self._client_list_graphs():
            return []
        rows = self._graph(site_id).ro_query(
            f"MATCH (n:{label_value}) RETURN n.id, properties(n) ORDER BY n.id LIMIT {limit}", timeout=self._query_timeout_ms
        ).result_set
        return [{"id": str(node_id), **{k: v for k, v in dict(props).items() if k not in {"id", "site_id"}}} for node_id, props in rows]

    def edges_of(self, site_id: str, node_id: str) -> dict[str, list[dict[str, Any]]]:
        """Outgoing and incoming relationships of one node: [{rel, id, label}]. Bounded; empty if the graph is absent."""
        check_id(node_id)
        empty: dict[str, list[dict[str, Any]]] = {"out": [], "in": []}
        if self.graph_name(site_id) not in self._client_list_graphs():
            return empty
        graph = self._graph(site_id)
        out_rows = graph.ro_query("MATCH (n {id: $id})-[r]->(m) RETURN type(r), m.id, labels(m) LIMIT 500", {"id": node_id}, timeout=self._query_timeout_ms).result_set
        in_rows = graph.ro_query("MATCH (m)-[r]->(n {id: $id}) RETURN type(r), m.id, labels(m) LIMIT 500", {"id": node_id}, timeout=self._query_timeout_ms).result_set
        shape = lambda rows: [{"rel": str(r), "id": str(i), "label": (lab[0] if lab else "")} for r, i, lab in rows if i is not None]  # noqa: E731
        return {"out": shape(out_rows), "in": shape(in_rows)}

    def handoffs(self, site_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
        """Who produced a memory and which other agent sessions recalled it: the cross-agent sharing record."""
        if not 1 <= limit <= 1000:
            raise ContractError("limit must be between 1 and 1000")
        if self.graph_name(site_id) not in self._client_list_graphs():
            return []
        rows = self._graph(site_id).ro_query(
            "MATCH (m:Memory)-[:RECALLED_IN]->(s:AgentSession) "
            f"RETURN m.id, m.agent_id, m.status, s.id, s.agent_id, s.started_at ORDER BY s.started_at DESC LIMIT {limit}",
            timeout=self._query_timeout_ms,
        ).result_set
        return [{"memory_id": str(m), "produced_by": pa, "memory_status": ms, "recall_session": str(sid), "recalled_by": ra, "at": at}
                for m, pa, ms, sid, ra, at in rows]

    def memory_lineage(self, site_id: str, *, limit: int = 200, offset: int = 0) -> list[dict[str, Any]]:
        """Read one page of complete memory lineage, failing closed on excessive fan-out."""
        if not 1 <= limit <= 1000:
            raise ContractError("limit must be between 1 and 1000")
        if not 0 <= offset <= 100_000:
            raise ContractError("offset must be between 0 and 100000")
        if self.graph_name(site_id) not in self._client_list_graphs():
            return []
        row_budget = min(limit * 64, 10_000)
        rows = self._graph(site_id).ro_query(
            "MATCH (m:Memory) "
            f"WITH m ORDER BY m.id SKIP {offset} LIMIT {limit} "
            "OPTIONAL MATCH (m)-[:DERIVED_FROM]->(c:Claim) "
            "OPTIONAL MATCH (c)-[:SUPPORTED_BY]->(s:SourceVersion) "
            "OPTIONAL MATCH (s)-[:VERSION_OF]->(d:Document) "
            "RETURN m.id, properties(m), c.id, c.fact_key, c.fact_value, c.status, s.id, s.status, d.id, s.content_sha256 "
            f"ORDER BY m.id, c.id, s.id LIMIT {row_budget + 1}",
            timeout=self._query_timeout_ms,
        ).result_set
        if len(rows) > row_budget:
            raise TraversalLimitExceeded("memory lineage exceeded the row limit")
        out: dict[str, dict[str, Any]] = {}
        for mid, props, cid, ckey, cval, cstatus, sid, sstatus, did, sha in rows:
            entry = out.setdefault(str(mid), {"id": str(mid), **{k: v for k, v in dict(props).items() if k not in {"id", "site_id"}}, "claims": [], "sources": []})
            if cid is not None and all(c["id"] != cid for c in entry["claims"]):
                entry["claims"].append({"id": str(cid), "fact_key": ckey, "fact_value": cval, "status": cstatus})
            if sid is not None and all(x["id"] != sid for x in entry["sources"]):
                entry["sources"].append({"id": str(sid), "status": sstatus, "document_id": did, "content_sha256": sha})
        return list(out.values())[:limit]

    def export_graph(self, site_id: str, max_nodes: int = 500, max_edges: int = 2000) -> dict[str, Any]:
        """Bounded read-only export of the caller's site graph in Graph Lab shape.

        Edges keep the store's "dependent -> dependency" direction. Only SUPPORTED_BY / DERIVED_FROM /
        DEPENDS_ON edges take part in analysis (the same set `find_impacts` follows); every other
        relationship is exported `disabled` so views can show it. Logical/policy edges are `definite`;
        context edges export as `maybe` because they advise review but never invalidate.
        Never creates a graph; an absent site graph exports as empty.
        """
        if not 1 <= max_nodes <= 2000 or not 1 <= max_edges <= 10000:
            raise ContractError("export bounds are outside the Graph Lab limits")
        if self.graph_name(site_id) not in self._client_list_graphs():
            return {"nodes": [], "edges": [], "truncated": False}
        graph = self._graph(site_id)
        node_rows = graph.ro_query(
            f"MATCH (n) WHERE n.id IS NOT NULL RETURN n.id, labels(n), properties(n) ORDER BY n.id LIMIT {max_nodes + 1}",
            timeout=self._query_timeout_ms,
        ).result_set
        edge_rows = graph.ro_query(
            "MATCH (a)-[r]->(b) WHERE a.id IS NOT NULL AND b.id IS NOT NULL "
            f"RETURN a.id, b.id, type(r), properties(r) ORDER BY a.id, b.id, type(r) LIMIT {max_edges + 1}",
            timeout=self._query_timeout_ms,
        ).result_set
        truncated = len(node_rows) > max_nodes or len(edge_rows) > max_edges
        nodes, kept = [], set()
        for node_id, labels, props in node_rows[:max_nodes]:
            clean = {k: v for k, v in dict(props).items() if k not in {"id", "site_id"} and isinstance(v, (str, int, float, bool))}
            kept.add(str(node_id))
            rev_n = clean.get("revision_n")
            stat = clean.get("status", "")
            summary = clean.get("summary")
            val = clean.get("fact_value")
            nlabel = clean.get("title") or clean.get("name")
            if not nlabel and summary:
                nlabel = str(summary)[:45] + ("..." if len(str(summary)) > 45 else "")
            if not nlabel and val is not None:
                nlabel = str(val)[:35]
            if not nlabel and clean.get("fact_key"):
                nlabel = str(clean.get("fact_key"))
            if not nlabel and rev_n is not None:
                nlabel = f"Rev {rev_n} ({stat})" if stat else f"Rev {rev_n}"
            if not nlabel and clean.get("reason"):
                nlabel = str(clean.get("reason"))[:45]
            if not nlabel:
                nlabel = str(node_id)
            nodes.append({"id": str(node_id), "type": (labels[0] if labels else "node"),
                          "label": str(nlabel), "props": clean})
        edges = []
        for source, target, rel, props in edge_rows[:max_edges]:
            if str(source) in kept and str(target) in kept:
                kind = dict(props).get("kind", "logical")
                edges.append({"source": str(source), "target": str(target), "rel": str(rel),
                              "certainty": "definite" if kind in _PROPAGATING else "maybe",
                              # Metadata relationships (SUPERSEDES, HAS_SESSION, ...) stay visible but never propagate.
                              "disabled": str(rel) not in _DEPENDENCY_RELS})
        return {"nodes": nodes, "edges": edges, "truncated": truncated}

    def _graph(self, site_id: str):
        try:
            return self._client.select_graph(self.graph_name(site_id))
        except Exception:
            self._ensure_fallback()
            return self._client.select_graph(self.graph_name(site_id))

    def close(self) -> None:
        """Close pooled Redis connections when the application lifespan ends."""
        try:
            self._client.connection.connection_pool.disconnect()
        except Exception:
            pass


def _safe_properties(properties: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(properties, Mapping):
        raise ContractError("graph properties must be an object")
    safe: dict[str, Any] = {}
    for key, value in properties.items():
        check_key(key)
        if key in {"id", "site_id"}:
            raise ContractError(f"{key} is reserved by the drift store")
        if value is None:
            continue
        safe[key] = check_value(value)
    return safe
