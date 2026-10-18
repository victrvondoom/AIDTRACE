"""AIDTRACE agent endpoints. Mounted at /aidtrace-agent.

Read-only. A question is answered by Claude only when the switch is on and a key is configured, and only from the
caller's own site graph, through the tools in services/aidtrace_agent/tools.py. Otherwise /ask answers 503, and the
workspace keeps its deterministic routes, which stay the first answer path for every question.
"""

from __future__ import annotations

import time
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.dependencies import CurrentUserDep, FalkorDriftDep, RedisDep, SettingsDep, demo_llm_budget, require_role
from api.routers.resolveai import _site_for_user
from api.services import tenant
from api.services.aidtrace_agent import orchestrator
from api.services.aidtrace_agent.provider import readiness
from api.services.memory.agent_memory import AgentMemory

log = structlog.get_logger(__name__)
router = APIRouter()
STAFF = ("engineer", "reliability", "admin")
OPERATORS = ("admin",)  # token usage and cost estimates are for operators only


class AskBody(BaseModel):
    question: str = Field(min_length=3, max_length=orchestrator.QUESTION_MAX_CHARS)


async def _user_budget(user: dict[str, Any], redis: Any, settings: Any) -> None:
    """Hourly cap per signed-in staff user. Demo accounts are counted by demo_llm_budget instead.

    Fails open on a Redis error, as demo_llm_budget does, so a cache outage cannot stop reasoning.
    """
    if tenant.is_demo_user(user):
        return
    who = user.get("user_id") or user.get("email") or "unknown"
    key = f"kairos:aidtrace_llm:{who}:{int(time.time() // 3600)}"
    try:
        used = await redis.incr(key)
        if used == 1:
            await redis.expire(key, 3600)
    except Exception as exc:  # noqa: BLE001
        log.warning("aidtrace_agent.budget_redis_unavailable", error=type(exc).__name__)
        return
    if used > settings.AIDTRACE_LLM_MAX_REQUESTS_PER_USER_PER_HOUR:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            {"status": "USER_LIMIT", "message": "This account has used its reasoning requests for this hour."})


@router.get("/status", summary="Whether model reasoning is available, and the reason when it is not")
async def agent_status(settings: SettingsDep, _staff: dict = Depends(require_role(*STAFF))) -> dict[str, Any]:
    return readiness(settings).as_dict()


@router.post("/ask", summary="Answer a question from the site graph, with Claude reasoning when it is enabled")
async def ask(body: AskBody, user: CurrentUserDep, store: FalkorDriftDep, redis: RedisDep, settings: SettingsDep,
              _staff: dict = Depends(require_role(*STAFF))) -> dict[str, Any]:
    state = readiness(settings)
    if not state.ready:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            {"status": state.state, "message": state.reason, "fallback": "graph-only"})
    if tenant.is_demo_user(user):
        await demo_llm_budget(user, redis, settings)
    else:
        await _user_budget(user, redis, settings)
    # Built from the authenticated site, so every tool call stays inside it.
    memory = AgentMemory(store, _site_for_user(user, write=False))
    return await orchestrator.answer(body.question, memory=memory, settings=settings, include_usage=user.get("role") in OPERATORS)
