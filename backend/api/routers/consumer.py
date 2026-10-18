"""ResolveAI consumer-remedy routes, native to Kairos (ported from the Track 01 project).

Mounted at /resolveai/consumer. Differences from the standalone original, all deliberate:
  * Staff roles only, resolved by the shared Kairos session; no separate login.
  * The graph is tenant-scoped (`resolve_consumer_<site>`); the site comes from the token, never the request.
  * The reviewer recorded on an approval is the authenticated user, not a field the client supplies.
  * No GET route takes a path parameter (the showcase read fence only understands known record names).
Every decision route answers 503 GRAPH_UNAVAILABLE when FalkorDB is down; nothing is ever decided without it.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.dependencies import CurrentUserDep, SettingsDep, require_role
from api.routers.resolveai import _site_for_user
from api.services import tenant
from api.services.consumer import actions, case_data, engine, graphdb, intake
from api.services.consumer.store import GraphStore

log = structlog.get_logger(__name__)
router = APIRouter()
STAFF = ("engineer", "reliability", "admin")


class LoadRequest(BaseModel):
    overrides: dict[str, Any] = Field(default_factory=dict)


class EvidenceRequest(BaseModel):
    status: str = Field(max_length=16)


class SourceRequest(BaseModel):
    verified: bool


class DropEdgeRequest(BaseModel):
    src_label: str = Field(max_length=40)
    src_id: str = Field(max_length=80)
    rel: str = Field(max_length=40)
    dst_label: str = Field(max_length=40)
    dst_id: str = Field(max_length=80)


class ApproveRequest(BaseModel):
    revision: str = Field(max_length=64)


class IntakeRequest(BaseModel):
    text: str = Field(default="", max_length=20000)


def _open(settings, site_id: str) -> GraphStore:
    try:
        return graphdb.open_store(graph_name=f"resolve_consumer_{site_id}", url=settings.FALKORDB_URL)
    except graphdb.GraphUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, {
            "status": "GRAPH_UNAVAILABLE", "message": str(exc), "note": "No decision is possible without FalkorDB."}) from exc
    except ValueError as exc:  # unsafe site id for a graph name
        raise HTTPException(status.HTTP_403_FORBIDDEN, "A valid site assignment is required.") from exc


async def _run(fn: Callable[[], Any]) -> Any:
    try:
        return await asyncio.to_thread(fn)
    except HTTPException:
        raise
    except graphdb.GraphUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, {"status": "GRAPH_UNAVAILABLE", "message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log.warning("consumer.failed", error=repr(exc))
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "The consumer graph is unavailable.") from exc


def _scope(user: dict, *, write: bool) -> str:
    site_id = _site_for_user(user, write=write)
    if write:
        tenant.guard_site(user, site_id)
    return site_id


@router.get("/health", summary="Consumer graph connectivity and whether a case is loaded")
async def health(user: CurrentUserDep, settings: SettingsDep, _staff: dict = Depends(require_role(*STAFF))) -> dict:
    site_id = _scope(user, write=False)

    def work() -> dict:
        try:
            store = graphdb.open_store(graph_name=f"resolve_consumer_{site_id}", url=settings.FALKORDB_URL)
            return {"falkordb": True, "graph": store.graph_name, "case_loaded": store.query("MATCH (c:CitizenCase) RETURN count(c)")[0][0] > 0}
        except graphdb.GraphUnavailable as exc:
            return {"falkordb": False, "message": str(exc)}
    return await asyncio.to_thread(work)


@router.post("/intake", summary="Parse complaint text into facts, domains and gaps (stateless)")
async def intake_complaint(body: IntakeRequest, _staff: dict = Depends(require_role(*STAFF))) -> dict:
    return intake.parse(body.text)


@router.post("/case/load", summary="Write the synthetic case to this site's consumer graph")
async def load_case(body: LoadRequest, user: CurrentUserDep, settings: SettingsDep, _staff: dict = Depends(require_role(*STAFF))) -> dict:
    site_id = _scope(user, write=True)
    tenant.guard_site(user, site_id)

    def work() -> dict:
        store = _open(settings, site_id)
        counts = graphdb.write_case(store, case_data.build_case(body.overrides))
        return {"graph": store.graph_name, "counts": counts, "revision": graphdb.compute_revision(store)}
    return await _run(work)


@router.get("/graph", summary="Nodes and decision edges for the graph views")
async def graph_view(user: CurrentUserDep, settings: SettingsDep, _staff: dict = Depends(require_role(*STAFF))) -> dict:
    site_id = _scope(user, write=False)

    def work() -> dict:
        store = _open(settings, site_id)
        nodes: dict[str, dict] = {}
        for label, node_id, title, text, kind, name in store.query("MATCH (n) RETURN labels(n)[0], n.id, n.title, n.text, n.type, n.name"):
            display = next((x for x in (title, text, kind, name) if x), node_id)
            key = f"{label}:{node_id}"
            nodes[key] = {"id": key, "type": label, "label": str(display)[:60], "props": {}}
        edges = [{"source": f"{r[0]}:{r[1]}", "target": f"{r[2]}:{r[3]}", "rel": r[4]} for r in store.query(
            "MATCH (a)-[r]->(b) WHERE type(r) IN $t RETURN labels(a)[0], a.id, labels(b)[0], b.id, type(r)", {"t": graphdb.DECISION_EDGE_TYPES})]
        return {"graph": {"nodes": list(nodes.values()), "edges": edges}, "revision": graphdb.compute_revision(store)}
    return await _run(work)


@router.get("/state", summary="Evidence and source status exactly as stored")
async def state(user: CurrentUserDep, settings: SettingsDep, _staff: dict = Depends(require_role(*STAFF))) -> dict:
    site_id = _scope(user, write=False)

    def work() -> dict:
        store = _open(settings, site_id)
        evidence = [{"id": r[0], "type": r[1], "status": r[2], "amount": r[3]} for r in store.query(
            "MATCH (e:Evidence) RETURN e.id, e.type, e.status, e.amount ORDER BY e.id")]
        sources = [{"id": r[0], "title": r[1], "verified": bool(r[2])} for r in store.query("MATCH (s:Source) RETURN s.id, s.title, s.verified ORDER BY s.id")]
        return {"evidence": evidence, "sources": sources, "revision": graphdb.compute_revision(store)}
    return await _run(work)


@router.get("/actions", summary="Every draft and approval, INVALIDATED where evidence changed after approval")
async def list_actions(user: CurrentUserDep, settings: SettingsDep, _staff: dict = Depends(require_role(*STAFF))) -> dict:
    site_id = _scope(user, write=False)

    def work() -> list[dict]:
        store = _open(settings, site_id)
        ids = [r[0] for r in store.query("MATCH (a:ProposedAction) RETURN a.id ORDER BY a.created_at DESC")]
        return [actions.status_of(store, i) for i in ids]
    return {"actions": await _run(work)}


@router.post("/analyze", summary="Run the full engine: routing, verification, strategy comparison and a draft")
async def analyze(user: CurrentUserDep, settings: SettingsDep, _staff: dict = Depends(require_role(*STAFF))):
    site_id = _scope(user, write=True)
    tenant.guard_site(user, site_id)
    result = await _run(lambda: engine.analyze(_open(settings, site_id)))
    return JSONResponse(status_code=503, content=result) if result.get("status") == "GRAPH_UNAVAILABLE" else result


@router.post("/evidence", summary="Set an evidence status (attach or remove a document)")
async def set_evidence(evidence_id: str, body: EvidenceRequest, user: CurrentUserDep, settings: SettingsDep,
                       _staff: dict = Depends(require_role(*STAFF))) -> dict:
    site_id = _scope(user, write=True)
    tenant.guard_site(user, site_id)

    def work() -> dict:
        store = _open(settings, site_id)
        graphdb.set_evidence_status(store, evidence_id, body.status)
        return {"evidence_id": evidence_id, "status": body.status, "revision": graphdb.compute_revision(store)}
    return await _run(work)


@router.post("/source", summary="Set a source's verified flag")
async def set_source(source_id: str, body: SourceRequest, user: CurrentUserDep, settings: SettingsDep,
                     _staff: dict = Depends(require_role(*STAFF))) -> dict:
    site_id = _scope(user, write=True)
    tenant.guard_site(user, site_id)

    def work() -> dict:
        store = _open(settings, site_id)
        graphdb.set_source_verified(store, source_id, body.verified)
        return {"source_id": source_id, "verified": body.verified, "revision": graphdb.compute_revision(store)}
    return await _run(work)


@router.post("/edges/drop", summary="Remove one decision relationship (data correction)")
async def drop_edge(body: DropEdgeRequest, user: CurrentUserDep, settings: SettingsDep, _staff: dict = Depends(require_role(*STAFF))) -> dict:
    site_id = _scope(user, write=True)
    tenant.guard_site(user, site_id)

    def work() -> dict:
        store = _open(settings, site_id)
        removed = graphdb.drop_decision_edge(store, body.src_label, body.src_id, body.rel, body.dst_label, body.dst_id)
        return {"removed": removed, "revision": graphdb.compute_revision(store)}
    return await _run(work)


@router.post("/actions/approve", summary="Approve a draft; the body must carry the reviewed revision")
async def approve(action_id: str, body: ApproveRequest, user: CurrentUserDep, settings: SettingsDep,
                  _staff: dict = Depends(require_role(*STAFF))) -> dict:
    site_id = _scope(user, write=True)
    tenant.guard_site(user, site_id)
    result = await _run(lambda: actions.approve(_open(settings, site_id), action_id, body.revision, str(user.get("user_id", "reviewer"))))
    if "error" in result:
        raise HTTPException(status.HTTP_409_CONFLICT, result)
    return result


@router.post("/actions/reject", summary="Reject a draft")
async def reject(action_id: str, user: CurrentUserDep, settings: SettingsDep, _staff: dict = Depends(require_role(*STAFF))) -> dict:
    site_id = _scope(user, write=True)
    tenant.guard_site(user, site_id)
    result = await _run(lambda: actions.reject(_open(settings, site_id), action_id))
    if "error" in result:
        raise HTTPException(status.HTTP_409_CONFLICT, result)
    return result
