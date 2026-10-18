"""Graph Lab routes: run the shared graph-reasoning engines on a scenario, a pasted graph or the site graph."""
from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from api.dependencies import CurrentUserDep, SettingsDep, get_falkor_drift_store, require_role
from api.routers.resolveai import _site_for_user
from api.services.drift.model import ContractError
from api.services.drift.store import FalkorDriftStore
from api.services.graphlab import algorithms as alg
from api.services.graphlab.registry import ALGORITHMS, SCENARIOS, evaluate_supply_chain, run_algorithm, scenario_list
from api.services.sources import catalog

log = structlog.get_logger(__name__)
router = APIRouter()
STAFF = ("engineer", "reliability", "admin")
MAX_BODY_BYTES = 2_000_000
ANALYZE_TIMEOUT_S = 20


class AnalyzeRequest(BaseModel):
    algorithm: str = Field(max_length=40)
    params: dict[str, Any] = Field(default_factory=dict)
    scenario: str | None = Field(default=None, max_length=40)
    graph: dict[str, Any] | None = None
    site_graph: bool = False


def _store_factory(request: Request, settings: SettingsDep) -> Callable[[], FalkorDriftStore]:
    """Defer FalkorDB construction (it raises when the server is down) so scenario and pasted-graph
    analysis keep working without it; only the site-graph source touches the store."""
    def make() -> FalkorDriftStore:
        override = request.app.dependency_overrides.get(get_falkor_drift_store)
        return override() if override else get_falkor_drift_store(settings)
    return make


StoreFactory = Annotated[Callable[[], FalkorDriftStore], Depends(_store_factory)]


def _provenance(algorithm_id: str) -> dict:
    engine = ALGORITHMS[algorithm_id]
    urls = catalog.repo_urls()
    return {"engine": engine.id, "implementation": "Clean-room standard algorithm; no third-party code is copied.",
            "readme_derived_hypothesis_from": [{"repo": r, "url": urls.get(r)} for r in engine.sources], "tests": engine.test,
            "status": "INTEGRATED_TESTED"}


@router.get("/algorithms", summary="Graph Lab engines with parameters and README provenance")
async def list_algorithms(_staff: dict = Depends(require_role(*STAFF))) -> dict:
    return {"algorithms": [{**a.spec(), "provenance": _provenance(a.id)} for a in ALGORITHMS.values()]}


@router.get("/scenarios", summary="Built-in synthetic scenarios")
async def list_scenarios(_staff: dict = Depends(require_role(*STAFF))) -> dict:
    return {"scenarios": scenario_list()}


@router.get("/evaluation/supply-chain", summary="Evaluate the unified synthetic software and supplier risk workflow")
async def supply_chain_evaluation(_staff: dict = Depends(require_role(*STAFF))) -> dict:
    """Return deterministic case scores and graph-path receipts for the judge evaluation."""
    return evaluate_supply_chain()


@router.get("/scenario", summary="One scenario graph")
async def get_scenario(scenario_id: str = Query(pattern=r"^[a-z_]{1,40}$"), _staff: dict = Depends(require_role(*STAFF))) -> dict:
    scenario = SCENARIOS.get(scenario_id)
    if scenario is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown scenario.")
    return {"id": scenario_id, "title": scenario["title"], "description": scenario["description"],
            "graph": alg.normalize_graph(scenario["graph"]).public(), "recommended": scenario["recommended"]}


@router.get("/site-graph", summary="The caller's site evidence graph from FalkorDB (read-only)")
async def site_graph(current_user: CurrentUserDep, make_store: StoreFactory, _staff: dict = Depends(require_role(*STAFF))) -> dict:
    site_id = _site_for_user(current_user, write=False)
    try:
        exported = await asyncio.to_thread(lambda: make_store().export_graph(site_id))
    except ContractError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log.warning("graphlab.site_graph_failed", error=repr(exc), site_id=site_id)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="FalkorDB is unavailable.") from exc
    graph = alg.normalize_graph(exported).public()
    return {"graph": graph, "truncated": exported["truncated"], "empty": not graph["nodes"]}


@router.post("/analyze", summary="Run one engine; the result is a pure function of the graph and parameters")
async def analyze(body: AnalyzeRequest, request: Request, current_user: CurrentUserDep, make_store: StoreFactory,
                  _staff: dict = Depends(require_role(*STAFF))) -> dict:
    if int(request.headers.get("content-length") or 0) > MAX_BODY_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Graph payload is too large.")
    if body.algorithm not in ALGORITHMS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown algorithm.")
    if sum([body.scenario is not None, body.graph is not None, body.site_graph]) != 1:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Provide exactly one of scenario, graph or site_graph.")
    if body.scenario is not None:
        if body.scenario not in SCENARIOS:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown scenario.")
        payload, origin = SCENARIOS[body.scenario]["graph"], f"scenario:{body.scenario}"
    elif body.site_graph:
        site_id = _site_for_user(current_user, write=False)
        try:
            payload, origin = await asyncio.to_thread(lambda: make_store().export_graph(site_id)), "site:falkordb"
        except Exception as exc:  # noqa: BLE001
            log.warning("graphlab.site_graph_failed", error=repr(exc), site_id=site_id)
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="FalkorDB is unavailable.") from exc
    else:
        payload, origin = body.graph, "payload"

    def work() -> dict:
        graph = alg.normalize_graph(payload)
        return {"graph": graph.public(), "result": run_algorithm(body.algorithm, graph, body.params)}

    started = time.perf_counter()
    try:
        out = await asyncio.wait_for(asyncio.to_thread(work), timeout=ANALYZE_TIMEOUT_S)
    except alg.GraphError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="The analysis exceeded its time budget.") from exc
    return {"algorithm": body.algorithm, "graph_source": origin, **out, "provenance": _provenance(body.algorithm),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1)}
