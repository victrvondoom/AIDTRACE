"""SGLang backend protocol handling, configuration validation, and the scripted backend.

The SGLang server is replaced by httpx.MockTransport, so every status code and malformed payload is
exercised deterministically. Real-socket coverage lives in test_orchestration_http.py.
"""

import asyncio
import json

import httpx
import pytest

from orchestration.backends import ChatResponse, ScriptedBackend, SGLangBackend
from orchestration.config import Settings, validate_base_url
from orchestration.errors import BackendError, ConfigError

BASE = "http://sglang.test:30000"
KEY = "sk-test-key-123456"


def _backend(handler, *, api_key=None, model="demo-model") -> SGLangBackend:
    return SGLangBackend(base_url=BASE, model=model, api_key=api_key, transport=httpx.MockTransport(handler))


def _completion(content="hello", tool_calls=None) -> httpx.Response:
    message = {"role": "assistant", "content": content}
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    body = {
        "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls" if tool_calls else "stop"}],
        "usage": {"prompt_tokens": 7, "completion_tokens": 3},
    }
    return httpx.Response(200, json=body)


def _chat(backend: SGLangBackend, **kwargs) -> ChatResponse:
    async def go() -> ChatResponse:
        async with backend:
            return await backend.chat([{"role": "user", "content": "hi"}], **kwargs)

    return asyncio.run(go())


def test_success_returns_text_and_usage():
    backend = _backend(lambda request: _completion("hello"))
    response = _chat(backend)
    assert response.content == "hello"
    assert response.finish_reason == "stop"
    assert (response.prompt_tokens, response.completion_tokens) == (7, 3)
    assert response.latency_ms >= 0


def test_request_carries_model_auth_and_tools():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _completion("ok")

    tools = [{"type": "function", "function": {"name": "t", "description": "d", "parameters": {"type": "object"}}}]
    _chat(_backend(handler, api_key=KEY), tools=tools, temperature=0.0, max_tokens=16)

    request = seen[0]
    body = json.loads(request.content)
    assert request.url.path == "/v1/chat/completions"
    assert request.headers["Authorization"] == f"Bearer {KEY}"
    assert body["model"] == "demo-model"
    assert body["stream"] is False
    assert body["tools"] == tools
    assert body["tool_choice"] == "auto"
    assert body["max_tokens"] == 16


def test_tool_calls_are_parsed_and_dict_arguments_are_serialised():
    tool_calls = [
        {"id": "call_1", "type": "function", "function": {"name": "word_count", "arguments": '{"text": "a"}'}},
        {"id": "call_2", "type": "function", "function": {"name": "word_count", "arguments": {"text": "b"}}},
    ]
    response = _chat(_backend(lambda request: _completion(None, tool_calls=tool_calls)))
    assert response.content is None
    assert [call.id for call in response.tool_calls] == ["call_1", "call_2"]
    assert response.tool_calls[0].arguments == '{"text": "a"}'
    assert json.loads(response.tool_calls[1].arguments) == {"text": "b"}


@pytest.mark.parametrize(
    ("status", "kind", "retryable"),
    [
        (401, "auth_rejected", False),
        (403, "auth_rejected", False),
        (400, "bad_request", False),
        (429, "rate_limited", True),
        (500, "server_error", True),
        (503, "server_error", True),
    ],
)
def test_status_codes_map_to_failure_kinds(status, kind, retryable):
    backend = _backend(lambda request: httpx.Response(status, text="nope"))
    with pytest.raises(BackendError) as info:
        _chat(backend)
    assert info.value.kind == kind
    assert info.value.retryable is retryable


def test_transport_failures_are_retryable():
    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("no bytes", request=request)

    with pytest.raises(BackendError) as unreachable:
        _chat(_backend(refused))
    assert (unreachable.value.kind, unreachable.value.retryable) == ("unreachable", True)

    with pytest.raises(BackendError) as timed_out:
        _chat(_backend(slow))
    assert (timed_out.value.kind, timed_out.value.retryable) == ("timeout", True)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="<html>not json</html>"),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, json={"choices": [{"message": "a string, not an object"}]}),
        httpx.Response(200, json={"choices": [{"message": {"content": 42}}]}),
        httpx.Response(
            200,
            json={"choices": [{"message": {"content": None, "tool_calls": [{"function": {"arguments": "{}"}}]}}]},
        ),
    ],
)
def test_malformed_payloads_are_protocol_errors(response):
    with pytest.raises(BackendError) as info:
        _chat(_backend(lambda request: response))
    assert info.value.kind == "protocol_error"
    assert info.value.retryable is False


@pytest.mark.parametrize(
    "url",
    ["ftp://host:30000", "http://user:pw@host:30000", "http://host:30000/?x=1", "http:///no-host", "http://host:99999"],
)
def test_base_url_must_be_plain_http_without_credentials(url):
    with pytest.raises(ConfigError):
        validate_base_url(url)


def test_base_url_trailing_slash_is_normalised():
    assert validate_base_url("http://127.0.0.1:30000/") == "http://127.0.0.1:30000"


def test_model_name_is_required():
    with pytest.raises(ConfigError, match="model"):
        SGLangBackend(base_url=BASE, model="")


def test_settings_read_the_environment_and_hide_the_key_in_repr():
    settings = Settings.from_env(
        {"SGLANG_API_KEY": "sk-secret-value-000", "SGLANG_MODEL": "m", "ORCH_MAX_CONCURRENCY": "4"}
    )
    assert settings.sglang_api_key == "sk-secret-value-000"
    assert settings.max_concurrency == 4
    text = repr(settings)
    assert "sk-secret-value-000" not in text
    assert "<set>" in text


@pytest.mark.parametrize(
    "environ",
    [{"ORCH_REQUEST_TIMEOUT_S": "soon"}, {"ORCH_MAX_CONCURRENCY": "0"}, {"SGLANG_BASE_URL": "ftp://x"}],
)
def test_settings_reject_invalid_values(environ):
    with pytest.raises(ConfigError):
        Settings.from_env(environ)


def test_scripted_backend_echoes_and_can_be_scripted():
    echoed = asyncio.run(ScriptedBackend().chat([{"role": "user", "content": "ping"}]))
    assert echoed.content.startswith("[scripted dry run, no model]")
    assert "ping" in echoed.content

    scripted = ScriptedBackend(responder=lambda messages: "fixed")
    assert asyncio.run(scripted.chat([{"role": "user", "content": "x"}])).content == "fixed"
