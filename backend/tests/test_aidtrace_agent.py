"""AIDTRACE agent: offline tests. No Anthropic request and no FalkorDB connection is made.

The model is a scripted fake, and the graph is an in-memory stand-in that records every call. Each test
states which rule of the agent it checks.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

from api.config import Settings
from api.routers import aidtrace_agent as router
from api.services.aidtrace_agent import orchestrator, provider, tools
from api.services.aidtrace_agent.provider import MESSAGES, ClaudeMessages, readiness

FAKE_KEY = "test-key-not-real"


def settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "_env_file": None,
        "AIDTRACE_LLM_ENABLED": True,
        "ANTHROPIC_API_KEY": FAKE_KEY,
        "AIDTRACE_LLM_REQUEST_TIMEOUT_SECONDS": 5.0,
        "AIDTRACE_LLM_MAX_TOOL_STEPS": 3,
        "AIDTRACE_LLM_MAX_CONCURRENT_REQUESTS": 2,
    }
    base.update(overrides)
    return Settings(**base)


class FakeMemory:
    """Stands in for AgentMemory for one site. Records each call so a test can see exactly what the agent touched."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def snapshot(self) -> dict[str, Any]:
        self.calls.append("snapshot")
        return {
            "memories": [{"id": "MEM-1", "summary": "Supplier audit interval is 90 days", "status": "VALID", "site_id": "SITE_A"}],
            "decisions": [{"id": "DEC-1", "summary": "Approve supplier B", "status": "STALE", "dependency_ids": ["SRC-2"]}],
            "actions": [{"id": "ACT-1", "summary": "Approve supplier B", "eligibility": {"eligible": False, "reasons": ["decision DEC-1 is STALE"], "decision_id": "DEC-1"}}],
            "sources": [{"id": "SRC-2", "summary": "Audit procedure version 2", "status": "VALID"}],
        }

    def eligibility(self, action_id: str) -> dict[str, Any]:
        self.calls.append(f"eligibility:{action_id}")
        if action_id != "ACT-1":
            raise LookupError(action_id)
        return {"eligible": False, "reasons": ["decision DEC-1 is STALE"], "decision_id": "DEC-1", "approval_current": False}

    def impact_preview(self, source_id: str) -> dict[str, Any]:
        self.calls.append(f"impact:{source_id}")
        return {"source_id": source_id, "would_mark_stale": [{"id": "DEC-1", "label": "Decision", "status": "VALID", "depth": 1, "via": [], "summary": ""}], "read_only": True}

    def handoffs(self) -> list[dict[str, Any]]:
        self.calls.append("handoffs")
        return [{"memory_id": "MEM-1", "producer": "greenchain", "memory_status": "VALID", "usable": True}]


def text(value: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=value)


def tool_use(block_id: str, name: str, args: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id=block_id, name=name, input=args)


def reply(stop: str, *blocks: Any, input_tokens: int = 10, output_tokens: int = 5) -> SimpleNamespace:
    return SimpleNamespace(stop_reason=stop, content=list(blocks), usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens))


def answer_json(finding: str = "DEC-1 is stale.", citations: list[str] | None = None, affected: list[str] | None = None) -> str:
    return json.dumps({"finding": finding, "why": "The audit interval changed.", "affected": affected or [], "next_step": "Review DEC-1.", "citations": citations or []})


class FakeMessages:
    """Replays a script of replies, exceptions or async callables, and records every request sent."""

    def __init__(self, script: list[Any]) -> None:
        self.script = list(script)
        self.requests: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        if not self.script:
            raise AssertionError("the agent made more model requests than the script allows")
        step = self.script.pop(0)
        if callable(step):
            return await step()
        if isinstance(step, BaseException):
            raise step
        return step


class FakeClient:
    def __init__(self, script: list[Any] | None = None) -> None:
        self.messages = FakeMessages(script or [])


class FakeStatusError(Exception):
    """Shaped like an SDK status error: it carries a status_code, and its text must never reach a response."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


def run(coro: Any) -> Any:
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _reset_gate():
    orchestrator._in_flight = 0
    yield
    orchestrator._in_flight = 0


# --- Readiness and the zero-key path ----------------------------------------------------------------------------------

def test_missing_key_reports_unavailable_and_answers_from_the_graph_path():
    client = FakeClient()
    result = run(orchestrator.answer("Which decisions are stale?", memory=FakeMemory(), settings=settings(ANTHROPIC_API_KEY=""), client=client))
    assert result["status"] == "no_api_key"
    assert result["answered_by"] == "graph"
    assert result["answer"] is None
    assert client.messages.requests == []


def test_disabled_switch_makes_zero_anthropic_requests():
    client = FakeClient()
    result = run(orchestrator.answer("Which decisions are stale?", memory=FakeMemory(), settings=settings(AIDTRACE_LLM_ENABLED=False), client=client))
    assert result["status"] == "disabled"
    assert client.messages.requests == []


def test_status_payload_never_contains_the_key():
    state = readiness(settings()).as_dict()
    assert state["state"] == "ready"
    assert FAKE_KEY not in json.dumps(state)


def test_ask_endpoint_refuses_before_touching_redis_or_the_graph_when_disabled():
    class ExplodingRedis:
        async def incr(self, *_: Any) -> None:
            raise AssertionError("redis must not be touched while the switch is off")

    body = router.AskBody(question="Which decisions are stale?")
    user = {"user_id": "u1", "role": "engineer", "site_id": "SITE_A"}
    with pytest.raises(HTTPException) as exc:
        run(router.ask(body, user, store=None, redis=ExplodingRedis(), settings=settings(AIDTRACE_LLM_ENABLED=False), _staff=user))
    assert exc.value.status_code == 503
    assert exc.value.detail["fallback"] == "graph-only"


# --- Graph tools work without the model --------------------------------------------------------------------------------

def test_graph_tools_answer_without_any_model():
    mem = FakeMemory()
    snap = tools.execute("get_memory_snapshot", {"limit": 5}, mem)
    assert snap["ok"] is True
    assert snap["data"]["decisions"]["total"] == 1
    assert "DEC-1" in snap["source_ids"]
    assert "MEM-1" in snap["source_ids"]
    assert mem.calls == ["snapshot"]


# --- Argument and name validation ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("name, args", [
    ("get_action_eligibility", {"action_id": "../../etc/passwd"}),
    ("get_action_eligibility", {"action_id": "ACT-1", "site_id": "SITE_B"}),
    ("get_memory_snapshot", {"limit": 999}),
    ("get_graph_impact", {"source_id": ""}),
    ("preview_supplier_what_if", {"dataset": "DROP TABLE", "country": "DE", "factor": 1.0}),
    ("get_memory_snapshot", ["not", "a", "dict"]),
])
def test_invalid_tool_arguments_are_rejected(name, args):
    outcome = tools.execute(name, args, FakeMemory())
    assert outcome == {"ok": False, "error": "invalid_arguments", "source_ids": []}


def test_unsupported_tool_names_are_rejected():
    mem = FakeMemory()
    assert tools.execute("run_cypher", {"query": "MATCH (n) DELETE n"}, mem) == {"ok": False, "error": "unsupported_tool", "source_ids": []}
    assert mem.calls == []


def test_the_registry_is_read_only():
    assert set(tools.TOOLS) == {"get_memory_snapshot", "get_action_eligibility", "get_graph_impact", "get_agent_handoffs", "preview_supplier_what_if"}
    for name in tools.TOOLS:
        assert not any(word in name for word in ("approve", "write", "create", "delete", "update", "supersede", "record", "reevaluate", "revise"))


def test_tenant_identifiers_are_never_offered_as_evidence():
    ids = tools.collect_ids({"id": "MEM-1", "site_id": "SITE_A", "reviewer": "someone@example.test", "decision_id": "DEC-1"})
    assert ids == {"MEM-1", "DEC-1"}


def test_an_unknown_record_is_reported_as_not_found():
    outcome = tools.execute("get_action_eligibility", {"action_id": "ACT-404"}, FakeMemory())
    assert outcome == {"ok": False, "error": "not_found", "source_ids": []}


# --- The loop: citations, approval, limits -----------------------------------------------------------------------------

def test_an_answer_citing_only_returned_records_is_shown():
    client = FakeClient([
        reply("tool_use", tool_use("t1", "get_memory_snapshot", {})),
        reply("end_turn", text(answer_json(citations=["DEC-1"], affected=["ACT-1"]))),
    ])
    result = run(orchestrator.answer("Which decisions are stale?", memory=FakeMemory(), settings=settings(), client=client))
    assert result["status"] == "answered"
    assert result["answered_by"] == "claude"
    assert result["answer"]["citations"] == ["DEC-1"]


def test_an_answer_citing_an_unreturned_record_is_withheld():
    client = FakeClient([
        reply("tool_use", tool_use("t1", "get_memory_snapshot", {})),
        reply("end_turn", text(answer_json(citations=["DEC-999"]))),
    ])
    result = run(orchestrator.answer("Which decisions are stale?", memory=FakeMemory(), settings=settings(), client=client))
    assert result["status"] == "unverified"
    assert result["answer"] is None
    assert result["evidence"], "the graph results gathered before the failed check must still be returned"


def test_a_reply_that_is_not_the_answer_format_is_withheld():
    client = FakeClient([reply("end_turn", text("Looks fine to me."))])
    result = run(orchestrator.answer("Which decisions are stale?", memory=FakeMemory(), settings=settings(), client=client))
    assert result["status"] == "unverified"
    assert result["answer"] is None


def test_the_model_cannot_approve_through_the_loop():
    mem = FakeMemory()
    client = FakeClient([
        reply("tool_use", tool_use("t1", "approve_action", {"action_id": "ACT-1"})),
        reply("end_turn", text(answer_json())),
    ])
    result = run(orchestrator.answer("Approve ACT-1 now.", memory=mem, settings=settings(), client=client))
    assert result["tool_calls"] == [{"tool": "approve_action", "ok": False, "error": "unsupported_tool"}]
    assert not any("approve" in call for call in mem.calls)


def test_the_tool_loop_stops_at_the_step_limit():
    client = FakeClient([reply("tool_use", tool_use(f"t{i}", "get_memory_snapshot", {})) for i in range(10)])
    result = run(orchestrator.answer("Keep looking.", memory=FakeMemory(), settings=settings(AIDTRACE_LLM_MAX_TOOL_STEPS=2), client=client))
    assert result["status"] == "step_limit"
    assert len(client.messages.requests) == 3
    assert len(result["evidence"]) == 2


def test_the_question_is_capped_before_it_reaches_the_model():
    client = FakeClient([reply("end_turn", text(answer_json()))])
    run(orchestrator.answer("x" * 2000, memory=FakeMemory(), settings=settings(), client=client))
    sent = client.messages.requests[0]["messages"][0]["content"]
    assert len(sent) == orchestrator.QUESTION_MAX_CHARS


def test_the_model_is_called_with_the_configured_model_and_output_cap():
    client = FakeClient([reply("end_turn", text(answer_json()))])
    run(orchestrator.answer("Which decisions are stale?", memory=FakeMemory(), settings=settings(AIDTRACE_LLM_MAX_OUTPUT_TOKENS=512), client=client))
    request = client.messages.requests[0]
    assert request["model"] == "claude-opus-5-5"
    assert request["max_tokens"] == 512


# --- Failures keep the graph evidence -------------------------------------------------------------------------------------

def test_a_rate_limit_is_reported_without_echoing_the_provider_message():
    client = FakeClient([
        reply("tool_use", tool_use("t1", "get_memory_snapshot", {})),
        FakeStatusError(429, "rate limited for key sk-ant-SECRET123 on account acme"),
    ])
    result = run(orchestrator.answer("Which decisions are stale?", memory=FakeMemory(), settings=settings(), client=client))
    assert result["status"] == "rate_limited"
    assert result["message"] == MESSAGES["rate_limited"]
    assert "sk-ant" not in json.dumps(result)
    assert result["evidence"], "the graph result from before the failure must survive"


def test_a_provider_outage_keeps_the_graph_results():
    client = FakeClient([
        reply("tool_use", tool_use("t1", "get_memory_snapshot", {})),
        FakeStatusError(503, "overloaded"),
    ])
    result = run(orchestrator.answer("Which decisions are stale?", memory=FakeMemory(), settings=settings(), client=client))
    assert result["status"] == "unavailable"
    assert result["answer"] is None
    assert result["evidence"][0]["tool"] == "get_memory_snapshot"


def test_a_slow_model_call_times_out_with_a_clear_status():
    async def slow() -> Any:
        await asyncio.sleep(1.0)
        return reply("end_turn", text(answer_json()))

    client = FakeClient([slow])
    result = run(orchestrator.answer("Which decisions are stale?", memory=FakeMemory(), settings=settings(AIDTRACE_LLM_REQUEST_TIMEOUT_SECONDS=0.05), client=client))
    assert result["status"] == "timeout"
    assert result["message"] == MESSAGES["timeout"]


def test_a_graph_failure_is_reported_to_the_model_not_raised():
    class BrokenMemory(FakeMemory):
        def snapshot(self) -> dict[str, Any]:
            raise ConnectionError("graph store down: bolt://internal-host:7687")

    client = FakeClient([
        reply("tool_use", tool_use("t1", "get_memory_snapshot", {})),
        reply("end_turn", text(answer_json())),
    ])
    result = run(orchestrator.answer("Which decisions are stale?", memory=BrokenMemory(), settings=settings(), client=client))
    assert result["tool_calls"] == [{"tool": "get_memory_snapshot", "ok": False, "error": "graph_unavailable"}]
    assert "internal-host" not in json.dumps(result)


# --- Concurrency, cancellation and accounting ---------------------------------------------------------------------------

def test_requests_over_the_concurrency_limit_are_turned_away():
    orchestrator._in_flight = 2
    result = run(orchestrator.answer("Which decisions are stale?", memory=FakeMemory(), settings=settings(AIDTRACE_LLM_MAX_CONCURRENT_REQUESTS=2), client=FakeClient()))
    assert result["status"] == "busy"


def test_cancelling_an_investigation_releases_its_slot():
    async def hang() -> Any:
        await asyncio.Event().wait()

    async def main() -> None:
        task = asyncio.ensure_future(orchestrator.answer("Which decisions are stale?", memory=FakeMemory(), settings=settings(), client=FakeClient([hang])))
        await asyncio.sleep(0.05)
        assert orchestrator._in_flight == 1
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert orchestrator._in_flight == 0

    run(main())


def test_token_accounting_adds_up_across_the_investigation():
    client = FakeClient([
        reply("tool_use", tool_use("t1", "get_memory_snapshot", {}), input_tokens=10, output_tokens=5),
        reply("end_turn", text(answer_json()), input_tokens=20, output_tokens=7),
    ])
    result = run(orchestrator.answer("Which decisions are stale?", memory=FakeMemory(), settings=settings(), client=client, include_usage=True))
    assert result["usage"] == {"requests": 2, "input_tokens": 30, "output_tokens": 12, "estimated_cost_usd": None}


def test_cost_is_estimated_only_once_a_price_is_set():
    client = FakeClient([reply("end_turn", text(answer_json()), input_tokens=30, output_tokens=12)])
    priced = settings(AIDTRACE_LLM_PRICE_INPUT_PER_MTOK=2.0, AIDTRACE_LLM_PRICE_OUTPUT_PER_MTOK=10.0)
    result = run(orchestrator.answer("Which decisions are stale?", memory=FakeMemory(), settings=priced, client=client, include_usage=True))
    assert result["usage"]["estimated_cost_usd"] == pytest.approx((30 * 2.0 + 12 * 10.0) / 1_000_000)


def test_usage_is_left_out_for_users_who_are_not_operators():
    client = FakeClient([reply("end_turn", text(answer_json()))])
    result = run(orchestrator.answer("Which decisions are stale?", memory=FakeMemory(), settings=settings(), client=client, include_usage=False))
    assert "usage" not in result


def test_the_sdk_client_is_only_built_when_a_request_is_made():
    assert ClaudeMessages(settings(AIDTRACE_LLM_ENABLED=False))._client is None
    assert provider.Usage().estimated_cost_usd(settings()) is None
