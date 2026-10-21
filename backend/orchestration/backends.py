"""Chat backends: turn OpenAI-style messages into one model reply.

``SGLangBackend`` calls SGLang's OpenAI-compatible ``/v1/chat/completions`` endpoint. Retries are not
done here: the scheduler owns retry policy, so every attempt appears in the trace.

``ScriptedBackend`` is deterministic and offline. It exists for dry runs and tests, and its output
says it is not a model.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from .config import validate_base_url
from .errors import BackendError, ConfigError


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str  # JSON text, exactly as the model produced it


@dataclass(frozen=True)
class ChatResponse:
    content: str | None
    tool_calls: tuple[ToolCall, ...] = ()
    finish_reason: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: float = 0.0


class ChatBackend(Protocol):
    """Anything that can answer a chat request. Implement this to add a provider."""

    name: str

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> ChatResponse: ...


class SGLangBackend:
    """Client for an SGLang server started with its OpenAI-compatible API (the default)."""

    name = "sglang"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout_s: float = 60.0,
        max_concurrency: int = 8,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not model:
            raise ConfigError("an SGLang model name is required (--model or SGLANG_MODEL)")
        self.base_url = validate_base_url(base_url)
        self.model = model
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.AsyncClient(
            base_url=self.base_url, headers=headers, timeout=timeout_s, transport=transport
        )
        self._slots = asyncio.Semaphore(max_concurrency)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> SGLangBackend:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> ChatResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        started = time.perf_counter()
        async with self._slots:
            try:
                response = await self._client.post("/v1/chat/completions", json=payload)
            except httpx.TimeoutException as exc:
                raise BackendError("SGLang request timed out", kind="timeout", retryable=True) from exc
            except httpx.HTTPError as exc:
                raise BackendError(
                    f"SGLang server unreachable ({type(exc).__name__})", kind="unreachable", retryable=True
                ) from exc
        latency_ms = (time.perf_counter() - started) * 1000
        _raise_for_status(response)
        return _parse_completion(response, latency_ms)


def _raise_for_status(response: httpx.Response) -> None:
    code = response.status_code
    if code < 400:
        return
    if code in (401, 403):
        raise BackendError(f"SGLang rejected the API key (HTTP {code})", kind="auth_rejected", retryable=False)
    if code == 429:
        raise BackendError("SGLang rate-limited the request (HTTP 429)", kind="rate_limited", retryable=True)
    if code >= 500:
        raise BackendError(f"SGLang server error (HTTP {code})", kind="server_error", retryable=True)
    raise BackendError(
        f"SGLang rejected the request (HTTP {code}): {response.text[:200]}", kind="bad_request", retryable=False
    )


def _protocol_error(detail: str) -> BackendError:
    return BackendError(f"unexpected SGLang response: {detail}", kind="protocol_error", retryable=False)


def _parse_completion(response: httpx.Response, latency_ms: float) -> ChatResponse:
    try:
        body = response.json()
    except ValueError as exc:
        raise _protocol_error("body is not JSON") from exc
    if not isinstance(body, dict) or not isinstance(body.get("choices"), list) or not body["choices"]:
        raise _protocol_error("no choices")
    choice = body["choices"][0]
    message = choice.get("message") if isinstance(choice, dict) else None
    if not isinstance(message, dict):
        raise _protocol_error("first choice has no message")

    content = message.get("content")
    if content is not None and not isinstance(content, str):
        raise _protocol_error("message content is not text")

    calls: list[ToolCall] = []
    for raw in message.get("tool_calls") or []:
        function = raw.get("function") if isinstance(raw, dict) else None
        if not isinstance(function, dict) or not isinstance(function.get("name"), str) or not function["name"]:
            raise _protocol_error("tool call without a function name")
        arguments = function.get("arguments", "{}")
        if not isinstance(arguments, str):
            arguments = json.dumps(arguments)
        call_id = str(raw.get("id") or f"call_{len(calls)}")
        calls.append(ToolCall(id=call_id, name=function["name"], arguments=arguments))

    usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    return ChatResponse(
        content=content,
        tool_calls=tuple(calls),
        finish_reason=choice.get("finish_reason"),
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
        latency_ms=round(latency_ms, 1),
    )


Responder = Callable[[list[dict[str, Any]]], "ChatResponse | str"]


class ScriptedBackend:
    """Deterministic backend for dry runs and tests. It is not a model, and its output says so."""

    name = "scripted"

    def __init__(self, responder: Responder | None = None) -> None:
        self._responder = responder
        self.requests: list[list[dict[str, Any]]] = []

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> ChatResponse:
        self.requests.append([dict(message) for message in messages])
        if self._responder is None:
            last_user = next(
                (str(m.get("content", "")) for m in reversed(messages) if m.get("role") == "user"), ""
            )
            return ChatResponse(content=f"[scripted dry run, no model] {last_user[:2000]}")
        result = self._responder(messages)
        return ChatResponse(content=result) if isinstance(result, str) else result
