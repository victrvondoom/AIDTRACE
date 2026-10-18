"""Fraud investigation, native to Kairos (migrated from track1-agent: graph tools, freeze policy, agent runtime).

Mounted at /fraud. The agent proposes; code decides the freeze set (`policy.decide_freeze`); a human approves.
Differences from the standalone original, all deliberate: tenant-scoped graph (`fraud_<site>`), the approver is the
signed-in user, and an approval is re-validated against the CURRENT graph (a ring that changed since the proposal
makes the approval stale instead of freezing accounts on old evidence). Nothing leaves the synthetic graph.
"""
from __future__ import annotations

import asyncio
import json
import random
import threading
import time
import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from api.dependencies import CurrentUserDep, SettingsDep, require_role
from api.routers.resolveai import _site_for_user
from api.services import tenant
from domains.fraud import actions, config, policy, seed
from domains.fraud.investigator import Investigator
from domains.fraud.store import GraphStore
from domains.fraud.tools import GraphTools

log = structlog.get_logger(__name__)
router = APIRouter()
STAFF = ("engineer", "reliability", "admin")
MAX_EVENTS = 400
_runs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


class StartRequest(BaseModel):
    use_llm: bool = False


def _store(settings, site_id: str) -> GraphStore:
    try:
        store = GraphStore(settings.FALKORDB_URL, f"fraud_{site_id}")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, {"status": "GRAPH_UNAVAILABLE", "message": "FalkorDB is unreachable."}) from exc
    if not store.ping():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, {"status": "GRAPH_UNAVAILABLE", "message": "FalkorDB ping failed."})
    return store


def _scope(user: dict, *, write: bool) -> str:
    site_id = _site_for_user(user, write=write)
    if write:
        tenant.guard_site(user, site_id)
    return site_id


async def _run(fn):
    try:
        return await asyncio.to_thread(fn)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        log.warning("fraud.failed", error=repr(exc))
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "The fraud graph is unavailable.") from exc


def _lab_graph(nodes: list[dict], edges: list[dict]) -> dict:
    return {"nodes": [{"id": n["id"], "type": n["label"], "label": str(n["name"]), "props": {}} for n in nodes],
            "edges": [{"source": e["source"], "target": e["target"], "rel": e["type"], "weight": 1} for e in edges]}


@router.get("/health", summary="Fraud graph connectivity and whether a network is loaded")
async def health(user: CurrentUserDep, settings: SettingsDep, _staff: dict = Depends(require_role(*STAFF))) -> dict:
    site_id = _scope(user, write=False)

    def work() -> dict:
        try:
            store = GraphStore(settings.FALKORDB_URL, f"fraud_{site_id}")
            if not store.ping():
                return {"falkordb": False}
            return {"falkordb": True, "graph": store.graph_name, "loaded": store.query("MATCH (a:Account) RETURN count(a)")[0][0] > 0,
                    "llm_available": bool(config.ANTHROPIC_API_KEY)}
        except Exception:  # noqa: BLE001
            return {"falkordb": False}
    return await asyncio.to_thread(work)


@router.post("/seed", summary="Load the synthetic fraud network (planted rings and a household decoy) into this site's graph")
async def seed_network(user: CurrentUserDep, settings: SettingsDep, _staff: dict = Depends(require_role(*STAFF))) -> dict:
    site_id = _scope(user, write=True)
    tenant.guard_site(user, site_id)

    def work() -> dict:
        store = _store(settings, site_id)
        data = seed.build_dataset(random.Random(seed.SEED))
        counts = seed.load(store, data)
        return {"graph": store.graph_name, "counts": counts, "synthetic": True}
    return await _run(work)


@router.get("/flagged", summary="Flagged transactions and their accounts")
async def flagged(user: CurrentUserDep, settings: SettingsDep, _staff: dict = Depends(require_role(*STAFF))) -> dict:
    site_id = _scope(user, write=False)
    return {"transactions": await _run(lambda: GraphTools(_store(settings, site_id)).flagged_transactions())}


@router.get("/neighborhood", summary="Two-hop subgraph around an account, in Graph Lab shape")
async def neighborhood(user: CurrentUserDep, settings: SettingsDep, account_id: str = Query(max_length=40, pattern=r"^[A-Za-z0-9_.-]+$"),
                       _staff: dict = Depends(require_role(*STAFF))) -> dict:
    site_id = _scope(user, write=False)
    hood = await _run(lambda: GraphTools(_store(settings, site_id)).neighborhood(account_id))
    return {"graph": _lab_graph(hood["nodes"], hood["edges"])}


@router.get("/ring", summary="Accounts linked by shared device or card, with the evidence path to each")
async def ring(user: CurrentUserDep, settings: SettingsDep, account_id: str = Query(max_length=40, pattern=r"^[A-Za-z0-9_.-]+$"),
               _staff: dict = Depends(require_role(*STAFF))) -> dict:
    site_id = _scope(user, write=False)
    tools_members = await _run(lambda: GraphTools(_store(settings, site_id)).ring_members(account_id))
    nodes: dict[str, dict] = {}
    edges: dict[tuple, dict] = {}
    for member in tools_members:
        path = member["path"]
        for node in path:
            nodes.setdefault(f"{node['label']}:{node['id']}", {"id": f"{node['label']}:{node['id']}", "label": node["label"], "name": node["id"]})
        for i, rel in enumerate(member["rels"]):
            a, b = f"{path[i]['label']}:{path[i]['id']}", f"{path[i + 1]['label']}:{path[i + 1]['id']}"
            edges[(a, b, rel)] = {"source": a, "target": b, "type": rel}
    return {"account_id": account_id, "members": tools_members, "graph": _lab_graph(list(nodes.values()), list(edges.values()))}


def _emit(run: dict[str, Any], event: dict) -> None:
    with _lock:
        if len(run["events"]) < MAX_EVENTS:
            run["events"].append({"seq": len(run["events"]), "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **event})
        if event["type"] in ("done", "error"):
            run["status"] = event["type"]
            run["mode"] = event.get("mode", run["mode"])


def _execute(run: dict[str, Any], store: GraphStore, use_llm: bool) -> None:
    tools = GraphTools(store, recorder=lambda rec: _emit(run, {"type": "query", **rec}))
    Investigator(tools, lambda ev: _emit(run, ev), run["run_id"]).run(use_llm=use_llm)
    try:  # persist the execution record so history survives a restart
        store.query("MERGE (r:Run {id: $id}) SET r.status = $s, r.mode = $m, r.started_at = $t, r.events = $e",
                    {"id": run["run_id"], "s": run["status"], "m": run["mode"], "t": run["started_at"], "e": json.dumps(run["events"], default=str)})
    except Exception as exc:  # noqa: BLE001
        log.warning("fraud.run_persist_failed", error=repr(exc))


@router.post("/investigations", status_code=202, summary="Start an investigation of every flagged transaction")
async def start(body: StartRequest, user: CurrentUserDep, settings: SettingsDep, _staff: dict = Depends(require_role(*STAFF))) -> dict:
    site_id = _scope(user, write=True)
    tenant.guard_site(user, site_id)
    llm = body.use_llm and bool(config.ANTHROPIC_API_KEY) and not tenant.is_demo_user(user)
    store = await _run(lambda: _store(settings, site_id))
    run_id = uuid.uuid4().hex[:12]
    run = {"run_id": run_id, "site": site_id, "status": "running", "mode": "llm" if llm else "deterministic",
           "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "events": []}
    with _lock:
        _runs[run_id] = run
    threading.Thread(target=_execute, args=(run, store, llm), daemon=True).start()
    return {"run_id": run_id, "mode": run["mode"]}


@router.get("/investigation", summary="Status, event trace and proposals of one run")
async def investigation(user: CurrentUserDep, settings: SettingsDep, run_id: str = Query(max_length=32, pattern=r"^[a-f0-9]+$"),
                        _staff: dict = Depends(require_role(*STAFF))) -> dict:
    site_id = _scope(user, write=False)
    run = _runs.get(run_id)
    if run is None or run["site"] != site_id:  # never serve another tenant's run
        def stored() -> dict | None:
            rows = _store(settings, site_id).query("MATCH (r:Run {id: $id}) RETURN r.status, r.mode, r.started_at, r.events", {"id": run_id})
            return {"run_id": run_id, "status": rows[0][0], "mode": rows[0][1], "started_at": rows[0][2], "events": json.loads(rows[0][3] or "[]")} if rows else None
        run = await _run(stored)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown run.")
    with _lock:
        events = list(run["events"])
    return {"run_id": run_id, "status": run["status"], "mode": run["mode"], "started_at": run["started_at"], "events": events,
            "proposals": [e["action"] for e in events if e["type"] == "proposal"]}


@router.get("/actions", summary="Proposed, executed and rejected actions")
async def list_actions(user: CurrentUserDep, settings: SettingsDep, _staff: dict = Depends(require_role(*STAFF))) -> dict:
    site_id = _scope(user, write=False)
    return {"actions": await _run(lambda: GraphTools(_store(settings, site_id)).list_actions())}


def _still_valid(store: GraphStore, action_id: str) -> tuple[bool, list[str], list[str]]:
    """Re-derive the freeze set from the graph as it is NOW and compare it with what was proposed."""
    row = store.query("MATCH (x:Action {id: $id}) OPTIONAL MATCH (x)-[:TARGETS]->(a:Account) RETURN collect(a.id)", {"id": action_id})
    proposed = sorted(t for t in (row[0][0] if row else []) if t)
    current: set[str] = set()
    for account in proposed:
        decision = policy.decide_freeze(account, GraphTools(store).ring_members(account))
        if decision:
            current |= set(decision["targets"])
    return (bool(proposed) and set(proposed) <= current), proposed, sorted(current)


@router.post("/actions/approve", summary="Human approval; refused if the evidence changed since the proposal")
async def approve(action_id: str, user: CurrentUserDep, settings: SettingsDep, _staff: dict = Depends(require_role(*STAFF))) -> dict:
    site_id = _scope(user, write=True)
    tenant.guard_site(user, site_id)

    def work() -> dict:
        store = _store(settings, site_id)
        ok, proposed, current = _still_valid(store, action_id)
        if proposed and not ok:
            store.query("MATCH (x:Action {id: $id}) WHERE x.status = 'PROPOSED' SET x.status = 'INVALIDATED'", {"id": action_id})
            return {"error": "EVIDENCE_CHANGED", "message": "The ring no longer supports this freeze; the proposal was invalidated.",
                    "proposed": proposed, "current": current}
        result = actions.approve(store, action_id)
        if "error" not in result:
            store.query("MATCH (x:Action {id: $id}) SET x.approved_by = $u", {"id": action_id, "u": str(user.get("user_id", "reviewer"))})
        return result
    result = await _run(work)
    if "error" in result:
        raise HTTPException(status.HTTP_409_CONFLICT, result)
    return result


@router.post("/actions/reject", summary="Reject a proposed action")
async def reject(action_id: str, user: CurrentUserDep, settings: SettingsDep, _staff: dict = Depends(require_role(*STAFF))) -> dict:
    site_id = _scope(user, write=True)
    tenant.guard_site(user, site_id)
    result = await _run(lambda: actions.reject(_store(settings, site_id), action_id))
    if "error" in result:
        raise HTTPException(status.HTTP_409_CONFLICT, result)
    return result
