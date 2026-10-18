"""ResolveAI platform gateway: identity forwarding, tenant namespacing, allow-list, failure honesty.

The worker is stood in by an httpx MockTransport. These tests prove the Kairos side of the integration only; they do
NOT prove the RESOLVE-AI-main worker runs end to end (that needs Supabase, Qdrant, Neo4j, Redis and model keys)."""
from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_current_user
from api.routers import resolveai_platform as platform


def client(role="engineer", site="site_rp_a", user_id="u1") -> TestClient:
    app = FastAPI()
    app.include_router(platform.router, prefix="/resolveai/platform")
    app.dependency_overrides[get_current_user] = lambda: {"user_id": user_id, "role": role, "site_id": site}
    return TestClient(app)


@pytest.fixture
def worker(monkeypatch):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/api/v1/domains":
            return httpx.Response(200, json=[{"id": "airlines", "label": "Airlines", "active": True}])
        if request.url.path == "/api/v1/cases" and request.method == "POST":
            return httpx.Response(200, json={"id": "case-1", "user_id": request.headers["x-kairos-tenant"] + ":" + request.headers["x-kairos-user"]})
        if request.url.path == "/api/v1/cases/missing":
            return httpx.Response(404, json={"code": "case_not_found"})
        if request.url.path == "/api/v1/agents/run-case":
            return httpx.Response(500, json={"boom": True})
        return httpx.Response(200, json=[])

    monkeypatch.setenv("RESOLVEAI_GATEWAY_SECRET", "s3cret")
    monkeypatch.setattr(platform, "_client", lambda: httpx.AsyncClient(base_url="http://worker", transport=httpx.MockTransport(handler)))
    return seen


def test_status_lists_domain_packs_and_forwards_the_kairos_identity(worker) -> None:
    body = client().get("/resolveai/platform/status").json()
    assert body["connected"] is True and body["domains"][0]["id"] == "airlines"
    h = worker[0].headers
    assert h["x-kairos-gateway-secret"] == "s3cret" and h["x-kairos-user"] == "u1" and h["x-kairos-tenant"] == "site_rp_a"
    assert "authorization" not in h  # the browser's bearer token is never passed on


def test_cases_are_namespaced_by_tenant_so_sites_cannot_collide(worker) -> None:
    payload = {"title": "Refund dispute", "institution_name": "Acme Air", "summary": "Flight cancelled; refund partly paid.", "domain": "airlines"}
    a = client(site="site_rp_a").post("/resolveai/platform/cases", json=payload).json()
    b = client(site="site_rp_b").post("/resolveai/platform/cases", json=payload).json()
    assert a["user_id"] == "site_rp_a:u1" and b["user_id"] == "site_rp_b:u1"


def test_without_a_secret_nothing_is_forwarded(worker, monkeypatch) -> None:
    monkeypatch.delenv("RESOLVEAI_GATEWAY_SECRET")
    r = client().post("/resolveai/platform/cases", json={"title": "Refund dispute", "institution_name": "Acme", "summary": "Flight cancelled badly."})
    assert r.status_code == 503 and r.json()["detail"]["status"] == "NOT_CONNECTED" and worker == []


def test_unreachable_worker_is_reported_not_connected_not_faked(monkeypatch) -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")
    monkeypatch.setenv("RESOLVEAI_GATEWAY_SECRET", "s3cret")
    monkeypatch.setattr(platform, "_client", lambda: httpx.AsyncClient(base_url="http://worker", transport=httpx.MockTransport(boom)))
    status_body = client().get("/resolveai/platform/status").json()
    assert status_body["connected"] is False and status_body["status"] == "NOT_CONNECTED"
    assert client().post("/resolveai/platform/agents/ask", json={"question": "What is covered?"}).status_code == 503


def test_worker_errors_pass_through_and_server_faults_become_502(worker) -> None:
    c = client()
    assert c.get("/resolveai/platform/case", params={"case_id": "missing"}).status_code == 404
    assert c.post("/resolveai/platform/agents/run-case", json={"case_id": "case-1"}).status_code == 502


def test_roles_input_validation_and_allowlist(worker) -> None:
    assert client(role="field_worker").get("/resolveai/platform/status").status_code == 403
    assert client(role="demo").post("/resolveai/platform/agents/ask", json={"question": "hello there"}).status_code == 403
    assert client().get("/resolveai/platform/case", params={"case_id": "../admin"}).status_code == 422
    assert client().post("/resolveai/platform/cases", json={"title": "x", "institution_name": "y", "summary": "z"}).status_code == 422
    paths = {r.path for r in platform.router.routes}
    assert not any("admin" in p or "upload" in p for p in paths)  # the worker's admin and upload routes are not exposed
