"""One agent: a chat model, a system prompt, and the tools it was granted."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .backends import ChatBackend, ToolCall
from .errors import AgentError, ToolError
from .tools import ToolRegistry
from .trace import Trace

ARG_TRACE_CHARS = 500


class AgentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system: str = Field(min_length=1, max_length=8000)
    max_steps: int = Field(default=4, ge=1, le=20)
    tools: list[str] = Field(default_factory=list, max_length=32)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=1, le=8192)
    tool_timeout_s: float = Field(default=30.0, gt=0, le=600)


async def run_agent(
    spec: AgentSpec,
    *,
    backend: ChatBackend,
    tools: ToolRegistry,
    user_input: str,
    trace: Trace,
    task_id: str,
    attempt: int,
) -> str:
    """Drive the model until it answers in text. Tool calls are executed only if granted.

    Raises BackendError for transport or server failures (the scheduler may retry these) and
    AgentError when the model cannot reach an answer within ``max_steps``.
    """
    schemas = tools.schemas(spec.tools) if spec.tools else None
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": spec.system},
        {"role": "user", "content": user_input},
    ]
    scope = {"task": task_id, "attempt": attempt}

    for step in range(1, spec.max_steps + 1):
        trace.record("LLM_REQUEST", step=step, backend=backend.name, message_count=len(messages), **scope)
        response = await backend.chat(
            messages, tools=schemas, temperature=spec.temperature, max_tokens=spec.max_tokens
        )
        trace.record(
            "LLM_RESPONSE",
            step=step,
            finish_reason=response.finish_reason,
            tool_call_count=len(response.tool_calls),
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            latency_ms=response.latency_ms,
            **scope,
        )

        if response.tool_calls:
            messages.append(
                {
                    "role": "assistant",
                    "content": response.content or "",
                    "tool_calls": [_as_wire_call(call) for call in response.tool_calls],
                }
            )
            for call in response.tool_calls:
                result = await _execute(call, spec=spec, tools=tools, trace=trace, scope=scope, step=step)
                messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
            continue

        if response.content and response.content.strip():
            trace.record("AGENT_ANSWERED", steps=step, **scope)
            return response.content
        raise AgentError("model returned neither an answer nor a tool call", kind="empty_reply")

    raise AgentError(f"no answer after {spec.max_steps} steps", kind="step_limit")


def _as_wire_call(call: ToolCall) -> dict[str, Any]:
    return {"id": call.id, "type": "function", "function": {"name": call.name, "arguments": call.arguments}}


async def _execute(
    call: ToolCall,
    *,
    spec: AgentSpec,
    tools: ToolRegistry,
    trace: Trace,
    scope: dict[str, Any],
    step: int,
) -> str:
    """Run one granted tool call. Failures are returned to the model as data so it can recover."""
    if call.name not in spec.tools:
        trace.record("TOOL_DENIED", tool=call.name, step=step, **scope)
        return json.dumps({"error": f"tool {call.name!r} is not granted to this agent"})

    trace.record("TOOL_CALLED", tool=call.name, arguments=call.arguments[:ARG_TRACE_CHARS], step=step, **scope)
    try:
        result = await tools.invoke(call.name, call.arguments, timeout_s=spec.tool_timeout_s)
    except ToolError as exc:
        trace.record("TOOL_ERROR", tool=call.name, error=str(exc), step=step, **scope)
        return json.dumps({"error": str(exc)})
    trace.record("TOOL_COMPLETED", tool=call.name, result_chars=len(result), step=step, **scope)
    return result
