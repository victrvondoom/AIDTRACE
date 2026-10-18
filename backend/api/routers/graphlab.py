"""Graph Lab routes: run the shared graph-reasoning engines on a scenario, a pasted graph or the site graph."""
from __future__ import annotations

import asyncio
import re
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
    node_dist: dict[str, int] = {}
    for n in graph["nodes"]:
        t = n.get("type") or "Unknown"
        node_dist[t] = node_dist.get(t, 0) + 1
    rel_dist: dict[str, int] = {}
    for e in graph["edges"]:
        r = e.get("rel") or "RELATED_TO"
        rel_dist[r] = rel_dist.get(r, 0) + 1

    sorted_node_dist = [{"type": k, "count": v} for k, v in sorted(node_dist.items(), key=lambda x: -x[1])]
    sorted_rel_dist = [{"relationship": k, "count": v} for k, v in sorted(rel_dist.items(), key=lambda x: -x[1])]

    return {
        "graph": graph,
        "truncated": exported["truncated"],
        "empty": not graph["nodes"],
        "falkordb": {
            "status": "connected",
            "graph_name": make_store().graph_name(site_id),
            "engine": "FalkorDB",
            "host": "configured connection",
            "site_id": site_id,
            "node_count": len(graph["nodes"]),
            "edge_count": len(graph["edges"]),
            "node_distribution": sorted_node_dist,
            "relationship_distribution": sorted_rel_dist,
        },
    }


class CypherQueryRequest(BaseModel):
    query: str = Field(min_length=3, max_length=1500)
    params: dict[str, Any] = Field(default_factory=dict)


@router.post("/site-cypher", summary="Execute a read-only Cypher query against the user's FalkorDB graph")
async def site_cypher(
    body: CypherQueryRequest,
    current_user: CurrentUserDep,
    make_store: StoreFactory,
    _staff: dict = Depends(require_role(*STAFF)),
) -> dict:
    site_id = _site_for_user(current_user, write=False)
    q = body.query.strip()
    if ";" in q or "//" in q or "/*" in q or not q.upper().startswith(("MATCH ", "RETURN ", "WITH ")):
        raise HTTPException(status_code=422, detail="Provide one read-only Cypher query.")
    explicit_limit = re.search(r"\bLIMIT\s+(\d+)\s*$", q, re.IGNORECASE)
    if (re.search(r"\bLIMIT\b", q, re.IGNORECASE) and explicit_limit is None) or (explicit_limit and int(explicit_limit.group(1)) > 100):
        raise HTTPException(status_code=422, detail="The result limit must be a literal integer of at most 100.")
    if explicit_limit is None:
        q += " LIMIT 100"
    try:
        def run() -> dict:
            store = make_store()
            graph_name = store.graph_name(site_id)
            if graph_name not in store._client.list_graphs():
                raise LookupError("This site has no graph yet.")
            g = store._graph(site_id)
            # GRAPH.RO_QUERY enforces read-only behavior even if Cypher parsing evolves.
            res = g.ro_query(q, body.params, timeout=store._query_timeout_ms)
            headers = [col[1] for col in res.header] if hasattr(res, "header") and res.header else []
            rows = res.result_set[:100] if hasattr(res, "result_set") else []
            runtime = getattr(res, "run_time_ms", 0.0)
            return {
                "graph_name": graph_name,
                "query": q,
                "run_time_ms": round(float(runtime), 2) if runtime else 0.0,
                "header": headers,
                "rows": rows,
                "row_count": len(rows),
                "engine": "FalkorDB GraphBLAS OpenCypher",
            }
        return await asyncio.to_thread(run)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log.warning("graphlab.site_cypher_failed", error=repr(exc), site_id=site_id)
        raise HTTPException(status_code=503, detail="FalkorDB query failed or is unavailable.") from exc



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
