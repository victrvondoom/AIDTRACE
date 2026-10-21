"""Provenance helpers whose outputs never promote a source into verified evidence."""
from __future__ import annotations

from typing import Any


def evaluate_source_independence(sources: list[dict[str, Any]]) -> dict[str, Any]:
    """Estimate distinct source families from explicit ancestry and content identifiers.

    Missing provenance remains one citation per source; this function never guesses ancestry
    from URLs or text similarity. It is a de-duplication aid, not a verification decision.
    """
    count = len(sources)
    if not count:
        return {"total_citations": 0, "independent_families": 0,
                "duplicate_citations_discounted": 0, "inflation_ratio": 0.0,
                "is_syndicated_reprint": False, "method": "explicit provenance only"}
    parent = list(range(count))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    lookup: dict[tuple[str, str], int] = {}
    ids: dict[str, int] = {}
    for index, source in enumerate(sources):
        source_id = str(source.get("source_id") or source.get("id") or "").strip()
        if source_id:
            ids[source_id] = index
        for field in ("origin_family_id", "canonical_source_id", "content_sha256"):
            value = str(source.get(field) or "").strip().casefold()
            if value:
                token = (field, value)
                if token in lookup:
                    union(index, lookup[token])
                else:
                    lookup[token] = index
    for index, source in enumerate(sources):
        ancestor = str(source.get("derived_from_source_id") or "").strip()
        if ancestor in ids:
            union(index, ids[ancestor])

    groups: dict[int, list[str]] = {}
    for index, source in enumerate(sources):
        label = str(source.get("source_id") or source.get("id") or f"citation_{index + 1}")
        groups.setdefault(find(index), []).append(label)
    families = list(groups.values())
    independent = len(families)
    return {
        "total_citations": count,
        "independent_families": independent,
        "duplicate_citations_discounted": count - independent,
        "inflation_ratio": round(count / independent, 3) if independent else 0.0,
        "is_syndicated_reprint": independent < count,
        "families": families,
        "method": "connected components of shared family, canonical source, hash, or explicit ancestry",
        "verification_effect": "none; source authority and validity require separate checks",
    }


class GovernedDeletionUnavailable(RuntimeError):
    """Broad verified deletion is not implemented across Kairos storage layers."""


class VerifiedUnlearningEngine:
    """Compatibility shell that fails closed instead of issuing a false deletion receipt."""

    def __init__(self, store: Any) -> None:
        self.store = store

    def verified_delete(self, **_: Any) -> None:
        raise GovernedDeletionUnavailable(
            "Verified deletion is unavailable until retention policy, every storage layer, indexes, "
            "authorization, and re-query verification are integrated. No data was changed."
        )
