"""Pure, bounded dependency-impact traversal for Evidence Drift Cascade.

Graph persistence belongs in the FalkorDB adapter. This module owns the deterministic rule for
which downstream records a material evidence change can affect, so it can be tested independently
of a database or model provider.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .model import ContractError, EdgeKind, PROPAGATING_KINDS, check_id


@dataclass(frozen=True)
class DependencyEdge:
    """A dependent record and the record it relies on."""

    dependent_id: str
    dependency_id: str
    kind: str = EdgeKind.LOGICAL.value

    def __post_init__(self) -> None:
        check_id(self.dependent_id, "dependent_id")
        check_id(self.dependency_id, "dependency_id")
        if self.kind not in {kind.value for kind in EdgeKind}:
            raise ContractError(f"unknown dependency kind: {self.kind}")


@dataclass(frozen=True)
class ImpactPath:
    """Shortest dependency chain from a changed record to one affected dependent."""

    node_id: str
    depth: int
    path: tuple[str, ...]

    def as_dict(self) -> dict:
        return {"node_id": self.node_id, "depth": self.depth, "path": list(self.path)}


def find_impacted_dependents(
    changed_ids: list[str] | tuple[str, ...] | set[str],
    edges: list[DependencyEdge] | tuple[DependencyEdge, ...],
    *,
    max_depth: int = 12,
) -> list[ImpactPath]:
    """Return affected dependents in deterministic breadth-first order.

    Edges point from dependent to dependency, so the traversal builds a reverse adjacency map and
    walks from changed evidence toward decisions, memories, plans, and action proposals. Context
    edges are deliberately excluded: they can prompt review, but do not prove invalidation.
    For multiple shortest paths, the lexicographically first path is retained for reproducible
    explanations. Changed roots themselves are not returned.
    """
    if not isinstance(max_depth, int) or isinstance(max_depth, bool) or max_depth < 1:
        raise ContractError("max_depth must be a positive integer")

    roots = sorted({check_id(node_id, "changed_id") for node_id in changed_ids})
    reverse: dict[str, list[str]] = {}
    for edge in edges:
        if edge.kind in PROPAGATING_KINDS:
            reverse.setdefault(edge.dependency_id, []).append(edge.dependent_id)
    for dependents in reverse.values():
        dependents.sort()

    queue = deque((root, 0, (root,)) for root in roots)
    best: dict[str, tuple[int, tuple[str, ...]]] = {}
    while queue:
        current_id, depth, path = queue.popleft()
        if depth >= max_depth:
            continue
        for dependent_id in reverse.get(current_id, ()):
            next_depth = depth + 1
            next_path = (*path, dependent_id)
            previous = best.get(dependent_id)
            if previous is not None and (previous[0], previous[1]) <= (next_depth, next_path):
                continue
            best[dependent_id] = (next_depth, next_path)
            queue.append((dependent_id, next_depth, next_path))

    return [
        ImpactPath(node_id=node_id, depth=depth, path=path)
        for node_id, (depth, path) in sorted(best.items(), key=lambda item: (item[1][0], item[0]))
        if node_id not in roots
    ]
