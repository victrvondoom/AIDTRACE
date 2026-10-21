"""GreenChain procurement intelligence, native to Kairos (migrated from the GreenChain project, MIT).

Mounted at /greenchain. Same session and role gates as the rest of Kairos. Scoring, transport rescoring, the
what-if re-ranking and the graph builder are deterministic and use GreenChain's real models and reference data.
Live supplier discovery, prompt-based scenario editing and report generation call external providers (Dedalus,
K2, Gemini): they need the provider keys, are reported NOT_CONNECTED without them, and are closed to the demo role.
"""
from __future__ import annotations

import asyncio
from typing import Any

import structlog
from domains.greenchain import kairos_adapter as adapter
from domains.greenchain import main as gc
from domains.greenchain.ml_scorer import compute_composite_scores
from domains.greenchain.transport import rescore_transport
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.dependencies import CurrentUserDep, SettingsDep, require_role
from api.routers.resolveai import _site_for_user
from api.services import tenant
from api.services.consumer.store import GraphStore

log = structlog.get_logger(__name__)
router = APIRouter()
STAFF = ("engineer", "reliability", "admin")
MAX_CANDIDATES = 200


class GraphBody(BaseModel):
    results: list[dict[str, Any]] = Field(max_length=MAX_CANDIDATES)


class WhatIfBody(BaseModel):
    remove: str = Field(max_length=120)
    transport_mode: str = "sea"
    weights: dict[str, float] | None = None


def _bounded(items: list) -> list:
    if len(items) > MAX_CANDIDATES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"At most {MAX_CANDIDATES} candidates per request.")
    return items


def _no_demo(user: dict) -> None:
    if tenant.is_demo_user(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Live provider calls are not available to the demo account.")


def _store(settings, site_id: str) -> GraphStore:
    try:
        store = GraphStore(settings.FALKORDB_URL, f"greenchain_{site_id}")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, {"status": "GRAPH_UNAVAILABLE", "message": "FalkorDB is unreachable."}) from exc
    if not store.ping():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, {"status": "GRAPH_UNAVAILABLE", "message": "FalkorDB ping failed."})
    return store


@router.get("/health", summary="Model, reference-data and provider readiness (no secrets)")
async def health(_staff: dict = Depends(require_role(*STAFF))) -> dict:
    def work() -> dict:
        from domains.greenchain.ml_bridge import get_model_backend
        backend = get_model_backend()
        data_ok = bool(__import__("os").path.isdir(__import__("os").environ.get("GREENCHAIN_DATA_DIR", "")))
        missing = gc._missing_component_agent_keys()
        return {"ml_models": backend is not None, "model_backend": backend, "reference_data": data_ok,
                "live_discovery": "NOT_CONNECTED" if missing else "CONFIGURED", "missing_provider_keys": missing,
                "demo_mode": "ILLUSTRATIVE_DEMO available"}
    return await asyncio.to_thread(work)


@router.get("/demo", summary="Illustrative scenario scored by the real ML pipeline, with its graph")
async def demo(transport_mode: str = "sea", _staff: dict = Depends(require_role(*STAFF))) -> dict:
    try:
        scenario = await asyncio.to_thread(adapter.demo_scenario, transport_mode=transport_mode)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return {**scenario, "graph": adapter.scenario_graph(scenario["results"])}


@router.post("/score", summary="Rank candidates with the configured quantile model and composite scorer")
async def score(req: gc.ScoreRequest, _staff: dict = Depends(require_role(*STAFF))) -> dict:
    _bounded(req.manufacturers)
    try:
        scored = await asyncio.to_thread(compute_composite_scores, req.manufacturers, transport_mode=req.transport_mode, weights=req.weights)
    except Exception as exc:  # noqa: BLE001
        log.warning("greenchain.score_failed", error=repr(exc))
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Scoring failed: {type(exc).__name__}") from exc
    return {"count": len(scored), "results": scored}


@router.post("/rescore-transport", summary="Recompute transport emissions under another mode and re-rank")
async def rescore(req: gc.RescoreRequest, _staff: dict = Depends(require_role(*STAFF))) -> dict:
    _bounded(req.manufacturers)

    def work() -> list[dict]:
        rescored = rescore_transport(req.manufacturers, req.mode)
        rescored.sort(key=lambda x: x.get("scores", {}).get("total_tco2e", float("inf")))
        for i, m in enumerate(rescored, 1):
            m["rank"] = i
        return rescored
    results = await asyncio.to_thread(work)
    return {"count": len(results), "mode": req.mode, "results": results}


@router.post("/whatif/remove-supplier", summary="Which recommendation changes if a demo-pool supplier is removed?")
async def what_if(body: WhatIfBody, _staff: dict = Depends(require_role(*STAFF))) -> dict:
    names = {c["name"] for c in adapter.demo_candidates()}
    if body.remove not in names:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown supplier in the demo pool.")
    return await asyncio.to_thread(adapter.rank_without, adapter.demo_candidates(), body.remove,
                                   transport_mode=body.transport_mode, weights=body.weights)


@router.post("/graph", summary="Build the decision-dependency graph for scored results")
async def build_graph(body: GraphBody, _staff: dict = Depends(require_role(*STAFF))) -> dict:
    return {"graph": adapter.scenario_graph(body.results)}


@router.post("/graph/persist", summary="Persist the scenario graph in this site's FalkorDB graph")
async def persist(body: GraphBody, user: CurrentUserDep, settings: SettingsDep, _staff: dict = Depends(require_role(*STAFF))) -> dict:
    site_id = _site_for_user(user, write=True)
    tenant.guard_site(user, site_id)
    graph = adapter.scenario_graph(body.results)

    def work() -> dict:
        return adapter.persist_graph(_store(settings, site_id), graph)
    try:
        return await asyncio.to_thread(work)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.get("/graph/stored", summary="The persisted scenario graph for this site")
async def stored(user: CurrentUserDep, settings: SettingsDep, _staff: dict = Depends(require_role(*STAFF))) -> dict:
    site_id = _site_for_user(user, write=False)
    return {"graph": await asyncio.to_thread(lambda: adapter.read_graph(_store(settings, site_id)))}


@router.post("/search", summary="Live supplier discovery (Dedalus agents); NOT_CONNECTED without provider keys")
async def search(req: gc.SearchRequest, user: CurrentUserDep, _staff: dict = Depends(require_role(*STAFF))):
    _no_demo(user)
    return await gc.search(req)


@router.post("/search/stream", summary="Live supplier discovery as server-sent events")
async def search_stream(req: gc.SearchRequest, user: CurrentUserDep, _staff: dict = Depends(require_role(*STAFF))) -> StreamingResponse:
    _no_demo(user)
    return await gc.search_stream(req)


@router.post("/scenario/edit", summary="Prompt-based scenario edit (needs the K2 provider key)")
async def edit_scenario(req: gc.ScenarioEditRequestPayload, user: CurrentUserDep, _staff: dict = Depends(require_role(*STAFF))):
    _no_demo(user)
    return await gc.edit_scenario_endpoint(req)


@router.post("/scenario/report", summary="Procurement recommendation report (needs the Gemini key)")
async def scenario_report(req: gc.ScenarioReportRequestPayload, user: CurrentUserDep, _staff: dict = Depends(require_role(*STAFF))):
    _no_demo(user)
    return await gc.generate_scenario_report_endpoint(req)
