"""Exception types shared by the orchestration package."""


class OrchestrationError(Exception):
    """Base class for errors that are reported to the user."""


class ConfigError(OrchestrationError):
    """Settings, CLI options, or tool registration are missing or invalid."""


class WorkflowError(OrchestrationError):
    """A workflow document is malformed or internally inconsistent."""


class ToolError(OrchestrationError):
    """A tool could not be invoked, or raised while running."""


class AgentError(OrchestrationError):
    """An agent could not reach a final answer (step limit, empty reply, bad protocol)."""

    def __init__(self, message: str, *, kind: str) -> None:
        super().__init__(message)
        self.kind = kind


class BackendError(OrchestrationError):
    """A chat backend call failed.

    ``retryable`` says whether repeating the same call may succeed: timeouts, unreachable servers,
    rate limits and 5xx responses are retryable; authentication and request errors are not.
    """

    def __init__(self, message: str, *, kind: str, retryable: bool) -> None:
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable
