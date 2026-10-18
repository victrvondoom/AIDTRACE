"""The headline Kairos scenario, end to end on real FalkorDB with GreenChain's real scorer:

A supplier is recommended -> a human approves -> a reference dataset is revised -> the cascade marks the memory, decision, plan and
action stale, the real scorer re-ranks, the old approval is refused, and a safer proposal needs a fresh approval."""
from __future__ import annotations

import os
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_current_user, get_falkor_drift_store
from api.routers import agent_memory
from api.services.drift.store import FalkorDriftStore


@pytest.fixture
def env():
    url = os.getenv("FALKORDB_TEST_URL")
    if not url:
        pytest.skip("set FALKORDB_TEST_URL to run FalkorDB integration coverage")
    store = FalkorDriftStore(url, graph_prefix=f"pytest_{uuid.uuid4().hex[:12]}", query_timeout_ms=8000, max_depth=12)
    sites = [f"site_{uuid.uuid4().hex[:8]}", f"site_{uuid.uuid4().hex[:8]}"]

    def client(site: str, role: str = "engineer") -> TestClient:
        app = FastAPI()
        app.include_router(agent_memory.router, prefix="/agent-memory")
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "u1", "email": "reviewer@example.test", "role": role, "site_id": site}
        app.dependency_overrides[get_falkor_drift_store] = lambda: store
        return TestClient(app)

    try:
        yield client, sites
    finally:
        for s in sites:
            if store.graph_name(s) in store._client.list_graphs():
                store._graph(s).delete()
        store.close()


def test_a_large_dataset_revision_changes_the_recommendation_and_voids_the_old_approval(env) -> None:
    client, (site, _) = env
    c = client(site)
    rec = c.post("/agent-memory/greenchain/record", json={"scenario_id": "s1"}).json()
    assert rec["top"] == "Illustrative Packaging D" and len(rec["ranking"]) == 5
    assert c.post("/agent-memory/actions/approve", json={"action_id": rec["action_id"]}).status_code == 200

    out = c.post("/agent-memory/greenchain/revise", json={"scenario_id": "s1", "dataset": "EMBER", "country": "PT", "factor": 50, "label": "Ember revision (counterfactual)"}).json()
    assert out["recommendation_changed"] is True and out["top_before"] == "Illustrative Packaging D" and out["top_after"] == "Illustrative Packaging B"
    stale = {x["id"]: x["after"] for x in out["cascade"]["invalidated"]}
    assert stale[rec["memory_id"]] == "STALE" and stale[rec["decision_id"]] == "STALE" and stale[rec["action_id"]] == "SUSPENDED"
    assert out["old_decision"]["status"] == "INVALIDATED"
    assert out["old_action"]["eligibility"]["eligible"] is False
    # the exact dependency path explains the change
    path = next(x["via"] for x in out["cascade"]["invalidated"] if x["id"] == rec["decision_id"])
    assert path[0] == "dataset:EMBER:s1:v1" and path[-1] == rec["decision_id"] and len(path) >= 3  # revised dataset -> claim -> memory -> decision
    d = next(r for r in out["ranking"] if r["name"] == "Illustrative Packaging D")
    assert d["rank_before"] == 1 and d["rank_after"] > 1 and d["total_after"] > d["total_before"]

    refused = c.post("/agent-memory/actions/approve", json={"action_id": rec["action_id"]})
    assert refused.status_code == 409 and refused.json()["detail"]["status"] == "APPROVAL_REFUSED"

    new = out["new_proposal"]
    assert new["eligibility"]["eligible"] is True and new["eligibility"]["approval_current"] is False
    assert c.post("/agent-memory/actions/approve", json={"action_id": new["action_id"]}).status_code == 200
    state = c.get("/agent-memory/actions/eligibility", params={"action_id": new["action_id"]}).json()
    assert state["approval_current"] is True

    memo = c.get("/agent-memory/greenchain/report", params={"scenario_id": "s1"}).json()["markdown"]
    assert "Illustrative Packaging B" in memo and "Illustrative Packaging D" in memo
    assert "INVALIDATED" in memo and "dataset:EMBER:s1:v1 ->" in memo  # the dependency path is in the memo
    assert "VOID" in memo and "reviewer@example.test" in memo  # the voided approval and the new receipt are both on record
    assert "counterfactual" in memo and "No purchase was made" not in memo and "no purchase was made" in memo
    assert c.get("/agent-memory/greenchain/report", params={"scenario_id": "unknown"}).status_code == 404


def test_a_moderate_revision_keeps_the_recommendation_but_still_requires_a_fresh_approval(env) -> None:
    client, (site, _) = env
    c = client(site)
    rec = c.post("/agent-memory/greenchain/record", json={"scenario_id": "s2"}).json()
    first = c.post("/agent-memory/actions/approve", json={"action_id": rec["action_id"]}).json()
    out = c.post("/agent-memory/greenchain/revise", json={"scenario_id": "s2", "dataset": "GLEC", "country": "PT", "factor": 3, "label": "GLEC revision (counterfactual)"}).json()
    assert out["recommendation_changed"] is False and out["new_proposal"] is None
    assert out["old_decision"]["status"] == "VALID" and out["old_decision"]["revision"]["revision_n"] == 2
    state = c.get("/agent-memory/actions/eligibility", params={"action_id": rec["action_id"]}).json()
    assert state["eligible"] is True and state["approval_current"] is False  # the earlier approval pinned revision 1
    second = c.post("/agent-memory/actions/approve", json={"action_id": rec["action_id"]}).json()
    assert second["graph_revision"] != first["graph_revision"]


def test_the_same_revision_twice_is_idempotent_and_recall_blocks_stale_memory(env) -> None:
    client, (site, _) = env
    c = client(site)
    rec = c.post("/agent-memory/greenchain/record", json={"scenario_id": "s3"}).json()
    body = {"scenario_id": "s3", "dataset": "USEEIO", "country": "PT", "factor": 2, "label": "USEEIO revision (counterfactual)"}
    first = c.post("/agent-memory/greenchain/revise", json=body).json()
    again = c.post("/agent-memory/greenchain/revise", json=body).json()
    assert first["duplicate"] is False and again["duplicate"] is True
    recall = c.post("/agent-memory/recall", json={"agent_id": "agent:fraud-investigator", "fact_key": "top_supplier:s3"}).json()
    assert rec["memory_id"] in {m["id"] for m in recall["blocked"]}
    assert first["new_memory_id"] in {m["id"] for m in recall["usable"]}  # the re-scored memory is what a second agent may use
    assert recall["influenced_by"] == [m["id"] for m in recall["usable"]]


def test_scenarios_and_sites_are_isolated(env) -> None:
    client, (site_a, site_b) = env
    a, b = client(site_a), client(site_b)
    a.post("/agent-memory/greenchain/record", json={"scenario_id": "p"})
    a.post("/agent-memory/greenchain/record", json={"scenario_id": "q"})
    a.post("/agent-memory/greenchain/revise", json={"scenario_id": "p", "dataset": "EMBER", "country": "PT", "factor": 50, "label": "Ember revision (counterfactual)"})
    snap = a.get("/agent-memory/snapshot").json()
    q_action = next(x for x in snap["actions"] if x["id"] == "gc:q:action")
    assert q_action["eligibility"]["eligible"] is True  # scenario q rests on its own dataset versions, so it is untouched
    other = b.get("/agent-memory/snapshot").json()
    assert other["memories"] == [] and other["actions"] == []
    assert b.get("/agent-memory/actions/eligibility", params={"action_id": "gc:q:action"}).status_code == 422  # not in site B's graph


def test_previews_are_read_only_and_match_the_real_revision(env) -> None:
    client, (site, _) = env
    c = client(site)
    rec = c.post("/agent-memory/greenchain/record", json={"scenario_id": "pv"}).json()
    before = c.get("/agent-memory/snapshot").json()
    body = {"scenario_id": "pv", "dataset": "EMBER", "country": "PT", "factor": 50, "label": "Preview only"}
    preview = c.post("/agent-memory/greenchain/preview-revision", json=body).json()
    impact = c.get("/agent-memory/impact-preview", params={"source_id": rec["datasets"]["EMBER"]}).json()
    assert preview["read_only"] and preview["counterfactual"] and preview["recommendation_changes"] is True
    assert impact["read_only"] and {x["label"] for x in impact["would_mark_stale"]} >= {"Claim", "Memory", "Decision", "ActionProposal"}
    after = c.get("/agent-memory/snapshot").json()
    assert [m["status"] for m in after["memories"]] == [m["status"] for m in before["memories"]] == ["VALID"]  # nothing changed
    real = c.post("/agent-memory/greenchain/revise", json={**body, "label": "Applied"}).json()
    assert real["top_after"] == preview["top_after"] and real["recommendation_changed"] is True
    assert c.get("/agent-memory/impact-preview", params={"source_id": "no-such-source"}).status_code == 422


def test_validation_and_roles(env) -> None:
    client, (site, _) = env
    c = client(site)
    assert c.post("/agent-memory/greenchain/revise", json={"scenario_id": "s", "dataset": "BOGUS", "country": "PT", "factor": 2, "label": "x y z"}).status_code == 422
    assert c.post("/agent-memory/greenchain/revise", json={"scenario_id": "s", "dataset": "EMBER", "country": "PT", "factor": 5000, "label": "too big"}).status_code == 422
    assert client(site, role="field_worker").get("/agent-memory/snapshot").status_code == 403
