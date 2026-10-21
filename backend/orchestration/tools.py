"""Tools agents may call. An agent sees and can invoke only the tools its spec grants."""

from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from .errors import ConfigError, ToolError

MAX_RESULT_CHARS = 8000
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


@dataclass(frozen=True)
class Tool:
    name: str
    fn: Callable[..., Any]
    description: str
    parameters: dict[str, Any]


class ToolRegistry:
    """Named tools with JSON-schema parameters. Sync and async functions are both accepted.

    Sync functions run in a worker thread, so a timeout stops waiting for them but cannot kill them.
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(
        self,
        name: str,
        fn: Callable[..., Any],
        *,
        description: str,
        parameters: dict[str, Any] | None = None,
    ) -> None:
        if not _NAME.match(name):
            raise ConfigError(f"tool name {name!r} must be an identifier of at most 64 characters")
        if name in self._tools:
            raise ConfigError(f"tool {name!r} is already registered")
        if not description.strip():
            raise ConfigError(f"tool {name!r} needs a description; the model relies on it")
        if not callable(fn):
            raise ConfigError(f"tool {name!r} must be callable")
        schema = parameters or {"type": "object", "properties": {}}
        self._tools[name] = Tool(name=name, fn=fn, description=description.strip(), parameters=schema)

    def __contains__(self, name: object) -> bool:
        return name in self._tools

    def names(self) -> list[str]:
        return sorted(self._tools)

    def schemas(self, names: Iterable[str]) -> list[dict[str, Any]]:
        """OpenAI-style ``tools`` entries for the named tools. Unknown names are a configuration error."""
        result = []
        for name in names:
            tool = self._tools.get(name)
            if tool is None:
                raise ConfigError(f"agent is granted tool {name!r}, which is not registered")
            result.append(
                {
                    "type": "function",
                    "function": {"name": tool.name, "description": tool.description, "parameters": tool.parameters},
                }
            )
        return result

    async def invoke(self, name: str, arguments: str, *, timeout_s: float) -> str:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolError(f"unknown tool {name!r}")
        try:
            kwargs = json.loads(arguments or "{}")
        except json.JSONDecodeError as exc:
            raise ToolError(f"arguments for {name!r} are not valid JSON") from exc
        if not isinstance(kwargs, dict):
            raise ToolError(f"arguments for {name!r} must be a JSON object")
        try:
            inspect.signature(tool.fn).bind(**kwargs)
        except TypeError as exc:
            raise ToolError(f"arguments do not match tool {name!r}: {exc}") from exc

        try:
            if inspect.iscoroutinefunction(tool.fn):
                value = await asyncio.wait_for(tool.fn(**kwargs), timeout_s)
            else:
                value = await asyncio.wait_for(asyncio.to_thread(tool.fn, **kwargs), timeout_s)
        except TimeoutError as exc:
            raise ToolError(f"tool {name!r} timed out after {timeout_s}s") from exc
        except Exception as exc:
            raise ToolError(f"tool {name!r} failed: {type(exc).__name__}: {exc}") from exc

        text = value if isinstance(value, str) else json.dumps(value, default=str)
        return text[:MAX_RESULT_CHARS]


def load_registry(spec: str) -> ToolRegistry:
    """Load a ToolRegistry from ``package.module:attribute``."""
    module_name, sep, attribute = spec.partition(":")
    if not sep or not module_name or not attribute:
        raise ConfigError("tools must be given as module:attribute, e.g. myproject.tools:REGISTRY")
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise ConfigError(f"cannot import tools module {module_name!r}: {exc}") from exc
    registry = getattr(module, attribute, None)
    if not isinstance(registry, ToolRegistry):
        raise ConfigError(f"{spec} is not a ToolRegistry instance")
    return registry
