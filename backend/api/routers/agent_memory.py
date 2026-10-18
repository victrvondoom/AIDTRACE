"""Agent memory, evidence revision and approval gating, on the caller's site graph (FalkorDB).

Mounted at /agent-memory. Staff roles only; every operation is bound to the token-derived site, so one site can never read or
change another's memory. Approvals are bound to the decision revision the reviewer saw: a stale or changed decision is refused
with specific reasons. Nothing here executes an external action.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from api.dependencies import CurrentUserDep, FalkorDriftDep, require_role
from api.routers import resolveai_platform as platform
from api.routers.resolveai import _site_for_user
from api.services import tenant
from api.services.drift.model import ContractError
from api.services.drift.store import TraversalLimitExceeded
from api.services.memory import greenchain_decisions, resolveai_memory
from api.services.memory.agent_memory import AgentMemory
from api.services.memory.context import build_llm_context

log = structlog.get_logger(__name__)
router = APIRouter()
STAFF = ("engineer", "reliability", "admin")
ID = r"^[A-Za-z0-9][A-Za-z0-9._:\-]{0,127}$"


class RecordBody(BaseModel):
    scenario_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_\-]{1,40}$")
    transport_mode: str = Field(default="sea", pattern=r"^(sea|air|rail|road)$")


class ReviseBody(BaseModel):
    scenario_id: str = Field(pattern=r"^[A-Za-z0-9_\-]{1,40}$")
    dataset: str = Field(pattern=r"^(USEEIO|EMBER|GLEC|NDGAIN)$")
    country: str = Field(pattern=r"^[A-Za-z]{2}$")
    factor: float = Field(gt=0.05, le=100)
    label: str = Field(min_length=3, max_length=80)
    transport_mode: str = Field(default="sea", pattern=r"^(sea|air|rail|road)$")


class ApproveBody(BaseModel):
    action_id: str = Field(pattern=ID)
    note: str = Field(default="", max_length=300)


class RememberCaseBody(BaseModel):
    case_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,80}$")


class RecallBody(BaseModel):
    agent_id: str = Field(pattern=ID)
    fact_key: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=10, ge=1, le=50)


class ContextBody(BaseModel):
    agent_id: str = Field(pattern=ID)
    fact_key: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/\-]{0,199}$")
    limit: int = Field(default=5, ge=1, le=10)


async def _run(fn):
    try:
        return await asyncio.to_thread(fn)
    except ContractError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except TraversalLimitExceeded as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The impact traversal exceeded its safety limit.") from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        log.warning("agent_memory.failed", error=repr(exc))
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, {"status": "GRAPH_UNAVAILABLE", "message": "FalkorDB is unavailable, so no fresh analysis was done."}) from exc


def _memory(user: dict, store, *, write: bool) -> AgentMemory:
    site = _site_for_user(user, write=write)
    if write:
        tenant.guard_site(user, site)
    return AgentMemory(store, site)


@router.get("/snapshot", summary="Memories, decisions, actions and sources in this site's graph, with live eligibility")
async def snapshot(user: CurrentUserDep, store: FalkorDriftDep, _staff: dict = Depends(require_role(*STAFF))) -> dict[str, Any]:
    mem = _memory(user, store, write=False)
    return await _run(mem.snapshot)


@router.post("/greenchain/record", summary="Score the illustrative GreenChain suppliers and store the decision as evidence-backed memory")
async def record(body: RecordBody, user: CurrentUserDep, store: FalkorDriftDep, _staff: dict = Depends(require_role(*STAFF))) -> dict[str, Any]:
    mem = _memory(user, store, write=True)
    scenario = body.scenario_id or f"s{uuid.uuid4().hex[:6]}"
    return await _run(lambda: greenchain_decisions.record_scenario(mem, scenario_id=scenario, transport_mode=body.transport_mode))


@router.post("/greenchain/revise", summary="Counterfactual: a reference dataset is revised; replay the evidence cascade with real re-scoring")
async def revise(body: ReviseBody, user: CurrentUserDep, store: FalkorDriftDep, _staff: dict = Depends(require_role(*STAFF))) -> dict[str, Any]:
    mem = _memory(user, store, write=True)
    return await _run(lambda: greenchain_decisions.revise_dataset(
        mem, scenario_id=body.scenario_id, dataset=body.dataset, country=body.country, factor=body.factor, label=body.label, transport_mode=body.transport_mode))


@router.get("/actions/eligibility", summary="May this action be approved now, and is its approval still current?")
async def eligibility(user: CurrentUserDep, store: FalkorDriftDep, action_id: str = Query(pattern=ID), _staff: dict = Depends(require_role(*STAFF))) -> dict[str, Any]:
    mem = _memory(user, store, write=False)
    return await _run(lambda: mem.eligibility(action_id))


@router.post("/actions/approve", summary="Approve the current revision of a decision's action; refused if its evidence is stale or changed")
async def approve(body: ApproveBody, user: CurrentUserDep, store: FalkorDriftDep, _staff: dict = Depends(require_role(*STAFF))) -> dict[str, Any]:
    mem = _memory(user, store, write=True)
    reviewer = str(user.get("email") or user.get("user_id") or "unknown")
    result = await _run(lambda: mem.approve_action(body.action_id, reviewer, body.note))
    if not result["approved"]:
        raise HTTPException(status.HTTP_409_CONFLICT, {"status": "APPROVAL_REFUSED", "message": "Approval refused: " + "; ".join(result["reasons"]) + ".", "reasons": result["reasons"], "action_id": body.action_id})
    return result


@router.post("/recall", summary="What an agent may rely on now (stale memory is returned as blocked, with the reason)")
async def recall(body: RecallBody, user: CurrentUserDep, store: FalkorDriftDep, _staff: dict = Depends(require_role(*STAFF))) -> dict[str, Any]:
    mem = _memory(user, store, write=True)  # recalling records which memory influenced the agent
    return await _run(lambda: mem.recall(agent_id=body.agent_id, fact_key=body.fact_key, limit=body.limit))


@router.post("/context", summary="Verified, site-scoped graph memory for an agent, with claim and source provenance")
async def context(body: ContextBody, user: CurrentUserDep, store: FalkorDriftDep, _staff: dict = Depends(require_role(*STAFF))) -> dict[str, Any]:
    mem = _memory(user, store, write=True)  # retrieval records exactly which memory influenced this agent
    return await _run(lambda: build_llm_context(
        mem.recall(agent_id=body.agent_id, fact_key=body.fact_key, limit=body.limit, verified_only=True),
        fact_key=body.fact_key,
    ))


@router.post("/greenchain/preview-revision", summary="Dry run: how would the ranking change under a revised factor? Writes nothing")
async def preview(body: ReviseBody, user: CurrentUserDep, store: FalkorDriftDep, _staff: dict = Depends(require_role(*STAFF))) -> dict[str, Any]:
    _memory(user, store, write=False)
    return await _run(lambda: greenchain_decisions.preview_revision(dataset=body.dataset, country=body.country, factor=body.factor, transport_mode=body.transport_mode))


@router.get("/impact-preview", summary="Dry run: what would go stale if this source were superseded? Writes nothing")
async def impact_preview(user: CurrentUserDep, store: FalkorDriftDep, source_id: str = Query(pattern=ID), _staff: dict = Depends(require_role(*STAFF))) -> dict[str, Any]:
    mem = _memory(user, store, write=False)
    return await _run(lambda: mem.impact_preview(source_id))


@router.get("/handoffs", summary="Which agent produced a memory and which other agents recalled it")
async def handoffs(user: CurrentUserDep, store: FalkorDriftDep, _staff: dict = Depends(require_role(*STAFF))) -> dict[str, Any]:
    mem = _memory(user, store, write=False)
    return {"handoffs": await _run(mem.handoffs)}


@router.post("/resolveai/remember", summary="Store a case's latest ResolveAI evidence investigation as memory another agent can recall")
async def remember_case(body: RememberCaseBody, user: CurrentUserDep, store: FalkorDriftDep, _staff: dict = Depends(require_role(*STAFF))) -> dict[str, Any]:
    mem = _memory(user, store, write=True)
    report = await platform._forward("GET", f"/reports/case/{body.case_id}", user)
    case = report.get("case")
    if not case:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found.")
    runs = [r for r in report.get("agent_runs", []) if r.get("workflow_name") == "kairos_evidence_investigation"]
    if not runs:
        raise HTTPException(status.HTTP_409_CONFLICT, "Run the evidence investigation for this case first; there is nothing to remember yet.")
    investigation = runs[-1].get("output") or {}
    domain = case["domain"] if isinstance(case["domain"], str) else str(case["domain"])
    return await _run(lambda: resolveai_memory.remember_investigation(
        mem, case_id=case["id"], institution=case.get("institution_name", ""), domain=domain, investigation=investigation))


@router.get("/greenchain/report", summary="Procurement memo for one scenario, written only from the graph")
async def greenchain_report(user: CurrentUserDep, store: FalkorDriftDep, scenario_id: str = Query(pattern=r"^[A-Za-z0-9_\-]{1,40}$"),
                            _staff: dict = Depends(require_role(*STAFF))) -> dict[str, Any]:
    mem = _memory(user, store, write=False)
    return await _run(lambda: greenchain_decisions.scenario_report(mem, scenario_id=scenario_id))
