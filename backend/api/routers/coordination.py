"""FastAPI Router for Multi-Agent Coordination on FalkorDB. Mounted at /coordination.

Endpoints:
- GET  /capabilities: Registry status and prerequisites (not proof of execution)
- GET  /runs: List coordination runs for site
- POST /runs: Plan and execute a multi-agent investigation (Coordinator + Workers)
- GET  /runs/{run_id}: Get run status, task DAG, events, and verified findings
- POST /runs/{run_id}/resume: Resume an interrupted run
- POST /unlearning/delete: Preserved compatibility route that fails closed until all stores are integrated
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from api.dependencies import CurrentUserDep, FalkorDriftDep, require_role
from api.routers.resolveai import _site_for_user
from api.services import tenant
from api.services.coordination import (
    CAPABILITY_REGISTRY,
    CoordinationGraphStore,
    CoordinatorAgent,
    CoordinationStoreUnavailable,
    DependencyScheduler,
)

router = APIRouter()
STAFF = ("engineer", "reliability", "admin")


class PlanRunRequest(BaseModel):
    goal: str = Field(min_length=3, max_length=500)
    domain: str = Field(default="general", max_length=100)
    context_ids: list[str] = Field(default_factory=list)
    execute_now: bool = Field(default=True)


class VerifiedDeleteRequest(BaseModel):
    entity_id: str = Field(min_length=1, max_length=128)
    entity_type: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=3, max_length=500)


def _get_store(store: Any, user: dict[str, Any], write: bool = False) -> CoordinationGraphStore:
    site_id = _site_for_user(user, write=write)
    tenant.guard_site(user, site_id)
    if store is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="FalkorDB is required for coordination; no in-memory fallback is enabled.")
    return CoordinationGraphStore(drift_store=store, site_id=site_id)


async def _graph_call(fn, *args, **kwargs):
    try:
        return await asyncio.to_thread(fn, *args, **kwargs)
    except CoordinationStoreUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="The site's FalkorDB coordination graph is unavailable; no local result was substituted.") from exc


@router.get("/capabilities", summary="List registered domain capabilities across Packs A through I")
async def list_capabilities(_staff: dict = Depends(require_role(*STAFF))) -> dict[str, Any]:
    caps = [c.to_dict() for c in CAPABILITY_REGISTRY.list_all()]
    return {
        "total": len(caps),
        "capabilities": caps,
    }


@router.get("/runs", summary="List recent coordination runs")
async def list_runs(user: CurrentUserDep, store: FalkorDriftDep,
                    domain: str = "all", limit: int = Query(default=10, ge=1, le=100),
                    _staff: dict = Depends(require_role(*STAFF))) -> dict[str, Any]:
    c_store = _get_store(store, user)
    runs = await _graph_call(c_store.find_past_campaigns, domain, limit)
    return {
        "total": len(runs),
        "runs": [r.to_dict() for r in runs],
    }


@router.post("/runs", summary="Plan and execute a multi-agent investigation")
async def create_and_run(body: PlanRunRequest, user: CurrentUserDep, store: FalkorDriftDep,
                         _staff: dict = Depends(require_role(*STAFF))) -> dict[str, Any]:
    c_store = _get_store(store, user, write=True)
    coordinator = CoordinatorAgent(c_store)

    run = await _graph_call(
        coordinator.plan_investigation,
        goal=body.goal,
        domain=body.domain,
        site_id=c_store.site_id,
        context_ids=body.context_ids,
    )

    if body.execute_now:
        execution_summary = await _graph_call(coordinator.execute_investigation, run.run_id)
        return {
            "run": run.to_dict(),
            "execution": execution_summary,
        }

    tasks = await _graph_call(c_store.list_tasks_for_run, run.run_id)
    return {
        "run": run.to_dict(),
        "tasks": [t.to_dict() for t in tasks],
    }


@router.get("/runs/{run_id}", summary="Get run DAG status, events, and findings")
async def get_run_details(run_id: str, user: CurrentUserDep, store: FalkorDriftDep,
                          _staff: dict = Depends(require_role(*STAFF))) -> dict[str, Any]:
    c_store = _get_store(store, user)
    run = await _graph_call(c_store.get_run, run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run '{run_id}' not found")

    tasks = await _graph_call(c_store.list_tasks_for_run, run_id)
    events = await _graph_call(c_store.list_events_for_run, run_id)
    checkpoint = await _graph_call(c_store.get_latest_checkpoint, run_id)

    return {
        "run": run.to_dict(),
        "tasks": [t.to_dict() for t in tasks],
        "events": [e.to_dict() for e in events],
        "checkpoint": checkpoint.to_dict() if checkpoint else None,
    }


@router.post("/runs/{run_id}/resume", summary="Resume an interrupted run from checkpoint")
async def resume_run(run_id: str, user: CurrentUserDep, store: FalkorDriftDep,
                     _staff: dict = Depends(require_role(*STAFF))) -> dict[str, Any]:
    c_store = _get_store(store, user, write=True)
    scheduler = DependencyScheduler(c_store)
    coordinator = CoordinatorAgent(c_store)

    recovered = await _graph_call(scheduler.recover_run, run_id)
    if not recovered:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run '{run_id}' not found")

    execution_summary = await _graph_call(coordinator.execute_investigation, run_id)
    return {
        "recovered_run": recovered.to_dict(),
        "execution": execution_summary,
    }


@router.post("/runs/{run_id}/tasks/{task_id}/cancel", summary="Cancel a nonterminal task in this site's run")
async def cancel_task(run_id: str, task_id: str, user: CurrentUserDep, store: FalkorDriftDep,
                      _staff: dict = Depends(require_role(*STAFF))) -> dict[str, Any]:
    c_store = _get_store(store, user, write=True)
    task = await _graph_call(c_store.get_task, task_id)
    if not task or task.run_id != run_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found in this run")
    actor = str(user.get("email") or user.get("user_id") or "operator")
    cancelled = await _graph_call(DependencyScheduler(c_store).cancel_task, task_id, actor)
    if not cancelled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Task is already terminal or its state changed")
    return {"run_id": run_id, "task_id": task_id, "status": "CANCELLED"}


@router.post("/unlearning/delete", summary="Unavailable until governed deletion is verified across all storage layers")
async def verified_delete(body: VerifiedDeleteRequest, user: CurrentUserDep, store: FalkorDriftDep,
                          _staff: dict = Depends(require_role(*STAFF))) -> dict[str, Any]:
    _get_store(store, user, write=True)
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"status": "UNAVAILABLE", "data_changed": False,
                "reason": "Deletion requires retention-policy review and verified removal from every applicable graph, vector, search, relational, and audit store."},
    )
