"""Independent Python oracle for evidence drift fixtures."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

TRAVERSABLE_RELATION_KINDS = frozenset({"SUPPORTS", "DEPENDS_ON", "APPROVES", "DESCRIBES"})
MAX_DEPENDENCY_HOPS = 12


def expected_impact(scenario: dict[str, Any]) -> set[str]:
    """Return the scenario's independently declared impacted decision IDs."""
    return set(scenario["expected_affected_decisions"])


def reference_impact(scenario: dict[str, Any]) -> set[str]:
    """Traverse fixture edges in Python and apply invalidation and support rules."""
    nodes = {node["id"]: node for node in scenario["nodes"]}
    outgoing: dict[str, list[dict[str, str]]] = defaultdict(list)
    for relationship in scenario["relationships"]:
        outgoing[relationship["source"]].append(relationship)

    source = nodes[scenario["source_evidence_id"]]
    candidates: set[str] = set()
    if source.get("invalidated") is True:
        queue = deque([(source["id"], 0)])
        visited = {source["id"]}
        while queue:
            current_id, depth = queue.popleft()
            if depth >= MAX_DEPENDENCY_HOPS:
                continue
            for relationship in outgoing[current_id]:
                if relationship["kind"] not in TRAVERSABLE_RELATION_KINDS:
                    continue
                next_id = relationship["target"]
                next_node = nodes[next_id]
                if next_node["kind"] == "decision" and next_node["tenant_id"] == scenario["tenant_id"]:
                    candidates.add(next_id)
                if next_id not in visited:
                    visited.add(next_id)
                    queue.append((next_id, depth + 1))

    independently_supported = {
        relationship["target"]
        for node in scenario["nodes"]
        if node["kind"] == "evidence" and node.get("current") is True and node["id"] != source["id"]
        for relationship in outgoing[node["id"]]
        if relationship["kind"] == "SUPPORTS"
        and nodes[relationship["target"]]["kind"] == "decision"
        and nodes[relationship["target"]]["tenant_id"] == scenario["tenant_id"]
    }
    challenged = {
        relationship["target"]
        for relationship in outgoing[scenario["updated_evidence_id"]]
        if relationship["kind"] == "CHALLENGES"
        and nodes[relationship["target"]]["kind"] == "decision"
        and nodes[relationship["target"]]["tenant_id"] == scenario["tenant_id"]
    }
    return (candidates - independently_supported) | challenged


def reference_memory_valid(scenario: dict[str, Any]) -> bool:
    """Return whether every declared memory remains supported by current evidence."""
    nodes = {node["id"]: node for node in scenario["nodes"]}
    source = nodes[scenario["source_evidence_id"]]
    invalidated_memory_ids = {
        relationship["target"]
        for relationship in scenario["relationships"]
        if source.get("invalidated") is True
        and relationship["source"] == source["id"]
        and relationship["kind"] == "MEMORY_SOURCE"
    }
    return all(
        nodes[memory_id].get("initially_valid", False) and memory_id not in invalidated_memory_ids
        for memory_id in scenario["expected_memory_ids"]
    )


def validate_scenario_oracle(scenario: dict[str, Any]) -> dict[str, Any]:
    """Check that the explicit oracle agrees with the independent traversal."""
    expected = expected_impact(scenario)
    reference = reference_impact(scenario)
    affected = set(scenario["expected_affected_decisions"])
    unaffected = set(scenario["expected_unaffected_decisions"])
    declared_decisions = {
        node["id"] for node in scenario["nodes"] if node["kind"] == "decision"
    }
    memory_valid = reference_memory_valid(scenario)
    return {
        "scenario_id": scenario["scenario_id"],
        "impact_matches": reference == expected,
        "memory_matches": memory_valid is scenario["expected_memory_valid"],
        "sets_are_disjoint": not (affected & unaffected),
        "decision_sets_complete": affected | unaffected == declared_decisions,
        "reference_impacted_decisions": sorted(reference),
    }


def validate_fixture_document(document: dict[str, Any]) -> dict[str, Any]:
    """Validate all scenario fields and oracle results before database access."""
    required = {
        "scenario_id",
        "scenario_type",
        "tenant_id",
        "nodes",
        "relationships",
        "original_evidence",
        "updated_evidence",
        "events",
        "expected_affected_decisions",
        "expected_unaffected_decisions",
        "expected_memory_valid",
        "explanation",
    }
    missing_fields: list[str] = []
    checks: list[dict[str, Any]] = []
    for scenario in document["scenarios"]:
        missing_fields.extend(
            f"{scenario.get('scenario_id', '<unknown>')}:{field}"
            for field in sorted(required - scenario.keys())
        )
        checks.append(validate_scenario_oracle(scenario))
    failed = [check["scenario_id"] for check in checks if not all(
        check[key]
        for key in ("impact_matches", "memory_matches", "sets_are_disjoint", "decision_sets_complete")
    )]
    return {
        "status": "PASS" if not missing_fields and not failed else "FAIL",
        "scenario_count": len(document["scenarios"]),
        "scenario_checks_passed": len(checks) - len(failed),
        "missing_fields": missing_fields,
        "failed_scenarios": failed,
    }
