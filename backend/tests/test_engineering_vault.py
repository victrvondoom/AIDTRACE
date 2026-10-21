"""Engineering memory must return a complete vault view or fail closed."""
from __future__ import annotations

import json

import pytest

from api.services.drift.store import TraversalLimitExceeded
from api.services.memory.engineering_vault import EngineeringMemoryVault, EngineeringVaultIncomplete


class PagedLineageStore:
    def __init__(self, items: list[dict], *, fail_offset: int | None = None) -> None:
        self.items = items
        self.fail_offset = fail_offset
        self.offsets: list[int] = []

    def memory_lineage(self, site_id: str, *, limit: int, offset: int = 0) -> list[dict]:
        self.offsets.append(offset)
        if self.fail_offset == offset:
            raise ConnectionError("test graph unavailable")
        return self.items[offset:offset + limit]


class MemoryStub:
    def __init__(self, store: PagedLineageStore) -> None:
        self.store = store


def _memory(index: int) -> dict:
    return {
        "id": f"memory-{index}",
        "memory_kind": "PROCEDURAL",
        "status": "VALID",
        "summary": f"Judgment {index}",
        "details": json.dumps({"tags": ["test"]}),
        "claims": [{"fact_key": "engineering.judgment", "fact_value": f"Keep rule {index}"}],
    }


def test_snapshot_pages_all_engineering_memories() -> None:
    store = PagedLineageStore([_memory(index) for index in range(1005)])
    snapshot = EngineeringMemoryVault(MemoryStub(store), "eng_test").snapshot()
    assert snapshot["complete"] is True
    assert snapshot["total_memories_scanned"] == 1005
    assert len(snapshot["memories"]) == 1005
    assert store.offsets == [0, 1000]


def test_snapshot_fails_closed_when_memory_read_breaks_mid_page() -> None:
    store = PagedLineageStore([_memory(index) for index in range(1005)], fail_offset=1000)
    with pytest.raises(ConnectionError, match="unavailable"):
        EngineeringMemoryVault(MemoryStub(store), "eng_test").snapshot()


def test_snapshot_reports_lineage_query_limits_as_incomplete_vault() -> None:
    class LimitStore:
        def memory_lineage(self, site_id: str, *, limit: int, offset: int = 0) -> list[dict]:
            raise TraversalLimitExceeded("fanout limit")

    with pytest.raises(EngineeringVaultIncomplete, match="query safety limit"):
        EngineeringMemoryVault(MemoryStub(LimitStore()), "eng_test").snapshot()


def test_snapshot_rejects_vault_beyond_complete_export_bound() -> None:
    store = PagedLineageStore([_memory(index) for index in range(10_001)])
    with pytest.raises(EngineeringVaultIncomplete, match="no partial recall"):
        EngineeringMemoryVault(MemoryStub(store), "eng_test").snapshot()


def test_recall_excludes_invalidated_judgments() -> None:
    current = _memory(1)
    obsolete = _memory(2)
    obsolete["status"] = "STALE"
    store = PagedLineageStore([current, obsolete])
    result = EngineeringMemoryVault(MemoryStub(store), "eng_test").recall("Keep rule")
    assert result["total_matching"] == 1
    assert [item["id"] for item in result["memories"]] == ["memory-1"]
