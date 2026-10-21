"""Provider-neutral orchestration for LLM agents, with an SGLang backend.

Workflows are DAGs of agent tasks. Each agent calls a chat backend, and may call only the tools it is
granted. Every decision is recorded in a redacted trace. See README.md for the workflow format,
the CLI, and the limits.
"""

from .agents import AgentSpec, run_agent
from .backends import ChatBackend, ChatResponse, SGLangBackend, ScriptedBackend, ToolCall
from .config import Settings, validate_base_url
from .doctor import DoctorReport, Health, probe
from .errors import (
    AgentError,
    BackendError,
    ConfigError,
    OrchestrationError,
    ToolError,
    WorkflowError,
)
from .scheduler import RetryPolicy, RunResult, TaskState, run_workflow
from .tools import Tool, ToolRegistry, load_registry
from .trace import Event, Trace
from .workflow import TaskSpec, Workflow, load_workflow, render_input, validate_workflow

__all__ = [
    "AgentError",
    "AgentSpec",
    "BackendError",
    "ChatBackend",
    "ChatResponse",
    "ConfigError",
    "DoctorReport",
    "Event",
    "Health",
    "OrchestrationError",
    "RetryPolicy",
    "RunResult",
    "SGLangBackend",
    "ScriptedBackend",
    "Settings",
    "TaskSpec",
    "TaskState",
    "Tool",
    "ToolCall",
    "ToolError",
    "ToolRegistry",
    "Trace",
    "Workflow",
    "WorkflowError",
    "load_registry",
    "load_workflow",
    "probe",
    "render_input",
    "run_agent",
    "run_workflow",
    "validate_base_url",
    "validate_workflow",
]
