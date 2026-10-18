"""FalkorDB persistence for the Kairos Evidence Drift dependency graph.

This store is intentionally separate from Kairos's Neo4j asset/document graph. A caller must pass
the authenticated site's scope; graph selection is derived from that scope, and every Cypher value
is parameterized. Do not pass a query-string site id here.
"""
from __future__ import annotations

import re
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

_GRAPH_PART = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_ALLOWED_LABELS = {label.value for label in Label}
_ALLOWED_RELS = {rel.value for rel in Rel}
_DEPENDENCY_RELS = tuple(sorted(DEPENDENCY_RELS))
_PROPAGATING = tuple(sorted(PROPAGATING_KINDS))


class TraversalLimitExceeded(RuntimeError):
    """Impact discovery exceeded its configured edge budget; callers must fail closed."""


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
        self._client = client or FalkorDB.from_url(url, socket_timeout=query_timeout_ms / 1000)
        self._graph_prefix = graph_prefix
        self._query_timeout_ms = query_timeout_ms
        self._max_depth = max_depth
        self._max_edges = max_edges

    def graph_name(self, site_id: str) -> str:
        """Select one graph for the token-derived Kairos site scope."""
        scope = check_site(site_id)
        return f"{self._graph_prefix}__{scope}"

    def inspect_site(self, site_id: str | None) -> dict[str, bool]:
        """Read connection and site-graph readiness without creating or changing a graph."""
        graphs = set(self._client.list_graphs())
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

    def find_impacts(self, site_id: str, changed_ids: Sequence[str] | set[str]) -> list[ImpactPath]:
        """Read bounded one-hop edges from FalkorDB, then apply the deterministic Python closure."""
        roots = sorted({check_id(node_id, "changed_id") for node_id in changed_ids})
        if not roots:
            return []
        if self.graph_name(site_id) not in self._client.list_graphs():
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
        if self.graph_name(site_id) not in self._client.list_graphs():
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
            "props": props,
        }
        if expected_revision_n == 0:
            query = (
                "MATCH (d:Decision {id: $decision_id}) "
                "WHERE coalesce(d.revision_n, 0) = $expected_revision_n "
                "MERGE (r:DecisionRevision {id: $revision_id}) ON CREATE SET r += $props "
                "WITH d, r WHERE r.decision_id = $decision_id AND r.revision_n = $revision_n "
                "AND r.graph_revision = $graph_revision "
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
                "AND r.graph_revision = $graph_revision "
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
            )
            if same:
                return {"revision_id": revision_id, "revision_n": current["revision_n"],
                        "graph_revision": current["graph_revision"], "status": current["status"]}
            raise ContractError("revision id already exists with different immutable content")
        raise RuntimeError("decision revision compare-and-set failed; the head changed or parent is missing")

    def _graph(self, site_id: str):
        return self._client.select_graph(self.graph_name(site_id))

    def close(self) -> None:
        """Close pooled Redis connections when the application lifespan ends."""
        self._client.connection.connection_pool.disconnect()


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
