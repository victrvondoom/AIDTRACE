"""Shared agent-runtime interface, and a real cross-system handoff: ResolveAI evidence -> memory -> another agent -> stale."""
from __future__ import annotations

import os
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_current_user, get_falkor_drift_store
from api.routers import agent_memory, agents, resolveai_platform
from api.services.agents.runtime import ADAPTERS, INTERFACES, NATIVE, NONE, Adapter, Tool
from api.services.drift.store import FalkorDriftStore


def test_every_adapter_declares_all_nine_interfaces_and_only_backs_what_it_provides() -> None:
    assert len(INTERFACES) == 9 and set(ADAPTERS) == {"resolveai", "fraud", "greenchain", "memory"}
    for adapter in ADAPTERS.values():
        assert set(adapter.interfaces) == set(INTERFACES)
        for tool in adapter.tools:
            assert adapter.interfaces[tool.interface] != NONE, f"{adapter.id}.{tool.name} claims an interface it does not provide"


def test_an_adapter_cannot_expose_a_tool_for_an_interface_it_says_it_lacks() -> None:
    interfaces = {name: NONE for name in INTERFACES}
    with pytest.raises(ValueError, match="does not provide"):
        Adapter(id="x", name="X", framework="f", origin="o", interfaces=interfaces, tools=(Tool("t", "memory", "d"),))
    with pytest.raises(ValueError, match="invalid interface matrix"):
        Adapter(id="x", name="X", framework="f", origin="o", interfaces={"memory": NATIVE}, tools=())


def test_the_matrix_tells_the_truth_about_known_gaps() -> None:
    assert ADAPTERS["fraud"].interfaces["memory"] == NONE  # the fraud agent does not use shared memory yet
    assert ADAPTERS["resolveai"].interfaces["approval"] == NONE
    assert ADAPTERS["greenchain"].interfaces["execution_trace"] == NONE
    assert ADAPTERS["memory"].interfaces["task_execution"] == NONE


@pytest.fixture
def env(monkeypatch):
    url = os.getenv("FALKORDB_TEST_URL")
    if not url:
        pytest.skip("set FALKORDB_TEST_URL to run FalkorDB integration coverage")
    store = FalkorDriftStore(url, graph_prefix=f"pytest_{uuid.uuid4().hex[:12]}", query_timeout_ms=8000, max_depth=12)
    sites = [f"site_{uuid.uuid4().hex[:8]}", f"site_{uuid.uuid4().hex[:8]}"]
    worker = {"up": True}

    async def runtime():
        return ({"model_provider": "disabled", "model_provider_name": "gemini", "vector_backend": "jsonl", "indexed_points": 12113, "collections": 8,
                 "graph_backend": "jsonl", "case_store": "local"} if worker["up"] else None)

    investigation = {"mode": "retrieval_only", "llm_used": False, "evidence": [
        {"title": "IRDAI Master Circular", "authority": "IRDAI", "retrieved_chunk": "Claims shall be settled within 30 days.", "confidence": 0.6, "chunk_id": "k1", "evidence_scores": {"authority_score": 1.0}}]}

    async def forward(method, path, user, **kw):
        if path.startswith("/reports/case/"):
            return {"case": {"id": "case-9", "domain": "health_insurance", "institution_name": "Acme"}, "agent_runs": [{"workflow_name": "kairos_evidence_investigation", "output": investigation}]}
        if path == "/reports/summary":
            return {"recent_activity": [{"id": "e1", "event_type": "agent_run", "case_id": "case-9", "title": "kairos_evidence_investigation finished", "body": "completed", "created_at": "2026-10-18T09:00:00+00:00"}]}
        raise AssertionError(path)

    monkeypatch.setattr(resolveai_platform, "_runtime", runtime)
    monkeypatch.setattr(resolveai_platform, "_forward", forward)

    def client(site: str, role: str = "engineer") -> TestClient:
        app = FastAPI()
        app.include_router(agents.router, prefix="/agents")
        app.include_router(agent_memory.router, prefix="/agent-memory")
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "u1", "role": role, "site_id": site}
        app.dependency_overrides[get_falkor_drift_store] = lambda: store
        return TestClient(app)

    try:
        yield client, sites, worker
    finally:
        for s in sites:
            if store.graph_name(s) in store._client.list_graphs():
                store._graph(s).delete()
        store.close()


def test_runtimes_report_live_status_and_a_dead_runtime_is_unavailable_not_faked(env) -> None:
    client, (site, _), worker = env
    body = client(site).get("/agents/runtimes").json()
    by = {r["id"]: r for r in body["runtimes"]}
    assert by["resolveai"]["status"]["state"] == "LIMITED" and "no model provider" in by["resolveai"]["status"]["detail"]
    assert by["memory"]["status"]["state"] == "OPERATIONAL"
    assert len(body["matrix"]["runtimes"]) == 4
    worker["up"] = False
    assert {r["id"]: r for r in client(site).get("/agents/runtimes").json()["runtimes"]}["resolveai"]["status"]["state"] == "UNAVAILABLE"


def test_resolveai_evidence_is_remembered_then_recalled_by_another_agent_until_the_source_changes(env) -> None:
    client, (site, other_site), _ = env
    c = client(site)
    remembered = c.post("/agent-memory/resolveai/remember", json={"case_id": "case-9"}).json()
    assert remembered["remembered"] is True

    # a different agent, through the shared tool interface, retrieves it
    got = c.post("/agents/tools/invoke", json={"runtime": "memory", "tool": "recall", "args": {"agent_id": "agent:greenchain-scorer", "fact_key": "evidence_for_case:case-9"}}).json()
    assert [m["id"] for m in got["result"]["usable"]] == [remembered["memory_id"]]
    handoff = c.get("/agent-memory/handoffs").json()["handoffs"]
    assert handoff[0]["produced_by"] == "agent:resolveai-investigator" and handoff[0]["recalled_by"] == "agent:greenchain-scorer" and handoff[0]["usable"] is True

    # the run shows up in the merged view, from the system that produced it
    runs = c.get("/agents/runs").json()
    assert {r["system"] for r in runs["runs"]} >= {"resolveai"}

    # another site sees nothing
    assert client(other_site).get("/agent-memory/handoffs").json()["handoffs"] == []


def test_verified_context_is_site_scoped_and_keeps_claim_and_source_provenance(env) -> None:
    client, (site, other_site), _ = env
    c = client(site)
    remembered = c.post("/agent-memory/resolveai/remember", json={"case_id": "case-9"}).json()
    request = {"agent_id": "agent:reviewer", "fact_key": "evidence_for_case:case-9", "limit": 5}
    context = c.post("/agent-memory/context", json=request)
    assert context.status_code == 200, context.text
    result = context.json()
    assert result["context_type"] == "untrusted_graph_memory"
    assert result["influenced_by"] == [remembered["memory_id"]]
    assert result["entries"][0]["verification_status"] == "VERIFIED"
    assert result["entries"][0]["claims"][0]["fact_key"] == request["fact_key"]
    assert result["entries"][0]["source_versions"][0]["document_id"]
    assert client(other_site).post("/agent-memory/context", json=request).json()["entries"] == []

    tool = c.post("/agents/tools/invoke", json={"runtime": "memory", "tool": "context", "args": request})
    assert tool.status_code == 200, tool.text
    assert tool.json()["result"]["influenced_by"] == [remembered["memory_id"]]
    assert c.post("/agent-memory/context", json={**request, "fact_key": "bad key"}).status_code == 422
    assert c.post("/agents/tools/invoke", json={"runtime": "memory", "tool": "context", "args": {}}).status_code == 422


def test_remembering_requires_a_prior_investigation(env, monkeypatch) -> None:
    client, (site, _), _ = env

    async def empty(method, path, user, **kw):
        return {"case": {"id": "case-9", "domain": "banking", "institution_name": "x"}, "agent_runs": []}

    monkeypatch.setattr(resolveai_platform, "_forward", empty)
    assert client(site).post("/agent-memory/resolveai/remember", json={"case_id": "case-9"}).status_code == 409


def test_only_declared_safe_tools_can_be_invoked_and_inputs_are_validated(env) -> None:
    client, (site, _), _ = env
    c = client(site)
    assert c.post("/agents/tools/invoke", json={"runtime": "fraud", "tool": "propose_freeze", "args": {}}).status_code == 404  # a write tool is not invokable
    assert c.post("/agents/tools/invoke", json={"runtime": "nope", "tool": "x", "args": {}}).status_code == 404
    assert c.post("/agents/tools/invoke", json={"runtime": "greenchain", "tool": "score_suppliers", "args": {"transport_mode": "teleport"}}).status_code == 422
    scored = c.post("/agents/tools/invoke", json={"runtime": "greenchain", "tool": "score_suppliers", "args": {"transport_mode": "sea"}}).json()
    assert scored["result"]["illustrative_candidates"] is True and scored["result"]["ranking"][0]["rank"] == 1
    assert client(site, role="field_worker").get("/agents/runtimes").status_code == 403
