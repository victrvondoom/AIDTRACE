"""Agent Operations: one view over the four agent runtimes Kairos hosts.

  GET  /agents/runtimes   each runtime's framework, live status, tools and declared interface support
  GET  /agents/interfaces the interface-support matrix (which runtime provides what, natively or only through Kairos)
  GET  /agents/runs       recent runs from every runtime, newest first, in one shape
  POST /agents/tools/invoke  run one safe read-only tool through the shared interface

Every status and run comes from the runtime itself, probed now. A runtime that does not answer is reported UNAVAILABLE with no
runs; nothing is substituted.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from api.dependencies import CurrentUserDep, FalkorDriftDep, SettingsDep, require_role
from api.routers import resolveai_platform as platform
from api.routers.resolveai import _site_for_user
from api.services import tenant
from api.services.agents.runtime import ADAPTERS, Context, support_matrix
from api.services.consumer.store import GraphStore
from api.services.memory.agent_memory import AgentMemory
from api.services.memory.context import build_llm_context

log = structlog.get_logger(__name__)
router = APIRouter()
STAFF = ("engineer", "reliability", "admin")
PROBE_S = 5.0


class InvokeBody(BaseModel):
    runtime: str = Field(pattern=r"^[a-z]+$", max_length=20)
    tool: str = Field(pattern=r"^[a-z_]+$", max_length=40)
    args: dict[str, Any] = Field(default_factory=dict)


def _ctx(user: dict, settings, store, *, write: bool = False) -> Context:
    return Context(user=user, site_id=_site_for_user(user, write=write), settings=settings, store=store)


async def _bounded(coro, default):
    try:
        return await asyncio.wait_for(coro, PROBE_S)
    except Exception as exc:  # noqa: BLE001 - a dead runtime is a status
        log.info("agents.probe_failed", error=type(exc).__name__)
        return default


# ---- live status and runs, one function per runtime ---------------------------------------------------------------------------

async def _status_resolveai(ctx: Context) -> dict[str, Any]:
    runtime = await platform._runtime()
    if runtime is None:
        return {"state": "UNAVAILABLE", "detail": "The private worker did not answer."}
    on = runtime["model_provider"] not in ("disabled", "missing_key")
    return {"state": "OPERATIONAL" if on else "LIMITED", "detail": f"{runtime['indexed_points']} indexed passages; " + ("model provider configured." if on else "no model provider, so LLM agents return placeholders."),
            "metrics": {"indexed_points": runtime["indexed_points"], "model": on}}


async def _runs_resolveai(ctx: Context, limit: int) -> list[dict[str, Any]]:
    try:
        summary = await platform._forward("GET", "/reports/summary", ctx.user)
    except HTTPException:
        return []
    return [{"system": "resolveai", "run_id": str(e.get("id")), "kind": "agent_run", "status": str(e.get("body") or "recorded"), "at": e.get("created_at"),
             "summary": e.get("title") or "agent run", "ref": e.get("case_id")} for e in summary.get("recent_activity", []) if e.get("event_type") == "agent_run"][:limit]


def _fraud_graph(ctx: Context) -> GraphStore | None:
    try:
        store = GraphStore(ctx.settings.FALKORDB_URL, f"fraud_{ctx.site_id}")
        return store if store.ping() else None
    except Exception:  # noqa: BLE001
        return None


async def _status_fraud(ctx: Context) -> dict[str, Any]:
    def work() -> dict[str, Any]:
        g = _fraud_graph(ctx)
        if g is None:
            return {"state": "UNAVAILABLE", "detail": "FalkorDB did not answer."}
        loaded = bool(g.query("MATCH (a:Account) RETURN count(a)")[0][0])
        return {"state": "LIMITED", "detail": "Synthetic transfer network " + ("loaded." if loaded else "not loaded yet."), "metrics": {"loaded": loaded}}
    return await asyncio.to_thread(work)


async def _runs_fraud(ctx: Context, limit: int) -> list[dict[str, Any]]:
    def work() -> list[dict[str, Any]]:
        g = _fraud_graph(ctx)
        if g is None:
            return []
        rows = g.query(f"MATCH (r:Run) RETURN r.id, r.status, r.mode, r.started_at ORDER BY r.started_at DESC LIMIT {int(limit)}")
        return [{"system": "fraud", "run_id": str(i), "kind": "investigation", "status": s, "at": at, "summary": f"{m} investigation", "ref": None} for i, s, m, at in rows]
    return await asyncio.to_thread(work)


async def _status_greenchain(ctx: Context) -> dict[str, Any]:
    from api.routers.hub import _greenchain
    gc = await asyncio.to_thread(_greenchain)
    if not (gc["models"] and gc["data"]):
        return {"state": "UNAVAILABLE", "detail": "Emissions models or reference data are missing."}
    backend = {"catboost": "CatBoost", "xgboost": "XGBoost"}.get(gc.get("model_backend"), "Quantile")
    return {"state": "LIMITED" if gc["missing_provider_keys"] else "OPERATIONAL", "detail": f"{backend} models and reference data loaded."
            + (" Live discovery needs provider keys." if gc["missing_provider_keys"] else ""), "metrics": {"missing_provider_keys": len(gc["missing_provider_keys"])}}


async def _runs_greenchain(ctx: Context, limit: int) -> list[dict[str, Any]]:
    def work() -> list[dict[str, Any]]:
        nodes = ctx.store.list_nodes(ctx.site_id, "Memory", limit=200)
        return [{"system": "greenchain", "run_id": n["id"], "kind": "decision_record", "status": n.get("status"), "at": n.get("recorded_at"), "summary": n.get("summary", "")[:140],
                 "ref": n.get("investigation_ref")} for n in nodes if str(n.get("agent_id", "")).startswith("agent:greenchain")][:limit]
    return await asyncio.to_thread(work)


async def _status_memory(ctx: Context) -> dict[str, Any]:
    info = await asyncio.to_thread(ctx.store.inspect_site, ctx.site_id)
    return {"state": "OPERATIONAL" if info.get("reachable") else "UNAVAILABLE", "detail": "FalkorDB reachable." if info.get("reachable") else "FalkorDB did not answer.",
            "metrics": {"site_graph_exists": bool(info.get("site_graph_exists"))}}


async def _runs_memory(ctx: Context, limit: int) -> list[dict[str, Any]]:
    def work() -> list[dict[str, Any]]:
        return [{"system": "memory", "run_id": n["id"], "kind": "evidence_change", "status": n.get("verdict"), "at": n.get("observed_at"), "summary": n.get("reason") or "source change",
                 "ref": n.get("source_id")} for n in ctx.store.list_nodes(ctx.site_id, "ChangeEvent", limit=100)][:limit]
    return await asyncio.to_thread(work)


STATUS = {"resolveai": _status_resolveai, "fraud": _status_fraud, "greenchain": _status_greenchain, "memory": _status_memory}
RUNS = {"resolveai": _runs_resolveai, "fraud": _runs_fraud, "greenchain": _runs_greenchain, "memory": _runs_memory}


@router.get("/runtimes", summary="Every agent runtime: framework, live status, tools and interface support")
async def runtimes(user: CurrentUserDep, settings: SettingsDep, store: FalkorDriftDep, _staff: dict = Depends(require_role(*STAFF))) -> dict[str, Any]:
    ctx = _ctx(user, settings, store)
    unavailable = {"state": "UNAVAILABLE", "detail": "The runtime did not answer in time."}
    states = await asyncio.gather(*[_bounded(STATUS[a](ctx), unavailable) for a in ADAPTERS])
    return {"runtimes": [{**ad.describe(), "status": st} for ad, st in zip(ADAPTERS.values(), states)], "matrix": support_matrix()}


@router.get("/interfaces", summary="Which runtime provides which shared interface, natively or only through Kairos")
async def interfaces(_staff: dict = Depends(require_role(*STAFF))) -> dict[str, Any]:
    return support_matrix()


@router.get("/runs", summary="Recent runs from every runtime in one shape, newest first")
async def runs(user: CurrentUserDep, settings: SettingsDep, store: FalkorDriftDep, limit: int = Query(20, ge=1, le=100), _staff: dict = Depends(require_role(*STAFF))) -> dict[str, Any]:
    ctx = _ctx(user, settings, store)
    groups = await asyncio.gather(*[_bounded(RUNS[a](ctx, limit), []) for a in ADAPTERS])
    merged = sorted([r for g in groups for r in g], key=lambda r: str(r.get("at") or ""), reverse=True)[:limit]
    return {"runs": merged, "by_system": {a: len(g) for a, g in zip(ADAPTERS, groups)}}


@router.post("/tools/invoke", summary="Run one safe tool through the shared interface")
async def invoke(body: InvokeBody, user: CurrentUserDep, settings: SettingsDep, store: FalkorDriftDep, _staff: dict = Depends(require_role(*STAFF))) -> dict[str, Any]:
    adapter = ADAPTERS.get(body.runtime)
    tool = next((t for t in adapter.tools if t.name == body.tool), None) if adapter else None
    if not adapter or not tool or not tool.invokable:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That tool is not available through the shared interface.")
    if tenant.is_demo_user(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tool invocation is not available to the demo account.")
    ctx = _ctx(user, settings, store, write=True)
    tenant.guard_site(user, ctx.site_id)
    if (body.runtime, body.tool) == ("resolveai", "search_corpus"):
        domain, query = str(body.args.get("domain", "health_insurance")), str(body.args.get("query", ""))
        if len(query) < 3 or len(query) > 1000 or not domain.replace("_", "").isalpha():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "search_corpus needs a domain and a query of 3 to 1000 characters.")
        result = await platform._forward("POST", "/search", user, json={"domain": domain, "query": query, "limit": 5})
        output = {"hits": [{"id": h["id"], "score": h["score"], "title": h["metadata"].get("title"), "text": h["text"][:300]} for h in result["hits"]]}
    elif (body.runtime, body.tool) == ("greenchain", "score_suppliers"):
        from domains.greenchain import kairos_adapter as adapter_gc
        mode = str(body.args.get("transport_mode", "sea"))
        if mode not in ("sea", "air", "rail", "road"):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "transport_mode must be sea, air, rail or road.")
        scored = await asyncio.to_thread(lambda: adapter_gc.score_candidates(adapter_gc.demo_candidates(), transport_mode=mode))
        output = {"ranking": [{"name": r["name"], "rank": r["rank"], "composite": round(float(r["composite_score"]), 2)} for r in scored], "illustrative_candidates": True}
    elif (body.runtime, body.tool) == ("memory", "recall"):
        agent = str(body.args.get("agent_id", "agent:operator"))
        mem = AgentMemory(store, ctx.site_id)
        output = await asyncio.to_thread(lambda: mem.recall(agent_id=agent, fact_key=body.args.get("fact_key"), limit=10))
    elif (body.runtime, body.tool) == ("memory", "context"):
        agent = body.args.get("agent_id")
        fact_key = body.args.get("fact_key")
        limit = body.args.get("limit", 5)
        if (not isinstance(agent, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:\-]{0,127}", agent)
                or not isinstance(fact_key, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/\-]{0,199}", fact_key)
                or not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 10):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "context needs a valid agent_id, exact fact_key and limit of 1 to 10.")
        mem = AgentMemory(store, ctx.site_id)
        output = await asyncio.to_thread(lambda: build_llm_context(
            mem.recall(agent_id=agent, fact_key=fact_key, limit=limit, verified_only=True), fact_key=fact_key))
    else:  # pragma: no cover - guarded by the invokable flag above
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That tool is not available through the shared interface.")
    log.info("agents.tool_invoked", runtime=body.runtime, tool=body.tool, site=ctx.site_id, user=user.get("user_id"))
    return {"runtime": body.runtime, "tool": body.tool, "read_only": tool.read_only, "result": output,
            "trace": {"event": "tool_invoked", "by": str(user.get("user_id")), "site": ctx.site_id}}
