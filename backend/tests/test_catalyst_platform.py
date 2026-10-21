"""Catalyst gateway: secret forwarding, allow-list, demo block, NDJSON and image passthrough, failure honesty.

The worker is stood in by an httpx MockTransport. These tests prove the Kairos side of the integration only; they do NOT prove
the Catalyst worker runs end to end (that needs integrations/catalyst/.venv and a batch folder on disk)."""
from __future__ import annotations

import json

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from api.dependencies import get_current_user
from api.routers import catalyst_platform as gateway


class Chunks(httpx.AsyncByteStream):
    """A real async body, as a network response has. MockTransport's content= bodies arrive already consumed."""

    def __init__(self, parts: list[bytes]) -> None:
        self.parts = parts

    async def __aiter__(self):
        for part in self.parts:
            yield part


def client(role: str = "engineer", user_id: str = "u1") -> TestClient:
    app = FastAPI()
    app.include_router(gateway.router, prefix="/catalyst")
    app.dependency_overrides[get_current_user] = lambda: {"user_id": user_id, "role": role, "site_id": "site_c"}
    return TestClient(app)


@pytest.fixture
def worker(monkeypatch):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path
        if path == "/api/health":
            return httpx.Response(200, json={"model_present": True})
        if path == "/api/evidence/Batch_1":
            return httpx.Response(200, json={"verdict": "INVESTIGATE"})
        if path == "/api/images/Batch_1/img_1/BSE":
            return httpx.Response(200, content=b"\x89PNG-bytes", headers={"content-type": "image/png"})
        if path == "/api/runs/Batch_1":
            parts = [b'{"type":"progress","done":1,"total":2,"tile":"img_1"}\n', b'{"type":"done"}\n']
            return httpx.Response(200, stream=Chunks(parts), headers={"content-type": "application/x-ndjson"})
        if path == "/api/batches/Batch_1/files":
            return httpx.Response(200, json={"saved": 1, "saw_file": b"img_1_BSE.tif" in request.content})
        if path == "/api/evidence/boom":
            return httpx.Response(500, json={"trace": "worker internals"})
        return httpx.Response(404, json={"detail": "Not Found"})

    monkeypatch.setenv("CATALYST_GATEWAY_SECRET", "s3cret")
    monkeypatch.setattr(gateway, "_client", lambda: httpx.AsyncClient(base_url="http://worker", transport=httpx.MockTransport(handler)))
    return seen


def test_status_reports_worker_health_and_sends_the_secret_not_the_bearer_token(worker) -> None:
    body = client().get("/catalyst/status").json()
    assert body["connected"] is True and body["health"]["model_present"] is True
    headers = worker[0].headers
    assert headers["x-kairos-gateway-secret"] == "s3cret"
    assert "authorization" not in headers


def test_an_allowed_read_reaches_the_same_path_on_the_worker(worker) -> None:
    assert client().get("/catalyst/api/evidence/Batch_1").json()["verdict"] == "INVESTIGATE"
    assert worker[-1].url.path == "/api/evidence/Batch_1"


def test_png_images_come_back_byte_for_byte(worker) -> None:
    response = client().get("/catalyst/api/images/Batch_1/img_1/BSE")
    assert response.content == b"\x89PNG-bytes"
    assert response.headers["content-type"].startswith("image/png")


def test_ndjson_progress_is_streamed_through_unchanged(worker) -> None:
    response = client().post("/catalyst/api/runs/Batch_1")
    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[0]["type"] == "progress" and events[-1]["type"] == "done"


def test_uploads_are_re_sent_to_the_worker_as_multipart(worker) -> None:
    response = client().post("/catalyst/api/batches/Batch_1/files", files=[("files", ("img_1_BSE.tif", b"II*\x00", "image/tiff"))])
    assert response.json() == {"saved": 1, "saw_file": True}
    assert worker[-1].headers["content-type"].startswith("multipart/form-data")


def test_an_oversized_upload_is_refused_before_it_is_read(worker, monkeypatch) -> None:
    monkeypatch.setattr(gateway, "MAX_UPLOAD_BYTES", 10)
    response = client().post("/catalyst/api/batches/Batch_1/files", files=[("files", ("big.tif", b"x" * 100, "image/tiff"))])
    assert response.status_code == 413
    assert worker == []


@pytest.mark.parametrize("method,path", [
    ("PUT", "/catalyst/api/settings/baseline"),      # the one config write Catalyst has, deliberately not exposed
    ("POST", "/catalyst/api/settings/baseline"),
    ("GET", "/catalyst/api/evidence/a/b"),           # extra segment
    ("GET", "/catalyst/api/unknown"),
])
def test_routes_outside_the_allow_list_never_reach_the_worker(worker, method, path) -> None:
    response = client().request(method, path, json={"baseline": "Batch_1"})
    assert response.status_code in (404, 405)
    assert worker == []


@pytest.mark.parametrize("raw", [b"/catalyst/api/evidence/%2E%2E", b"/catalyst/api/evidence/.."])
def test_dot_segments_are_refused_before_forwarding(raw: bytes) -> None:
    # HTTP clients normalise '..' before sending, so the gateway's own check is tested on the raw path directly.
    scope = {"type": "http", "method": "GET", "path": raw.decode(), "raw_path": raw, "query_string": b"",
             "headers": [], "scheme": "http", "server": ("testserver", 80)}
    with pytest.raises(HTTPException) as refused:
        gateway._worker_path(Request(scope))
    assert refused.value.status_code == 400


def test_the_demo_account_is_refused_before_any_call_is_made(worker) -> None:
    response = client(role="demo").get("/catalyst/api/evidence/Batch_1")
    assert response.status_code == 403
    assert worker == []


def test_roles_outside_the_staff_list_are_refused(worker) -> None:
    assert client(role="viewer").get("/catalyst/api/evidence/Batch_1").status_code == 403
    assert worker == []


def test_without_a_secret_nothing_is_forwarded(worker, monkeypatch) -> None:
    monkeypatch.delenv("CATALYST_GATEWAY_SECRET")
    response = client().get("/catalyst/api/evidence/Batch_1")
    assert response.status_code == 503 and response.json()["detail"]["status"] == "NOT_CONNECTED"
    assert worker == []


def test_an_unreachable_worker_is_reported_as_not_connected_not_faked(monkeypatch) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    monkeypatch.setenv("CATALYST_GATEWAY_SECRET", "s3cret")
    monkeypatch.setattr(gateway, "_client", lambda: httpx.AsyncClient(base_url="http://worker", transport=httpx.MockTransport(refuse)))
    status_body = client().get("/catalyst/status").json()
    assert status_body["connected"] is False and status_body["status"] == "NOT_CONNECTED"
    assert client().get("/catalyst/api/evidence/Batch_1").status_code == 503


def test_worker_server_errors_become_502_without_leaking_worker_text(worker) -> None:
    response = client().get("/catalyst/api/evidence/boom")
    assert response.status_code == 502
    assert "worker internals" not in response.text
