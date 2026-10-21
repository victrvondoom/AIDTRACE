"""Run a validated workflow.

Independent tasks run in parallel, up to ``max_parallel``. A task starts only after its dependencies
succeeded. Only failures the backend marks retryable are retried, within the task's retry budget.
On failure the run either stops (``fail_fast``) or skips only the tasks that depended on it
(``continue``).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .agents import run_agent
from .backends import ChatBackend
from .errors import BackendError, OrchestrationError
from .tools import ToolRegistry
from .trace import Trace
from .workflow import TaskSpec, Workflow, render_input, validate_workflow


class TaskState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"


_BLOCKING = frozenset({TaskState.FAILED, TaskState.SKIPPED, TaskState.CANCELLED})


@dataclass(frozen=True)
class RetryPolicy:
    """Exponential backoff: ``base_s * 2**(attempt - 1)``, capped at ``cap_s``."""

    base_s: float = 0.5
    cap_s: float = 8.0


@dataclass
class RunResult:
    workflow: str
    status: str  # SUCCEEDED: every task succeeded. PARTIAL: some did. FAILED: none did.
    states: dict[str, TaskState]
    outputs: dict[str, str]
    errors: dict[str, str]
    trace: Trace

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow": self.workflow,
            "status": self.status,
            "tasks": {
                task_id: {
                    "state": state.value,
                    "output": self.outputs.get(task_id),
                    "error": self.errors.get(task_id),
                }
                for task_id, state in self.states.items()
            },
        }


class _TaskFailure(Exception):
    """A task reached a terminal failure. The message is shown to the user."""


async def run_workflow(
    workflow: Workflow,
    *,
    backend: ChatBackend,
    tools: ToolRegistry | None = None,
    trace: Trace | None = None,
    retry: RetryPolicy | None = None,
    sleep: Callable[[float], Awaitable[object]] = asyncio.sleep,
) -> RunResult:
    registry = tools if tools is not None else ToolRegistry()
    validate_workflow(workflow, registry)
    trace = trace if trace is not None else Trace()
    policy = retry if retry is not None else RetryPolicy()

    tasks = {task.id: task for task in workflow.tasks}
    order = [task.id for task in workflow.tasks]
    states = {task_id: TaskState.PENDING for task_id in order}
    outputs: dict[str, str] = {}
    errors: dict[str, str] = {}
    running: dict[str, asyncio.Task[str]] = {}

    trace.record(
        "RUN_STARTED",
        workflow=workflow.name,
        task_count=len(order),
        failure_policy=workflow.failure_policy,
        max_parallel=workflow.max_parallel,
    )
    try:
        while True:
            _skip_blocked(order, tasks, states, trace)
            for task_id in order:
                if len(running) >= workflow.max_parallel:
                    break
                task = tasks[task_id]
                ready = states[task_id] is TaskState.PENDING and all(
                    states[dep] is TaskState.SUCCEEDED for dep in task.depends_on
                )
                if not ready:
                    continue
                states[task_id] = TaskState.RUNNING
                trace.record("TASK_STARTED", task=task_id, agent=task.agent, depends_on=list(task.depends_on))
                running[task_id] = asyncio.create_task(
                    _run_task(
                        task,
                        workflow=workflow,
                        backend=backend,
                        tools=registry,
                        trace=trace,
                        outputs=dict(outputs),
                        retry=policy,
                        sleep=sleep,
                    )
                )
            if not running:
                break

            await asyncio.wait(list(running.values()), return_when=asyncio.FIRST_COMPLETED)
            halt = False
            for task_id in [tid for tid, job in running.items() if job.done()]:
                job = running.pop(task_id)
                try:
                    outputs[task_id] = job.result()
                except _TaskFailure as exc:
                    states[task_id] = TaskState.FAILED
                    errors[task_id] = str(exc)
                    trace.record("TASK_FAILED", task=task_id, error=str(exc))
                    halt = halt or workflow.failure_policy == "fail_fast"
                else:
                    states[task_id] = TaskState.SUCCEEDED
                    trace.record("TASK_SUCCEEDED", task=task_id, output_chars=len(outputs[task_id]))
            if halt:
                await _cancel_running(running, states, trace)
                _cancel_pending(order, states, trace, reason="run stopped after a failure")
                break
    finally:
        if running:  # interrupted from outside, for example Ctrl-C: do not leave work behind
            await _cancel_running(running, states, trace)

    _cancel_pending(order, states, trace, reason="could not be scheduled")
    status = _overall_status(states)
    trace.record("RUN_COMPLETED", status=status, states={tid: state.value for tid, state in states.items()})
    return RunResult(
        workflow=workflow.name,
        status=status,
        states=states,
        outputs=outputs,
        errors=errors,
        trace=trace,
    )


async def _run_task(
    task: TaskSpec,
    *,
    workflow: Workflow,
    backend: ChatBackend,
    tools: ToolRegistry,
    trace: Trace,
    outputs: dict[str, str],
    retry: RetryPolicy,
    sleep: Callable[[float], Awaitable[object]],
) -> str:
    agent = workflow.agents[task.agent]
    prompt = render_input(task.input, outputs)
    attempt = 0
    while True:
        attempt += 1
        trace.record("ATTEMPT_STARTED", task=task.id, attempt=attempt)
        try:
            return await asyncio.wait_for(
                run_agent(
                    agent,
                    backend=backend,
                    tools=tools,
                    user_input=prompt,
                    trace=trace,
                    task_id=task.id,
                    attempt=attempt,
                ),
                timeout=task.timeout_s,
            )
        except TimeoutError:
            failure = BackendError(f"task timed out after {task.timeout_s:g}s", kind="task_timeout", retryable=True)
        except BackendError as exc:
            failure = exc
        except OrchestrationError as exc:
            raise _TaskFailure(str(exc)) from exc
        except Exception as exc:  # a bug in a backend or wrapper: report it, do not retry it
            raise _TaskFailure(f"{type(exc).__name__}: {exc}") from exc

        if not failure.retryable or attempt > task.retries:
            raise _TaskFailure(str(failure))
        delay = min(retry.cap_s, retry.base_s * (2 ** (attempt - 1)))
        trace.record(
            "TASK_RETRY",
            task=task.id,
            attempt=attempt,
            kind=failure.kind,
            delay_s=delay,
            error=str(failure),
        )
        await sleep(delay)


def _skip_blocked(
    order: list[str],
    tasks: dict[str, TaskSpec],
    states: dict[str, TaskState],
    trace: Trace,
) -> None:
    changed = True
    while changed:  # repeat so a skip propagates down a chain in one call
        changed = False
        for task_id in order:
            if states[task_id] is not TaskState.PENDING:
                continue
            blocker = next((dep for dep in tasks[task_id].depends_on if states[dep] in _BLOCKING), None)
            if blocker is not None:
                states[task_id] = TaskState.SKIPPED
                trace.record("TASK_SKIPPED", task=task_id, reason=f"dependency {blocker} is {states[blocker].value}")
                changed = True


async def _cancel_running(
    running: dict[str, asyncio.Task[str]],
    states: dict[str, TaskState],
    trace: Trace,
) -> None:
    jobs = dict(running)
    running.clear()
    for job in jobs.values():
        job.cancel()
    await asyncio.gather(*jobs.values(), return_exceptions=True)
    for task_id in jobs:
        states[task_id] = TaskState.CANCELLED
        trace.record("TASK_CANCELLED", task=task_id, reason="run stopped")


def _cancel_pending(order: list[str], states: dict[str, TaskState], trace: Trace, *, reason: str) -> None:
    for task_id in order:
        if states[task_id] is TaskState.PENDING:
            states[task_id] = TaskState.CANCELLED
            trace.record("TASK_CANCELLED", task=task_id, reason=reason)


def _overall_status(states: dict[str, TaskState]) -> str:
    values = list(states.values())
    if all(value is TaskState.SUCCEEDED for value in values):
        return "SUCCEEDED"
    if any(value is TaskState.SUCCEEDED for value in values):
        return "PARTIAL"
    return "FAILED"
