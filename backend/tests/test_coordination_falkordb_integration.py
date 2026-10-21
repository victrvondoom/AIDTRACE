"""Opt-in FalkorDB test. Uses a fresh graph namespace and never reads default app settings."""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from api.services.coordination.contracts import Run, Task, TaskStatus
from api.services.coordination.graph_store import CoordinationGraphStore
from api.services.drift.store import FalkorDriftStore


def test_coordination_persists_and_claims_atomically_on_isolated_falkordb() -> None:
    url = os.environ.get("AIDTRACE_COORDINATION_TEST_URL", "").strip()
    if not url:
        pytest.skip("set AIDTRACE_COORDINATION_TEST_URL to a disposable FalkorDB instance")

    namespace = uuid4().hex[:16]
    site_id = f"coordtest_{namespace}"
    drift = FalkorDriftStore(url, graph_prefix=f"aidtrace_coord_test_{namespace}")
    first = CoordinationGraphStore(drift_store=drift, site_id=site_id)
    run = Run(run_id=f"run_{namespace}", site_id=site_id, campaign_goal="isolated persistence check", domain="test")
    first.create_run(run)
    first.create_task(Task(task_id=f"task_{namespace}", run_id=run.run_id, domain="test",
                           capability_id="core.read", goal="isolated atomic claim", status=TaskStatus.READY))

    def claim(index: int) -> bool:
        return first.claim_task(f"task_{namespace}", f"worker_{index}", "2099-01-01T00:00:00+00:00")

    with ThreadPoolExecutor(max_workers=8) as pool:
        claims = list(pool.map(claim, range(8)))
    assert sum(claims) == 1

    restarted_view = CoordinationGraphStore(drift_store=drift, site_id=site_id)
    persisted_run = restarted_view.get_run(run.run_id)
    persisted_task = restarted_view.get_task(f"task_{namespace}")
    assert persisted_run is not None
    assert persisted_run.task_ids == [f"task_{namespace}"]
    assert persisted_task is not None
    assert persisted_task.status == TaskStatus.CLAIMED

    # The unique graph prefix and site id are intentionally left intact for forensic inspection.
