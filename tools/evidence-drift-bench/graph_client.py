"""FalkorDB graph loader and parameterized traversal queries."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from urllib.parse import urlsplit

from falkordb import FalkorDB
from oracle import TRAVERSABLE_RELATION_KINDS

NODE_LOAD_QUERY = """
UNWIND $nodes AS row
MERGE (node:BenchmarkNode {id: row.id})
SET node += row.properties
"""

RELATIONSHIP_LOAD_QUERY = """
UNWIND $relationships AS row
MATCH (source:BenchmarkNode {id: row.source})
MATCH (target:BenchmarkNode {id: row.target})
MERGE (source)-[relationship:BENCH_REL {kind: row.kind}]->(target)
"""

IMPACT_QUERY = """
MATCH (tenant:BenchmarkNode {id: $tenant_node_id, kind: 'tenant'})
      -[:BENCH_REL {kind: 'OWNS'}]->(source:BenchmarkNode {id: $source_id, kind: 'evidence'})
MATCH (tenant)-[:BENCH_REL {kind: 'OWNS'}]->(decision:BenchmarkNode {kind: 'decision'})
MATCH path = (source)-[:BENCH_REL*1..12]->(decision)
WHERE source.invalidated = true
  AND all(edge IN relationships(path) WHERE edge.kind IN $traversable_kinds)
RETURN DISTINCT decision.id
"""

CURRENT_SUPPORT_QUERY = """
MATCH (tenant:BenchmarkNode {id: $tenant_node_id, kind: 'tenant'})
      -[:BENCH_REL {kind: 'OWNS'}]->(evidence:BenchmarkNode {kind: 'evidence', current: true})
MATCH (tenant)-[:BENCH_REL {kind: 'OWNS'}]->(decision:BenchmarkNode {kind: 'decision'})
MATCH (evidence)-[:BENCH_REL {kind: 'SUPPORTS'}]->(decision)
RETURN DISTINCT decision.id
"""

CONFLICT_QUERY = """
MATCH (tenant:BenchmarkNode {id: $tenant_node_id, kind: 'tenant'})
      -[:BENCH_REL {kind: 'OWNS'}]->(evidence:BenchmarkNode {id: $updated_id, kind: 'evidence'})
MATCH (tenant)-[:BENCH_REL {kind: 'OWNS'}]->(decision:BenchmarkNode {kind: 'decision'})
MATCH (evidence)-[:BENCH_REL {kind: 'CHALLENGES'}]->(decision)
RETURN DISTINCT decision.id
"""

MEMORY_QUERY = """
MATCH (tenant:BenchmarkNode {id: $tenant_node_id, kind: 'tenant'})
      -[:BENCH_REL {kind: 'OWNS'}]->(evidence:BenchmarkNode {id: $source_id, kind: 'evidence'})
MATCH (tenant)-[:BENCH_REL {kind: 'OWNS'}]->(memory:BenchmarkNode {kind: 'memory'})
MATCH (evidence)-[:BENCH_REL {kind: 'MEMORY_SOURCE'}]->(memory)
WHERE evidence.invalidated = true
RETURN DISTINCT memory.id
"""

NODE_COUNT_QUERY = "MATCH (node:BenchmarkNode) RETURN count(node)"
RELATIONSHIP_COUNT_QUERY = "MATCH ()-[relationship:BENCH_REL]->() RETURN count(relationship)"


def validate_test_uri(uri: str, allow_remote: bool = False) -> None:
    """Reject non-local graph targets unless explicitly marked as a test server."""
    parsed = urlsplit(uri)
    if parsed.scheme not in {"redis", "rediss"} or not parsed.hostname:
        raise ValueError("FalkorDB URL must use redis:// or rediss:// and include a host")
    if not allow_remote and parsed.hostname.casefold() not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Remote FalkorDB is blocked by default; use a dedicated test server and --allow-remote-test-db")


def connect_falkordb(uri: str, allow_remote: bool = False) -> FalkorDB:
    """Connect with finite timeouts after applying the test-target guard."""
    validate_test_uri(uri, allow_remote=allow_remote)
    return FalkorDB(url=uri, socket_connect_timeout=2.0, socket_timeout=10.0, client_name="evidence-drift-bench")


def tenant_node_id(scenario: dict[str, Any]) -> str:
    """Return the graph node identifier for a scenario's owning tenant."""
    return next(
        node["id"]
        for node in scenario["nodes"]
        if node["kind"] == "tenant" and node.get("tenant_id") == scenario["tenant_id"]
    )


class FalkorGraphRunner:
    """Load fixtures and measure their invalidation results in one test graph."""

    def __init__(self, graph: Any) -> None:
        """Wrap the selected FalkorDB graph handle."""
        self.graph = graph

    def load_scenarios(self, scenarios: Iterable[dict[str, Any]], batch_size: int = 250) -> None:
        """Load nodes and relationships with parameterized, idempotent Cypher."""
        scenario_list = list(scenarios)
        nodes = [
            {"id": node["id"], "properties": {key: value for key, value in node.items() if key != "id"}}
            for scenario in scenario_list
            for node in scenario["nodes"]
        ]
        relationships = [
            relationship
            for scenario in scenario_list
            for relationship in scenario["relationships"]
        ]
        for batch in _batches(nodes, batch_size):
            self.graph.query(NODE_LOAD_QUERY, {"nodes": batch})
        for batch in _batches(relationships, batch_size):
            self.graph.query(RELATIONSHIP_LOAD_QUERY, {"relationships": batch})

    def evaluate_scenario(self, scenario: dict[str, Any]) -> dict[str, Any]:
        """Run scoped impact, current support, conflict, and memory traversals."""
        params = {
            "tenant_node_id": tenant_node_id(scenario),
            "source_id": scenario["source_evidence_id"],
            "updated_id": scenario["updated_evidence_id"],
            "traversable_kinds": sorted(TRAVERSABLE_RELATION_KINDS),
        }
        candidates = _column_values(self.graph.query(IMPACT_QUERY, params))
        supported = _column_values(self.graph.query(CURRENT_SUPPORT_QUERY, params))
        challenged = _column_values(self.graph.query(CONFLICT_QUERY, params))
        invalid_memories = _column_values(self.graph.query(MEMORY_QUERY, params))
        impacted = (candidates - supported) | challenged
        memory_valid = all(memory_id not in invalid_memories for memory_id in scenario["expected_memory_ids"])
        return {
            "affected_decisions": sorted(impacted),
            "memory_valid": memory_valid,
            "invalidated_memory_ids": sorted(invalid_memories),
        }

    def graph_counts(self) -> dict[str, int]:
        """Return actual node and relationship counts from FalkorDB."""
        nodes = self.graph.query(NODE_COUNT_QUERY).result_set[0][0]
        relationships = self.graph.query(RELATIONSHIP_COUNT_QUERY).result_set[0][0]
        return {"nodes": int(nodes), "relationships": int(relationships)}


def _batches(values: list[dict[str, Any]], batch_size: int) -> Iterable[list[dict[str, Any]]]:
    for start in range(0, len(values), batch_size):
        yield values[start : start + batch_size]


def _column_values(result: Any) -> set[str]:
    return {str(row[0]) for row in result.result_set}
