"""Read-only tools the AIDTRACE agent may call.

Each tool is a name, an argument schema and one bounded call into an existing service. Nothing else is reachable:
no Cypher, no SQL, no shell, no HTTP and no write path. The memory object a tool receives is built by the router
from the caller's authenticated site, so a tool cannot read another site's graph. Results are data. Text inside
them is evidence to quote, never an instruction to follow.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import structlog
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from api.services.memory import greenchain_decisions

log = structlog.get_logger(__name__)

ID = r"^[A-Za-z0-9][A-Za-z0-9._:\-]{0,127}$"
MAX_ITEMS = 25
MAX_RESULT_CHARS = 12_000
# Keys that name tenancy or people rather than evidence. They are never offered to the model as citations.
NOT_EVIDENCE = {"site_id", "user_id", "reviewer", "created_by"}


class SiteMemory(Protocol):
    """The read side of `AgentMemory`, bound to one authenticated site."""

    def snapshot(self) -> dict[str, Any]: ...
    def eligibility(self, action_id: str) -> dict[str, Any]: ...
    def impact_preview(self, source_id: str) -> dict[str, Any]: ...
    def handoffs(self) -> list[dict[str, Any]]: ...


class _Args(BaseModel):
    # Extra keys are refused. A model that adds a site_id or a write flag is rejected, not silently ignored.
    model_config = ConfigDict(extra="forbid")


class SnapshotArgs(_Args):
    limit: int = Field(default=10, ge=1, le=MAX_ITEMS, description="Most items returned for each list.")


class ActionArgs(_Args):
    action_id: str = Field(pattern=ID, description="An action id from get_memory_snapshot.")


class SourceArgs(_Args):
    source_id: str = Field(pattern=ID, description="A source version id from get_memory_snapshot. Nothing is changed.")


class HandoffArgs(_Args):
    limit: int = Field(default=10, ge=1, le=MAX_ITEMS)


class WhatIfArgs(_Args):
    dataset: Literal["USEEIO", "EMBER", "GLEC", "NDGAIN"]
    country: str = Field(pattern=r"^[A-Za-z]{2}$")
    factor: float = Field(gt=0.05, le=100)
    transport_mode: Literal["sea", "air", "rail", "road"] = "sea"


def _snapshot(mem: SiteMemory, a: SnapshotArgs) -> dict[str, Any]:
    snap = mem.snapshot()
    out: dict[str, Any] = {}
    for key in ("memories", "decisions", "actions", "sources"):
        items = snap.get(key) or []
        out[key] = {"total": len(items), "shown": items[: a.limit]}
    return out


def _eligibility(mem: SiteMemory, a: ActionArgs) -> dict[str, Any]:
    return mem.eligibility(a.action_id)


def _impact(mem: SiteMemory, a: SourceArgs) -> dict[str, Any]:
    result = mem.impact_preview(a.source_id)
    stale = result.get("would_mark_stale") or []
    return {**result, "would_mark_stale": stale[:MAX_ITEMS], "total_would_mark_stale": len(stale)}


def _handoffs(mem: SiteMemory, a: HandoffArgs) -> dict[str, Any]:
    rows = mem.handoffs()
    return {"total": len(rows), "shown": rows[: a.limit]}


def _what_if(_mem: SiteMemory | None, a: WhatIfArgs) -> dict[str, Any]:
    # A dry run over reference datasets. It reads no site graph and writes nothing.
    return greenchain_decisions.preview_revision(dataset=a.dataset, country=a.country.upper(), factor=a.factor, transport_mode=a.transport_mode)


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args: type[_Args]
    run: Callable[[Any, Any], Any]


TOOLS: dict[str, Tool] = {t.name: t for t in (
    Tool("get_memory_snapshot", "Memories, decisions, actions and sources in this site's graph, with live eligibility for each action. Call this first.", SnapshotArgs, _snapshot),
    Tool("get_action_eligibility", "Whether one action may be approved now, the reasons it may not, and whether its approval is still current.", ActionArgs, _eligibility),
    Tool("get_graph_impact", "Dry run: which records would go stale if this source version were superseded. Changes nothing.", SourceArgs, _impact),
    Tool("get_agent_handoffs", "Which agent produced each memory, which other agents recalled it, and whether that memory is still usable.", HandoffArgs, _handoffs),
    Tool("preview_supplier_what_if", "Dry run of the GreenChain supplier ranking under one revised factor. Writes nothing.", WhatIfArgs, _what_if),
)}


def tool_schemas() -> list[dict[str, Any]]:
    """The tool list sent to the model. Derived from the same argument models that validate calls."""
    return [{"name": t.name, "description": t.description, "input_schema": t.args.model_json_schema()} for t in TOOLS.values()]


def collect_ids(value: Any) -> set[str]:
    """Every string under an `id` or `*_id` key. These are the only ids the model may cite."""
    found: set[str] = set()
    stack = [value]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for key, child in node.items():
                if isinstance(child, str) and key not in NOT_EVIDENCE and (key == "id" or key.endswith("_id")):
                    found.add(child)
                stack.append(child)
        elif isinstance(node, list):
            stack.extend(node)
    return found


def execute(name: str, raw_args: Any, mem: SiteMemory | None) -> dict[str, Any]:
    """Run one registered tool. Returns {ok, data | error, source_ids}. A bad request is an answer, not an exception."""
    tool = TOOLS.get(name)
    if tool is None:
        return {"ok": False, "error": "unsupported_tool", "source_ids": []}
    if not isinstance(raw_args, dict):
        return {"ok": False, "error": "invalid_arguments", "source_ids": []}
    try:
        args = tool.args.model_validate(raw_args)
    except ValidationError:
        return {"ok": False, "error": "invalid_arguments", "source_ids": []}
    try:
        data = tool.run(mem, args)
    except LookupError:
        return {"ok": False, "error": "not_found", "source_ids": []}
    except Exception as exc:  # noqa: BLE001 - a failing graph store is a result the model must see, not a crash
        log.warning("aidtrace_agent.tool_failed", tool=name, error=type(exc).__name__)
        return {"ok": False, "error": "graph_unavailable", "source_ids": []}
    if len(json.dumps(data, default=str)) > MAX_RESULT_CHARS:
        note = "The result is larger than the agent may read. Ask for a smaller limit or one record."
        return {"ok": True, "truncated": True, "data": {"note": note}, "source_ids": []}
    return {"ok": True, "data": data, "source_ids": sorted(collect_ids(data))}
