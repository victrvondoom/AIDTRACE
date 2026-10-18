from __future__ import annotations

import pytest

from api.services.drift.engine import DependencyEdge, find_impacted_dependents
from api.services.drift.model import ContractError, EdgeKind


def test_cascade_finds_direct_and_transitive_dependents() -> None:
    edges = [
        DependencyEdge("claim-new", "source-old"),
        DependencyEdge("memory-a", "claim-new"),
        DependencyEdge("decision-a", "memory-a"),
        DependencyEdge("action-a", "decision-a", EdgeKind.POLICY.value),
    ]

    impacts = find_impacted_dependents(["source-old"], edges)

    assert [item.node_id for item in impacts] == ["claim-new", "memory-a", "decision-a", "action-a"]
    assert impacts[-1].path == ("source-old", "claim-new", "memory-a", "decision-a", "action-a")


def test_context_edges_do_not_invalidate_dependents() -> None:
    impacts = find_impacted_dependents(
        ["evidence"],
        [DependencyEdge("decision", "evidence", EdgeKind.CONTEXT.value)],
    )

    assert impacts == []


def test_depth_bound_stops_cascade() -> None:
    edges = [DependencyEdge("a", "root"), DependencyEdge("b", "a"), DependencyEdge("c", "b")]

    impacts = find_impacted_dependents(["root"], edges, max_depth=2)

    assert [item.node_id for item in impacts] == ["a", "b"]


def test_shortest_path_is_stable_for_multiple_roots_and_cycles() -> None:
    edges = [
        DependencyEdge("joined", "root-b"),
        DependencyEdge("joined", "root-a"),
        DependencyEdge("root-a", "joined"),
    ]

    impacts = find_impacted_dependents(["root-b", "root-a"], edges)

    assert [item.node_id for item in impacts] == ["joined"]
    assert impacts[0].path == ("root-a", "joined")


@pytest.mark.parametrize("max_depth", [0, -1, True, 1.5])
def test_invalid_depth_is_rejected(max_depth: int) -> None:
    with pytest.raises(ContractError):
        find_impacted_dependents(["evidence"], [], max_depth=max_depth)


def test_invalid_edge_kind_is_rejected() -> None:
    with pytest.raises(ContractError):
        DependencyEdge("decision", "claim", "background-ish")
