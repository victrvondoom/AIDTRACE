"""Workflow documents: agents, tasks, dependencies, and validation.

A workflow is JSON. Tasks form a directed acyclic graph. A task may insert an upstream task's output
with ``{task_id}``, but only if it depends on that task.
"""

from __future__ import annotations

import json
import re
from collections import deque
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .agents import AgentSpec
from .errors import WorkflowError
from .tools import ToolRegistry

MAX_WORKFLOW_BYTES = 1_000_000
_TASK_ID = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,63}$")
_PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_-]{0,63})\}")


class TaskSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    agent: str
    input: str = Field(min_length=1, max_length=20000)
    depends_on: list[str] = Field(default_factory=list, max_length=50)
    retries: int = Field(default=0, ge=0, le=5)
    timeout_s: float = Field(default=120.0, gt=0, le=3600)


class Workflow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    agents: dict[str, AgentSpec]
    tasks: list[TaskSpec] = Field(min_length=1, max_length=200)
    failure_policy: Literal["fail_fast", "continue"] = "fail_fast"
    max_parallel: int = Field(default=4, ge=1, le=64)


def validate_workflow(workflow: Workflow, tools: ToolRegistry | None = None) -> None:
    """Check what the schema cannot: ids, references, acyclicity, placeholders, and tool grants."""
    if not workflow.agents:
        raise WorkflowError("workflow defines no agents")
    ids = [task.id for task in workflow.tasks]
    for task_id in ids:
        if not _TASK_ID.match(task_id):
            raise WorkflowError(
                f"task id {task_id!r} must start with a letter or underscore and use only letters, digits, '-' or '_'"
            )
    duplicates = sorted({task_id for task_id in ids if ids.count(task_id) > 1})
    if duplicates:
        raise WorkflowError(f"duplicate task ids: {', '.join(duplicates)}")

    known = set(ids)
    for task in workflow.tasks:
        if task.agent not in workflow.agents:
            raise WorkflowError(f"task {task.id!r} uses unknown agent {task.agent!r}")
        for dep in task.depends_on:
            if dep == task.id:
                raise WorkflowError(f"task {task.id!r} depends on itself")
            if dep not in known:
                raise WorkflowError(f"task {task.id!r} depends on unknown task {dep!r}")
        for ref in sorted(set(_PLACEHOLDER.findall(task.input))):
            if ref in known and ref not in task.depends_on:
                raise WorkflowError(f"task {task.id!r} uses {{{ref}}} but does not depend on {ref!r}")
    _check_acyclic(workflow)

    if tools is not None:
        for name, agent in workflow.agents.items():
            missing = [tool for tool in agent.tools if tool not in tools]
            if missing:
                raise WorkflowError(f"agent {name!r} is granted unregistered tools: {', '.join(missing)}")


def _check_acyclic(workflow: Workflow) -> None:
    """Kahn's algorithm: any task left with unresolved dependencies sits on or behind a cycle."""
    pending = {task.id: len(set(task.depends_on)) for task in workflow.tasks}
    dependents: dict[str, list[str]] = {task.id: [] for task in workflow.tasks}
    for task in workflow.tasks:
        for dep in set(task.depends_on):
            dependents[dep].append(task.id)

    ready = deque(sorted(task_id for task_id, count in pending.items() if count == 0))
    resolved = 0
    while ready:
        node = ready.popleft()
        resolved += 1
        for child in dependents[node]:
            pending[child] -= 1
            if pending[child] == 0:
                ready.append(child)
    if resolved != len(pending):
        cyclic = sorted(task_id for task_id, count in pending.items() if count > 0)
        raise WorkflowError(f"dependency cycle involving: {', '.join(cyclic)}")


def load_workflow(source: str | Path | dict[str, Any], tools: ToolRegistry | None = None) -> Workflow:
    """Parse and validate a workflow from a JSON file or an already-decoded dict."""
    if isinstance(source, dict):
        data: Any = source
    else:
        path = Path(source)
        try:
            if path.stat().st_size > MAX_WORKFLOW_BYTES:
                raise WorkflowError(f"{path} is larger than {MAX_WORKFLOW_BYTES} bytes")
            data = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise WorkflowError(f"cannot read {path}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise WorkflowError(
                f"{path} is not valid JSON (line {exc.lineno}, column {exc.colno}): {exc.msg}"
            ) from exc
    try:
        workflow = Workflow.model_validate(data)
    except ValidationError as exc:
        raise WorkflowError(_summarize(exc)) from exc
    validate_workflow(workflow, tools)
    return workflow


def render_input(template: str, outputs: dict[str, str]) -> str:
    """Replace ``{task_id}`` with that task's output in one pass. Unknown names stay as written."""
    return _PLACEHOLDER.sub(lambda match: outputs.get(match.group(1), match.group(0)), template)


def _summarize(error: ValidationError) -> str:
    parts = []
    for item in error.errors()[:5]:
        location = ".".join(str(part) for part in item["loc"]) or "workflow"
        parts.append(f"{location}: {item['msg']}")
    return "invalid workflow: " + "; ".join(parts)
