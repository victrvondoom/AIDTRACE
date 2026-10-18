from __future__ import annotations

import os
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_current_user, get_falkor_drift_store
from api.routers.resolveai import router as resolveai_router
from api.services.drift.demo_workflow import run_evidence_supersession
from api.services.drift.model import Label, Rel
from api.services.drift.store import FalkorDriftStore, TraversalLimitExceeded


@pytest.fixture
def local_drift_store():
    url = os.getenv("FALKORDB_TEST_URL")
    if not url:
        pytest.skip("set FALKORDB_TEST_URL to run local FalkorDB integration coverage")
    prefix = f"pytest_{uuid.uuid4().hex[:12]}"
    store = FalkorDriftStore(url, graph_prefix=prefix, query_timeout_ms=5000, max_depth=8)
    sites = [f"site_{uuid.uuid4().hex[:8]}", f"site_{uuid.uuid4().hex[:8]}"]
    try:
        yield store, sites
    finally:
        for site_id in sites:
            if store.graph_name(site_id) in store._client.list_graphs():
                store._graph(site_id).delete()
        store.close()


def test_local_falkordb_upsert_link_and_bounded_impact_are_site_scoped(local_drift_store) -> None:
    store, (site_a, site_b) = local_drift_store
    store.upsert_node(site_a, Label.SOURCE_VERSION, "source-v1", {"status": "ACTIVE"})
    store.upsert_node(site_a, Label.CLAIM, "claim-1", {"status": "ACTIVE"})
    store.upsert_node(site_a, Label.MEMORY, "memory-1", {"status": "VALID"})
    store.upsert_node(site_a, Label.DECISION, "decision-1", {"status": "VALID"})
    store.link(site_a, Label.CLAIM, "claim-1", Rel.SUPPORTED_BY, Label.SOURCE_VERSION, "source-v1")
    store.link(site_a, Label.MEMORY, "memory-1", Rel.DERIVED_FROM, Label.CLAIM, "claim-1")
    store.link(site_a, Label.DECISION, "decision-1", Rel.DEPENDS_ON, Label.MEMORY, "memory-1")

    impacts = store.find_impacts(site_a, ["source-v1"])

    assert [item.node_id for item in impacts] == ["claim-1", "memory-1", "decision-1"]
    assert store.find_impacts(site_b, ["source-v1"]) == []


def test_local_falkordb_rejects_unapproved_labels(local_drift_store) -> None:
    store, (site_id, _) = local_drift_store

    with pytest.raises(ValueError, match="label"):
        store.upsert_node(site_id, "UserControlledLabel", "n1", {})


def test_local_falkordb_client_reconnects_after_its_pool_disconnects(local_drift_store) -> None:
    store, (site_id, _) = local_drift_store
    store.upsert_node(site_id, Label.SOURCE_VERSION, "source-reconnect", {"status": "ACTIVE"})
    store._client.connection.connection_pool.disconnect()
    assert store.inspect_site(site_id) == {"reachable": True, "site_graph_exists": True}
    assert store.read_node(site_id, "source-reconnect")["properties"]["status"] == "ACTIVE"


def test_memory_lineage_keeps_every_claim_in_selected_memory(local_drift_store) -> None:
    store, (site_id, _) = local_drift_store
    store.upsert_node(site_id, Label.MEMORY, "memory-fanout", {"status": "VALID"})
    for n in range(9):
        source_id, claim_id = f"source-{n}", f"claim-{n}"
        store.upsert_node(site_id, Label.SOURCE_VERSION, source_id, {"status": "ACTIVE"})
        store.upsert_node(site_id, Label.CLAIM, claim_id, {"status": "ACTIVE", "fact_key": "fanout"})
        store.link(site_id, Label.CLAIM, claim_id, Rel.SUPPORTED_BY, Label.SOURCE_VERSION, source_id)
        store.link(site_id, Label.MEMORY, "memory-fanout", Rel.DERIVED_FROM, Label.CLAIM, claim_id)
    lineage = store.memory_lineage(site_id, limit=1)
    assert len(lineage) == 1
    assert len(lineage[0]["claims"]) == 9
    assert len(lineage[0]["sources"]) == 9


def test_local_falkordb_impact_overflow_fails_closed(local_drift_store) -> None:
    store, (site_id, _) = local_drift_store
    store._max_edges = 1
    store.upsert_node(site_id, Label.SOURCE_VERSION, "source-v1", {})
    for claim_id in ("claim-a", "claim-b"):
        store.upsert_node(site_id, Label.CLAIM, claim_id, {})
        store.link(site_id, Label.CLAIM, claim_id, Rel.SUPPORTED_BY, Label.SOURCE_VERSION, "source-v1")

    with pytest.raises(TraversalLimitExceeded, match="edge limit"):
        store.find_impacts(site_id, ["source-v1"])


def test_local_falkordb_resolveai_memory_decision_action_cascade_is_idempotent(local_drift_store) -> None:
    store, (site_id, _) = local_drift_store

    result = run_evidence_supersession(store, site_id)
    replay = run_evidence_supersession(store, site_id)

    assert result["authority_verdict"] == "REPLACE"
    assert [item["node_id"] for item in result["impact_paths"]] == [
        "DEMO-DRIFT-CLAIM-V1",
        "DEMO-DRIFT-MEMORY-001",
        "DEMO-DRIFT-DECISION-001",
        "DEMO-DRIFT-DECISION-REV-001",
        "DEMO-DRIFT-PLAN-001",
        "DEMO-DRIFT-ACTION-001",
    ]
    assert result["condition_results"][0]["holds"] is False
    assert result["decision_status"] == "INVALIDATED"
    assert result["action_eligibility"] == "SUSPENDED"
    assert result["human_review"]["approved_revision_id"] == "DEMO-DRIFT-DECISION-REV-001"
    assert result["human_review"]["matches_current_revision"] is False
    assert [agent["focus_level"] for agent in result["agent_focus_trace"]] == ["HYPERFOCUS", "HYPERFOCUS"]
    assert result["statuses"]["DEMO-DRIFT-ACTION-001"] == "SUSPENDED"
    assert replay["audit_chain_hash"] == result["audit_chain_hash"]
    assert replay["impact_paths"] == result["impact_paths"]
    assert store.read_node(site_id, "DEMO-DRIFT-MEMORY-001")["properties"]["status"] == "STALE"
    assert store.read_node(site_id, "DEMO-DRIFT-DECISION-REV-001")["properties"]["graph_revision"] == result["decision_revision"]["previous_graph_revision"]
    assert store.read_node(site_id, "DEMO-DRIFT-APPROVAL-REV-001")["properties"]["graph_revision"] != result["decision_revision"]["current_graph_revision"]

    with pytest.raises(RuntimeError, match="compare-and-set failed"):
        store.append_decision_revision(
            site_id,
            decision_id="DEMO-DRIFT-DECISION-001",
            revision_id="DEMO-DRIFT-DECISION-REV-STALE",
            expected_revision_n=1,
            previous_revision_id="DEMO-DRIFT-DECISION-REV-001",
            graph_revision="a" * 64,
            status="INVALIDATED",
            conditions_json="[]",
            dependency_ids=["DEMO-DRIFT-CLAIM-V2"],
            created_at="2026-10-18T08:00:00+00:00",
            reason="stale write must not advance the decision head",
        )
    assert store.read_node(site_id, "DEMO-DRIFT-DECISION-REV-STALE") is None


def test_local_resolveai_api_runs_site_scoped_cascade_and_blocks_nonstaff(local_drift_store) -> None:
    store, (site_id, other_site_id) = local_drift_store
    app = FastAPI()
    app.include_router(resolveai_router, prefix="/resolveai")
    caller = {"user_id": "synthetic-staff", "role": "engineer", "site_id": site_id}
    app.dependency_overrides[get_current_user] = lambda: caller
    app.dependency_overrides[get_falkor_drift_store] = lambda: store
    client = TestClient(app)

    response = client.post("/resolveai/drift/demo", json={
        "focus_level": "TARGETED", "input_modalities": ["DOCUMENT", "VOICE", "IMAGE"]
    })
    assert response.status_code == 200, response.text
    assert response.json()["action_eligibility"] == "SUSPENDED"
    assert response.json()["focus_plan"]["focus_level"] == "TARGETED"
    assert response.json()["focus_plan"]["unconnected_modalities"] == ["IMAGE", "VOICE"]
    status_response = client.get("/resolveai/drift/demo")
    assert status_response.status_code == 200
    assert status_response.json()["statuses"]["DEMO-DRIFT-ACTION-001"] == "SUSPENDED"
    assert status_response.json()["source_before"] == "DEMO-DRIFT-SOP-V1"
    assert status_response.json()["source_after"] == "DEMO-DRIFT-SOP-V2"
    assert status_response.json()["sources"][1]["authority_level"] == 2
    assert status_response.json()["condition_results"][0]["actual"] == 90
    assert status_response.json()["condition_results"][0]["holds"] is False
    assert status_response.json()["action_eligibility"] == "SUSPENDED"
    assert status_response.json()["impact_paths"][-1]["node_id"] == "DEMO-DRIFT-ACTION-001"
    assert status_response.json()["audit_chain_hash"] == response.json()["audit_chain_hash"]
    assert store.read_node(other_site_id, "DEMO-DRIFT-ACTION-001") is None

    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "synthetic-field", "role": "field_worker", "site_id": site_id
    }
    denied = client.post("/resolveai/drift/demo")
    assert denied.status_code == 403
