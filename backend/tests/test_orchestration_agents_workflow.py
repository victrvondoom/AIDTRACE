"""Agent loop, tool grants, workflow validation, and the scheduler's concurrency, retry, and failure rules."""

import asyncio
import json

import pytest

from orchestration.agents import AgentSpec, run_agent
from orchestration.backends import ChatResponse, ScriptedBackend, ToolCall
from orchestration.errors import AgentError, BackendError, ConfigError, ToolError, WorkflowError
from orchestration.scheduler import RetryPolicy, TaskState, run_workflow
from orchestration.tools import ToolRegistry, load_registry
from orchestration.trace import REDACTED, Trace
from orchestration.workflow import load_workflow, render_input


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        "word_count",
        lambda text: {"words": len(text.split())},
        description="Count words.",
        parameters={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
    )
    return registry


def _call(name: str, arguments: str) -> ChatResponse:
    return ChatResponse(
        content=None, tool_calls=(ToolCall(id="c1", name=name, arguments=arguments),), finish_reason="tool_calls"
    )


def _answer(text: str) -> ChatResponse:
    return ChatResponse(content=text, finish_reason="stop")


def _tool_result_seen(messages) -> bool:
    return any(message["role"] == "tool" for message in messages)


def _spec(**overrides) -> AgentSpec:
    return AgentSpec.model_validate({"system": "You are terse.", "max_steps": 3, **overrides})


def _run_agent(spec, backend, *, tools=None, text="input"):
    trace = Trace()
    answer = asyncio.run(
        run_agent(
            spec,
            backend=backend,
            tools=tools or _registry(),
            user_input=text,
            trace=trace,
            task_id="t",
            attempt=1,
        )
    )
    return answer, trace


# --- agent loop and tool grants -------------------------------------------------------------------


def test_granted_tool_runs_and_its_result_reaches_the_model():
    backend = ScriptedBackend(
        responder=lambda messages: _answer("count is 3")
        if _tool_result_seen(messages)
        else _call("word_count", '{"text": "a b c"}')
    )
    answer, trace = _run_agent(_spec(tools=["word_count"]), backend)

    assert answer == "count is 3"
    tool_message = next(m for m in backend.requests[1] if m["role"] == "tool")
    assert json.loads(tool_message["content"]) == {"words": 3}
    assert {"TOOL_CALLED", "TOOL_COMPLETED", "AGENT_ANSWERED"} <= set(trace.types())


def test_ungranted_tool_is_refused_and_never_runs():
    ran: list[bool] = []
    registry = _registry()
    registry.register("delete_everything", lambda: ran.append(True) or "gone", description="Dangerous.")
    backend = ScriptedBackend(
        responder=lambda messages: _answer("done")
        if _tool_result_seen(messages)
        else _call("delete_everything", "{}")
    )
    answer, trace = _run_agent(_spec(tools=["word_count"]), backend, tools=registry)

    assert answer == "done"
    assert ran == []
    assert "TOOL_DENIED" in trace.types()
    denied = next(m for m in backend.requests[1] if m["role"] == "tool")
    assert "not granted" in json.loads(denied["content"])["error"]


def test_tool_errors_return_to_the_model_as_data():
    backend = ScriptedBackend(
        responder=lambda messages: _answer("recovered")
        if _tool_result_seen(messages)
        else _call("word_count", "{not json")
    )
    answer, trace = _run_agent(_spec(tools=["word_count"]), backend)

    assert answer == "recovered"
    assert "TOOL_ERROR" in trace.types()
    error_message = next(m for m in backend.requests[1] if m["role"] == "tool")
    assert "not valid JSON" in json.loads(error_message["content"])["error"]


def test_step_limit_stops_a_model_that_never_answers():
    backend = ScriptedBackend(responder=lambda messages: _call("word_count", '{"text": "x"}'))
    with pytest.raises(AgentError) as info:
        _run_agent(_spec(max_steps=2, tools=["word_count"]), backend)
    assert info.value.kind == "step_limit"
    assert len(backend.requests) == 2


def test_empty_reply_is_an_agent_error():
    backend = ScriptedBackend(responder=lambda messages: ChatResponse(content="   "))
    with pytest.raises(AgentError) as info:
        _run_agent(_spec(), backend)
    assert info.value.kind == "empty_reply"


def test_granting_an_unregistered_tool_is_a_configuration_error():
    with pytest.raises(ConfigError, match="not registered"):
        _run_agent(_spec(tools=["missing"]), ScriptedBackend())


def test_backend_failures_propagate_so_the_scheduler_can_decide():
    def failing(messages):
        raise BackendError("down", kind="unreachable", retryable=True)

    with pytest.raises(BackendError):
        _run_agent(_spec(), ScriptedBackend(responder=failing))


# --- tool registry ----------------------------------------------------------------------------------


def test_registry_rejects_bad_registrations():
    registry = ToolRegistry()
    registry.register("ok_tool", lambda: "x", description="fine")
    with pytest.raises(ConfigError):
        registry.register("bad name", lambda: "x", description="fine")
    with pytest.raises(ConfigError):
        registry.register("ok_tool", lambda: "x", description="again")
    with pytest.raises(ConfigError):
        registry.register("no_description", lambda: "x", description="   ")


@pytest.mark.parametrize(
    ("arguments", "fragment"),
    [("[1]", "JSON object"), ('{"wrong": 1}', "do not match"), ("nope", "not valid JSON")],
)
def test_invoke_validates_arguments(arguments, fragment):
    with pytest.raises(ToolError, match=fragment):
        asyncio.run(_registry().invoke("word_count", arguments, timeout_s=5))


def test_async_tools_run_and_slow_tools_time_out():
    async def add(a: int, b: int) -> dict:
        return {"sum": a + b}

    async def slow() -> str:
        await asyncio.sleep(5)
        return "late"

    registry = ToolRegistry()
    registry.register("add", add, description="Add two numbers.")
    registry.register("slow", slow, description="Slow.")

    assert json.loads(asyncio.run(registry.invoke("add", '{"a": 1, "b": 2}', timeout_s=5))) == {"sum": 3}
    with pytest.raises(ToolError, match="timed out"):
        asyncio.run(registry.invoke("slow", "{}", timeout_s=0.05))


def test_load_registry_accepts_the_example_and_rejects_bad_specs():
    assert "word_count" in load_registry("orchestration.examples.demo_tools:REGISTRY")
    with pytest.raises(ConfigError):
        load_registry("no_colon_here")
    with pytest.raises(ConfigError):
        load_registry("orchestration.tools:DOES_NOT_EXIST")
    with pytest.raises(ConfigError):
        load_registry("module_that_does_not_exist_anywhere:REGISTRY")


# --- workflow validation ----------------------------------------------------------------------------


def _doc(tasks, **top) -> dict:
    document = {"name": "wf", "agents": {"a": {"system": "sys", "max_steps": 2}}, "tasks": tasks}
    document.update(top)
    return document


def _task(task_id, input_text="go", **extra) -> dict:
    return {"id": task_id, "agent": "a", "input": input_text, **extra}


@pytest.mark.parametrize(
    ("document", "message"),
    [
        (_doc([_task("x", depends_on=["y"]), _task("y", depends_on=["x"])]), "cycle"),
        (_doc([_task("x", depends_on=["nope"])]), "unknown task"),
        (_doc([_task("x", depends_on=["x"])]), "depends on itself"),
        (_doc([_task("a"), _task("b", "uses {a}")]), "does not depend"),
        (_doc([_task("a"), _task("a")]), "duplicate"),
        (_doc([{"id": "a", "agent": "ghost", "input": "x"}]), "unknown agent"),
        (_doc([_task("1bad")]), "must start with a letter"),
        (_doc([_task("a")], surprise=True), "invalid workflow"),
    ],
)
def test_invalid_workflows_are_rejected_with_a_reason(document, message):
    with pytest.raises(WorkflowError, match=message):
        load_workflow(document)


def test_unregistered_tool_grants_are_rejected_when_tools_are_checked():
    document = _doc([_task("a")])
    document["agents"]["a"]["tools"] = ["ghost"]
    with pytest.raises(WorkflowError, match="unregistered tools: ghost"):
        load_workflow(document, tools=ToolRegistry())


def test_placeholders_are_single_pass_and_unknown_names_stay_literal():
    assert render_input("{a} and {zzz}", {"a": "X"}) == "X and {zzz}"
    assert render_input("{a}", {"a": "{a}"}) == "{a}"


# --- scheduler --------------------------------------------------------------------------------------

NO_WAIT = RetryPolicy(base_s=0.0, cap_s=0.0)


class _Gate:
    """A backend whose reply is decided by the text of the last user message."""

    name = "gate"

    def __init__(self, handler):
        self._handler = handler
        self.calls: list[str] = []

    async def chat(self, messages, *, tools=None, temperature=0.2, max_tokens=1024):
        text = messages[-1]["content"]
        self.calls.append(text)
        return await self._handler(text)


def _run(document, backend, *, retry=NO_WAIT, tools=None, trace=None):
    workflow = load_workflow(document)
    return asyncio.run(
        run_workflow(workflow, backend=backend, tools=tools or _registry(), trace=trace, retry=retry)
    )


def test_independent_tasks_run_concurrently():
    async def scenario():
        barrier = asyncio.Barrier(2)  # passes only when both tasks are in flight at once

        async def handler(text):
            await barrier.wait()
            return ChatResponse(content=f"done {text}")

        document = _doc([_task("a", "x", timeout_s=2), _task("b", "y", timeout_s=2)], max_parallel=2)
        return await run_workflow(
            load_workflow(document), backend=_Gate(handler), tools=_registry(), retry=NO_WAIT
        )

    assert asyncio.run(scenario()).status == "SUCCEEDED"


def test_max_parallel_bounds_in_flight_tasks():
    in_flight = 0
    peak = 0

    async def handler(text):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.02)
        in_flight -= 1
        return ChatResponse(content="ok")

    document = _doc([_task(f"t{i}", f"input {i}") for i in range(4)], max_parallel=1)
    assert _run(document, _Gate(handler)).status == "SUCCEEDED"
    assert peak == 1


def test_dependent_task_waits_and_receives_upstream_output():
    async def handler(text):
        return ChatResponse(content="alpha" if text == "start" else f"got<{text}>")

    trace = Trace()
    result = _run(
        _doc([_task("a", "start"), _task("b", "Use: {a}", depends_on=["a"])]),
        _Gate(handler),
        trace=trace,
    )
    assert result.outputs["b"] == "got<Use: alpha>"

    succeeded_a = next(e.seq for e in trace.events if e.type == "TASK_SUCCEEDED" and e.data["task"] == "a")
    started_b = next(e.seq for e in trace.events if e.type == "TASK_STARTED" and e.data["task"] == "b")
    assert succeeded_a < started_b


def test_retryable_failure_is_retried_within_budget():
    attempts: list[str] = []

    async def handler(text):
        attempts.append(text)
        if len(attempts) == 1:
            raise BackendError("slow", kind="timeout", retryable=True)
        return ChatResponse(content="ok")

    trace = Trace()
    result = _run(_doc([_task("a", retries=2)]), _Gate(handler), trace=trace)
    assert result.status == "SUCCEEDED"
    assert len(attempts) == 2
    assert "TASK_RETRY" in trace.types()


def test_non_retryable_failure_is_not_retried():
    attempts: list[str] = []

    async def handler(text):
        attempts.append(text)
        raise BackendError("SGLang rejected the API key", kind="auth_rejected", retryable=False)

    result = _run(_doc([_task("a", retries=3)]), _Gate(handler))
    assert result.states["a"] is TaskState.FAILED
    assert len(attempts) == 1
    assert "rejected the API key" in result.errors["a"]


def test_retry_budget_is_finite():
    attempts: list[str] = []

    async def handler(text):
        attempts.append(text)
        raise BackendError("slow", kind="timeout", retryable=True)

    result = _run(_doc([_task("a", retries=1)]), _Gate(handler))
    assert result.states["a"] is TaskState.FAILED
    assert len(attempts) == 2


def test_task_timeout_is_a_retryable_failure_with_a_clear_message():
    async def handler(text):
        await asyncio.sleep(5)
        return ChatResponse(content="late")

    result = _run(_doc([_task("a", timeout_s=0.05, retries=0)]), _Gate(handler))
    assert result.states["a"] is TaskState.FAILED
    assert "timed out" in result.errors["a"]


def test_fail_fast_cancels_running_siblings_and_unstarted_tasks():
    async def handler(text):
        if text == "boom":
            raise BackendError("bad request", kind="bad_request", retryable=False)
        if text == "slow":
            await asyncio.sleep(5)
        return ChatResponse(content="fine")

    document = _doc(
        [_task("a", "boom"), _task("b", "slow"), _task("c", "after {b}", depends_on=["b"])],
        failure_policy="fail_fast",
        max_parallel=2,
    )
    trace = Trace()
    result = _run(document, _Gate(handler), trace=trace)

    assert result.status == "FAILED"
    assert result.states == {"a": TaskState.FAILED, "b": TaskState.CANCELLED, "c": TaskState.CANCELLED}
    assert "TASK_CANCELLED" in trace.types()


def test_continue_policy_skips_only_dependents_of_the_failure():
    async def handler(text):
        if text == "boom":
            raise BackendError("bad request", kind="bad_request", retryable=False)
        return ChatResponse(content="fine")

    document = _doc(
        [_task("a", "boom"), _task("b", "after {a}", depends_on=["a"]), _task("c", "independent")],
        failure_policy="continue",
    )
    trace = Trace()
    result = _run(document, _Gate(handler), trace=trace)

    assert result.status == "PARTIAL"
    assert result.states == {"a": TaskState.FAILED, "b": TaskState.SKIPPED, "c": TaskState.SUCCEEDED}
    skip = next(e for e in trace.events if e.type == "TASK_SKIPPED")
    assert skip.data["reason"] == "dependency a is FAILED"


def test_secrets_are_redacted_from_the_trace():
    secret = "sk-live-abcdef123456"
    backend = ScriptedBackend(
        responder=lambda messages: _answer("done")
        if _tool_result_seen(messages)
        else _call("word_count", json.dumps({"text": f"key is {secret}"}))
    )
    trace = Trace(secrets=[secret])
    document = _doc([_task("a")])
    document["agents"]["a"]["tools"] = ["word_count"]
    result = _run(document, backend, trace=trace)

    assert result.status == "SUCCEEDED"
    dumped = trace.to_json()
    assert secret not in dumped
    assert REDACTED in dumped
