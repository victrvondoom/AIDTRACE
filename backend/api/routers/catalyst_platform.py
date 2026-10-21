"""Gateway to the Catalyst QC worker (electrode batch QC from microscope images, integrations/catalyst).

Catalyst pins its own stack (pydantic 2.13, numpy 2.4, pandas 3, torch), which conflicts with Kairos's pins. It therefore runs
as a PRIVATE worker in its own virtualenv (scripts/start_catalyst_worker.py, loopback only), and this router is the only way in:
  * authenticates with the one Kairos session (staff roles; the demo account is closed because the worker can call a paid model);
  * forwards only the routes named in ALLOWED and refuses everything else before any call is made;
  * shows each call came through this gateway with a shared secret that the worker checks on every request;
  * passes the NDJSON progress streams and the PNG images through unchanged.
Catalyst keeps one shared data folder that is not partitioned per site, so the gateway stays with the staff roles.
Without a configured worker every call answers 503 NOT_CONNECTED. Nothing here simulates a result.

Paths mirror the worker: the browser calls /catalyst/api/evidence/<batch>, which reaches the worker as /api/evidence/<batch>.
"""
from __future__ import annotations

import os
import re
from typing import Any, NamedTuple
from urllib.parse import unquote

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response, StreamingResponse

from api.dependencies import CurrentUserDep, require_role
from api.services import tenant

log = structlog.get_logger(__name__)
router = APIRouter()
STAFF = ("engineer", "reliability", "admin")
PREFIX = "/catalyst"
SEG = r"[^/]+"
MAX_UPLOAD_BYTES = int(os.getenv("CATALYST_MAX_UPLOAD_MB", "500")) * 1024 * 1024


def _client() -> httpx.AsyncClient:  # patched in tests with a stand-in worker
    timeout = httpx.Timeout(connect=5.0, read=float(os.getenv("CATALYST_WORKER_TIMEOUT", "900")), write=120.0, pool=5.0)
    return httpx.AsyncClient(base_url=os.environ.get("CATALYST_WORKER_URL", "http://127.0.0.1:8300"), timeout=timeout)


class Route(NamedTuple):
    method: str
    pattern: re.Pattern[str]
    stream: bool = False   # NDJSON progress, forwarded as it arrives
    upload: bool = False   # multipart files, re-sent to the worker


def _route(method: str, path: str, *, stream: bool = False, upload: bool = False) -> Route:
    return Route(method, re.compile(path), stream, upload)


# Everything the Catalyst web UI calls, except the one write that changes config (PUT /api/settings/baseline).
ALLOWED: tuple[Route, ...] = (
    _route("GET", r"/api/health"),
    _route("GET", r"/api/config"),
    _route("GET", r"/api/settings"),
    _route("GET", r"/api/batches"),
    _route("POST", rf"/api/batches/{SEG}/files", upload=True),
    _route("GET", r"/api/evidence"),
    _route("GET", rf"/api/evidence/{SEG}"),
    _route("GET", rf"/api/guide/{SEG}"),
    _route("POST", rf"/api/guide/{SEG}"),                 # one paid Claude call, cached per evidence
    _route("POST", rf"/api/verify/{SEG}"),
    _route("GET", r"/api/attribution"),
    _route("GET", r"/api/attribution-evaluation"),
    _route("GET", r"/api/attribution-model"),
    _route("GET", rf"/api/attribution/{SEG}"),
    _route("POST", rf"/api/attribution/{SEG}", stream=True),
    _route("GET", r"/api/kpis"),
    _route("GET", r"/api/tiles"),
    _route("GET", rf"/api/images/{SEG}/{SEG}/{SEG}"),
    _route("GET", rf"/api/layers/{SEG}/{SEG}/{SEG}"),
    _route("GET", rf"/api/particles/{SEG}/{SEG}"),
    _route("GET", rf"/api/slab/{SEG}"),
    _route("GET", rf"/api/impact/{SEG}"),
    _route("GET", r"/api/masks/.+"),
    _route("POST", rf"/api/runs/{SEG}", stream=True),
    _route("POST", rf"/api/measure/{SEG}", stream=True),
)


def _not_connected(reason: str) -> HTTPException:
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, {"status": "NOT_CONNECTED", "message": reason,
                         "setup": "Start the private worker with scripts/start_catalyst_worker.py (see docs/integration/CATALYST_INTEGRATION.md)."})


def _no_demo(user: dict) -> None:
    if tenant.is_demo_user(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "The Catalyst QC worker is not available to the demo account.")


def _headers(user: dict) -> dict[str, str]:
    secret = os.environ.get("CATALYST_GATEWAY_SECRET", "")
    if not secret:
        raise _not_connected("CATALYST_GATEWAY_SECRET is not configured, so no call is forwarded to the worker.")
    return {"X-Kairos-Gateway-Secret": secret, "X-Kairos-User": str(user.get("user_id", "")),
            "X-Kairos-Role": "admin" if user.get("role") == "admin" else "user"}


def _worker_path(request: Request) -> str:
    """The worker path for this request, taken from the raw (still percent-encoded) URL, with the /catalyst prefix removed."""
    raw = (request.scope.get("raw_path") or request.url.path.encode()).decode("ascii", "strict")
    if not raw.startswith(PREFIX + "/"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not a Catalyst route")
    path = raw[len(PREFIX):]
    if any(unquote(segment) in (".", "..") for segment in path.split("/")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "path segments may not be '.' or '..'")
    return path


def _match(method: str, path: str) -> Route:
    for route in ALLOWED:
        if route.method == method and route.pattern.fullmatch(path):
            return route
    raise HTTPException(status.HTTP_404_NOT_FOUND, "this Catalyst route is not available through the gateway")


async def _multipart(request: Request) -> list[tuple[str, tuple[str, bytes, str]]]:
    declared = int(request.headers.get("content-length", "0") or 0)
    if declared > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE,f"uploads are limited to {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
    form = await request.form()
    return [("files", (item.filename or "upload.tif", await item.read(), item.content_type or "application/octet-stream"))
            for item in form.getlist("files") if hasattr(item, "read")]


def _upstream_error(response: httpx.Response) -> HTTPException:
    return HTTPException(status.HTTP_502_BAD_GATEWAY, {"message": "The Catalyst worker failed on this request.", "worker_status": response.status_code})


def _passthrough(response: httpx.Response) -> Response:
    if response.status_code >= 500:
        raise _upstream_error(response)
    return Response(content=response.content, status_code=response.status_code,
                    media_type=response.headers.get("content-type", "application/octet-stream"))


async def _forward(request: Request, user: dict) -> Response:
    _no_demo(user)
    path = _worker_path(request)
    route = _match(request.method, path)
    headers = _headers(user)
    url = f"{path}?{request.url.query}" if request.url.query else path
    files = await _multipart(request) if route.upload else None
    client = _client()
    streaming = False  # once a stream is handed to the client, the relay closes the HTTP client instead
    try:
        if route.stream:
            upstream = await client.send(client.build_request(request.method, url, headers=headers, files=files), stream=True)
            if upstream.status_code >= 500:
                await upstream.aclose()
                raise _upstream_error(upstream)

            async def relay():
                try:
                    async for chunk in upstream.aiter_raw():
                        yield chunk
                finally:
                    await upstream.aclose()
                    await client.aclose()

            streaming = True
            return StreamingResponse(relay(), status_code=upstream.status_code,
                                     media_type=upstream.headers.get("content-type", "application/x-ndjson"))
        response = await client.request(request.method, url, headers=headers, files=files)
    except httpx.HTTPError as exc:
        log.warning("catalyst.unreachable", error=type(exc).__name__)
        raise _not_connected("The Catalyst worker is not reachable.") from exc
    finally:
        if not streaming:
            await client.aclose()
    return _passthrough(response)


async def _worker_json(path: str, user: dict) -> Any:
    client = _client()
    try:
        response = await client.get(path, headers=_headers(user), timeout=8)
    except httpx.HTTPError as exc:
        raise _not_connected("The Catalyst worker is not reachable.") from exc
    finally:
        await client.aclose()
    if response.status_code >= 500:
        raise _upstream_error(response)
    return response.json()


@router.get("/status", summary="Is the private Catalyst worker connected? Reports its own health when it is.")
async def catalyst_status(user: CurrentUserDep, _staff: dict = Depends(require_role(*STAFF))) -> dict:
    _no_demo(user)
    try:
        health = await _worker_json("/api/health", user)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
        return {"connected": False, **detail}
    return {"connected": True, "health": health}


@router.api_route("/{rest:path}", methods=["GET", "POST"], include_in_schema=False)
async def forward(rest: str, request: Request, user: CurrentUserDep, _staff: dict = Depends(require_role(*STAFF))) -> Response:
    """Every other /catalyst path: allow-listed above, refused otherwise (see ALLOWED)."""
    return await _forward(request, user)
