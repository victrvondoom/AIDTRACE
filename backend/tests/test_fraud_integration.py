"""Fraud investigation inside Kairos: tenant graphs, live run trace, revalidating approval and MCP tool surface."""
from __future__ import annotations

import os
import time
from types import SimpleNamespace

import pytest
from domains.fraud.store import GraphStore
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_current_user, get_settings
from api.routers.fraud import router

URL = os.environ.get("FALKORDB_TEST_URL", "")
pytestmark = pytest.mark.skipif(not URL, reason="set FALKORDB_TEST_URL")


def client(site: str, role: str = "engineer", user_id: str = "u-fraud") -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/fraud")
    app.dependency_overrides[get_current_user] = lambda: {"user_id": user_id, "role": role, "site_id": site}
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace(FALKORDB_URL=URL)
    return TestClient(app)


@pytest.fixture
def site():
    name = f"site_fr_{int(time.time() * 1000) % 10_000_000}"
    yield name
    GraphStore(URL, f"fraud_{name}").reset_synthetic_graph()


def run_to_completion(c: TestClient) -> dict:
    run_id = c.post("/fraud/investigations", json={}).json()["run_id"]
    for _ in range(80):
        body = c.get("/fraud/investigation", params={"run_id": run_id}).json()
        if body["status"] != "running":
            return body
        time.sleep(0.25)
    raise AssertionError("investigation did not finish")


def test_end_to_end_investigation_proposes_rings_and_never_the_decoy(site) -> None:
    c = client(site)
    assert c.post("/fraud/seed").json()["synthetic"] is True
    assert c.get("/fraud/health").json()["loaded"] is True
    result = run_to_completion(c)
    assert result["status"] == "done" and result["mode"] == "deterministic"
    frozen_candidates = {a for p in result["proposals"] for a in p["targets"]}
    assert {"RA1", "RB1"} <= frozen_candidates and not ({"HH1", "HH2"} & frozen_candidates)
    assert any(e["type"] == "query" for e in result["events"])  # every graph query is recorded in the trace
    assert c.get("/fraud/neighborhood", params={"account_id": "RA3"}).json()["graph"]["edges"]


def test_approval_records_the_session_user_and_revalidates_stale_evidence(site) -> None:
    c = client(site, user_id="u-approver")
    c.post("/fraud/seed")
    proposals = run_to_completion(c)["proposals"]
    ring_a = next(p for p in proposals if "RA1" in p["targets"])
    done = c.post("/fraud/actions/approve", params={"action_id": ring_a["action_id"]})
    assert done.status_code == 200 and done.json()["status"] == "EXECUTED"
    props = GraphStore(URL, f"fraud_{site}").query("MATCH (x:Action {id: $i}) RETURN x.approved_by", {"i": ring_a["action_id"]})
    assert props[0][0] == "u-approver"
    ring_b = next(p for p in proposals if "RB1" in p["targets"])
    store = GraphStore(URL, f"fraud_{site}")
    store.query("MATCH (:Account {id: 'RB2'})-[r:USED_DEVICE|OWNS_CARD]->() DELETE r")  # the evidence behind ring B changes
    stale = c.post("/fraud/actions/approve", params={"action_id": ring_b["action_id"]})
    assert stale.status_code == 409 and stale.json()["detail"]["error"] == "EVIDENCE_CHANGED"
    status_row = store.query("MATCH (x:Action {id: $i}) RETURN x.status", {"i": ring_b["action_id"]})
    assert status_row[0][0] == "INVALIDATED"
    frozen = store.query("MATCH (a:Account) WHERE a.id IN ['RB1','RB3','RB4'] RETURN a.status")
    assert all(r[0] == "ACTIVE" for r in frozen)  # nothing froze on stale evidence


def test_tenants_are_isolated_and_roles_enforced(site) -> None:
    a, b = client(site), client(site + "_other")
    try:
        a.post("/fraud/seed")
        assert b.get("/fraud/health").json()["loaded"] is False
        assert client(site, role="field_worker").get("/fraud/flagged").status_code == 403
        run_id = a.post("/fraud/investigations", json={}).json()["run_id"]
        assert b.get("/fraud/investigation", params={"run_id": run_id}).status_code == 404  # another tenant's run is not served
    finally:
        GraphStore(URL, f"fraud_{site}_other").reset_synthetic_graph()


def test_mcp_server_exposes_reads_and_propose_only() -> None:
    """The MCP SDK needs a newer pydantic than Kairos pins (2.7.4), so the stdio server cannot be imported in this
    environment and must run as a separate private process. Its tool surface is checked from source: reads plus
    propose_freeze, and no approve or execute tool, so an external agent can propose but never carry out an action."""
    import ast
    from pathlib import Path

    tree = ast.parse((Path(__file__).resolve().parents[1] / "domains" / "fraud" / "mcp_server.py").read_text(encoding="utf-8-sig"))
    tools = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
             and any("tool" in ast.unparse(d) for d in n.decorator_list)}
    assert tools == {"flagged_transactions", "account_profile", "ring_members", "weak_links", "propose_freeze"}
    assert not any(word in name for name in tools for word in ("approve", "execute", "freeze_now", "reject"))
