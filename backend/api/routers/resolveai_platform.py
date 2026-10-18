"""Gateway to the migrated RESOLVE-AI-main platform (multi-agent consumer cases, RAG, eight domain packs).

The RESOLVE-AI-main backend (`integrations/resolveai/backend`) has dependencies that conflict with Kairos's pins and
needs its own services (Supabase, Qdrant, Neo4j, Redis, Gemini/NVIDIA keys). It therefore runs as a PRIVATE worker and is
reached only through this router, which:
  * authenticates with the one Kairos session (staff roles; the demo role is closed because the worker calls paid LLMs);
  * forwards the Kairos identity to the worker over a shared-secret trusted-gateway channel (no second login);
  * namespaces case ownership by tenant (`<site>:<user>`);
  * exposes only an allow-listed set of worker operations (never its admin or upload routes).
Without a configured worker every call answers 503 NOT_CONNECTED. Nothing here simulates agent output.
"""
from __future__ import annotations

import os
from typing import Any

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from api.dependencies import CurrentUserDep, require_role
from api.routers.resolveai import _site_for_user
from api.services import tenant

log = structlog.get_logger(__name__)
router = APIRouter()
STAFF = ("engineer", "reliability", "admin")
API_PREFIX = "/api/v1"
TIMEOUT_S = float(os.getenv("RESOLVEAI_WORKER_TIMEOUT", "120"))
CASE_ID = r"^[A-Za-z0-9_.:-]{1,80}$"


class CaseBody(BaseModel):
    domain: str = Field(default="health_insurance", max_length=40, pattern=r"^[a-z_]+$")
    title: str = Field(min_length=4, max_length=160)
    institution_name: str = Field(min_length=2, max_length=160)
    summary: str = Field(min_length=10, max_length=4000)
    jurisdiction: str = Field(default="IN", max_length=80)


class AskBody(BaseModel):
    domain: str = Field(default="health_insurance", max_length=40, pattern=r"^[a-z_]+$")
    question: str = Field(min_length=3, max_length=2000)
    institution_name: str = Field(default="General health insurer", max_length=160)


class SearchBody(BaseModel):
    domain: str = Field(default="health_insurance", max_length=40, pattern=r"^[a-z_]+$")
    query: str = Field(min_length=3, max_length=1000)
    limit: int = Field(default=6, ge=1, le=20)


class InvestigateBody(BaseModel):
    case_id: str = Field(pattern=CASE_ID)
    run_model_synthesis: bool = False


class RunBody(BaseModel):
    case_id: str = Field(pattern=CASE_ID)
    include_negotiation_draft: bool = True


def _client() -> httpx.AsyncClient:  # patched in tests with a stand-in worker
    return httpx.AsyncClient(base_url=os.environ.get("RESOLVEAI_WORKER_URL", "http://127.0.0.1:8200"), timeout=TIMEOUT_S)


def _not_connected(reason: str) -> HTTPException:
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, {"status": "NOT_CONNECTED", "message": reason,
                         "setup": "Start the private worker from integrations/resolveai (see docs/integration/RESOLVEAI_MIGRATION.md)."})


def _headers(user: dict, site_id: str) -> dict[str, str]:
    secret = os.environ.get("RESOLVEAI_GATEWAY_SECRET", "")
    if not secret:
        raise _not_connected("RESOLVEAI_GATEWAY_SECRET is not configured, so no call is forwarded to the worker.")
    return {"X-Kairos-Gateway-Secret": secret, "X-Kairos-User": str(user.get("user_id", "")), "X-Kairos-Tenant": site_id,
            "X-Kairos-Role": "admin" if user.get("role") == "admin" else "user"}


async def _forward(method: str, path: str, user: dict, *, json: Any = None, params: dict | None = None, write: bool = False) -> Any:
    site_id = _site_for_user(user, write=write)
    if write:
        tenant.guard_site(user, site_id)
    headers = _headers(user, site_id)
    try:
        async with _client() as client:
            response = await client.request(method, f"{API_PREFIX}{path}", json=json, params=params, headers=headers)
    except httpx.HTTPError as exc:
        log.warning("resolveai_platform.unreachable", error=type(exc).__name__)
        raise _not_connected("The ResolveAI worker is not reachable.") from exc
    if response.status_code >= 400:
        try:
            detail = response.json()
        except ValueError:
            detail = {"message": response.text[:200]}
        raise HTTPException(response.status_code if response.status_code < 500 else status.HTTP_502_BAD_GATEWAY, detail)
    return response.json()


def _no_demo(user: dict) -> None:
    if tenant.is_demo_user(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "The ResolveAI agent platform calls paid models and is not available to the demo account.")


async def _runtime() -> dict[str, Any] | None:
    """What the worker is actually running on, from its own public /health. None if it cannot be read."""
    try:
        async with _client() as client:
            health = (await client.get("/health", timeout=8)).json()
    except (httpx.HTTPError, ValueError):
        return None
    if not isinstance(health, dict):
        return None
    llm = health.get("llm_provider", {})
    vector, graph = health.get("vector_store", {}), health.get("graph_store", {})
    return {"model_provider": llm.get("status", "unknown"), "model_provider_name": llm.get("provider"),
            "vector_backend": vector.get("backend"), "indexed_points": vector.get("total_points"), "collections": vector.get("collections"),
            "graph_backend": graph.get("backend"), "case_store": "supabase" if health.get("supabase", {}).get("status") == "configured" else "local"}


@router.get("/status", summary="Is the private ResolveAI worker connected? Lists its domain packs when it is.")
async def platform_status(user: CurrentUserDep, _staff: dict = Depends(require_role(*STAFF))) -> dict:
    try:
        domains = await _forward("GET", "/domains", user)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
        return {"connected": False, **detail}
    return {"connected": True, "domains": domains, "runtime": await _runtime()}


@router.get("/cases", summary="This user's cases on the worker")
async def list_cases(user: CurrentUserDep, domain: str | None = Query(None, pattern=r"^[a-z_]+$", max_length=40),
                     _staff: dict = Depends(require_role(*STAFF))) -> dict:
    return {"cases": await _forward("GET", "/cases", user, params={"domain": domain} if domain else None)}


@router.get("/case", summary="One case")
async def get_case(user: CurrentUserDep, case_id: str = Query(pattern=CASE_ID), _staff: dict = Depends(require_role(*STAFF))) -> dict:
    return await _forward("GET", f"/cases/{case_id}", user)


@router.post("/cases", summary="Create a case")
async def create_case(body: CaseBody, user: CurrentUserDep, _staff: dict = Depends(require_role(*STAFF))) -> dict:
    _no_demo(user)
    return await _forward("POST", "/cases", user, json=body.model_dump(), write=True)


@router.post("/agents/ask", summary="Ask the domain research agent a question (no case needed)")
async def ask(body: AskBody, user: CurrentUserDep, _staff: dict = Depends(require_role(*STAFF))) -> dict:
    _no_demo(user)
    return await _forward("POST", "/agents/ask", user, json=body.model_dump(), write=True)


@router.post("/agents/run-case", summary="Run the multi-agent investigation for a case")
async def run_case(body: RunBody, user: CurrentUserDep, _staff: dict = Depends(require_role(*STAFF))) -> dict:
    _no_demo(user)
    return await _forward("POST", "/agents/run-case", user, json=body.model_dump(), write=True)


@router.post("/agents/investigate", summary="Evidence-first investigation: ResolveAI's routing, retrieval, scoring and citations (no model needed)")
async def investigate(body: InvestigateBody, user: CurrentUserDep, _staff: dict = Depends(require_role(*STAFF))) -> dict:
    _no_demo(user)
    return await _forward("POST", "/kairos/investigate", user, json=body.model_dump(), write=True)


@router.get("/agents/runs", summary="Recorded agent runs for a case")
async def runs(user: CurrentUserDep, case_id: str = Query(pattern=CASE_ID), _staff: dict = Depends(require_role(*STAFF))) -> dict:
    return {"runs": await _forward("GET", f"/agents/runs/{case_id}", user)}


# --- Read-only views over one case or the indexed corpus. Only this tenant's cases are reachable (the worker namespaces
# --- ownership); the worker's cross-citizen aggregates (institution radar, similar cases) are deliberately not exposed.

@router.post("/search", summary="Search the indexed domain corpus (regulations, policies, FAQs)")
async def search(body: SearchBody, user: CurrentUserDep, _staff: dict = Depends(require_role(*STAFF))) -> dict:
    return await _forward("POST", "/search", user, json=body.model_dump())


@router.get("/case-graph", summary="Case, institution, document and appeal graph for one case")
async def case_graph(user: CurrentUserDep, case_id: str = Query(pattern=CASE_ID), _staff: dict = Depends(require_role(*STAFF))) -> dict:
    return await _forward("GET", f"/graph/case/{case_id}/graph", user)


@router.get("/reasoning-trail", summary="Recorded agent steps for the latest run, ordered")
async def reasoning_trail(user: CurrentUserDep, case_id: str = Query(pattern=CASE_ID), _staff: dict = Depends(require_role(*STAFF))) -> dict:
    return await _forward("GET", f"/graph/case/{case_id}/reasoning-trail", user)


@router.get("/timeline", summary="Case events")
async def timeline(user: CurrentUserDep, case_id: str = Query(pattern=CASE_ID), _staff: dict = Depends(require_role(*STAFF))) -> dict:
    return {"events": await _forward("GET", f"/timeline/{case_id}", user)}


@router.get("/report", summary="Full report for one case including its latest analysis")
async def report(user: CurrentUserDep, case_id: str = Query(pattern=CASE_ID), _staff: dict = Depends(require_role(*STAFF))) -> dict:
    return await _forward("GET", f"/reports/case/{case_id}", user)


@router.get("/summary", summary="Case, appeal and domain totals for this tenant")
async def summary(user: CurrentUserDep, _staff: dict = Depends(require_role(*STAFF))) -> dict:
    return await _forward("GET", "/reports/summary", user)
