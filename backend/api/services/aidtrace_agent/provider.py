"""Anthropic Messages adapter for the AIDTRACE agent.

The only module that talks to Anthropic. The SDK is imported and the client built lazily, so with the
switch off, or no key set, nothing is imported past this file's top and no socket opens. Provider failures
are reduced to a fixed vocabulary of codes. Their messages are never passed on, so a provider error cannot
carry a credential or private source text into a response or a log.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, get_args

from api.config import Settings

READY = "ready"
DISABLED = "disabled"
NO_KEY = "no_api_key"
NO_SDK = "sdk_missing"
UNSUPPORTED_MODEL = "unsupported_model"
FALLBACK = "graph-only"


@dataclass(frozen=True)
class Readiness:
    state: str
    model: str
    reason: str

    @property
    def ready(self) -> bool:
        return self.state == READY

    def as_dict(self) -> dict[str, Any]:
        return {"state": self.state, "ready": self.ready, "model": self.model, "reason": self.reason, "fallback": FALLBACK}


def readiness(settings: Settings) -> Readiness:
    """Whether a model call may be made at all. Never includes the key itself."""
    model = settings.ANTHROPIC_MODEL
    if not settings.AIDTRACE_LLM_ENABLED:
        return Readiness(DISABLED, model, "Model reasoning is switched off. Questions answer from the graph engines.")
    if not settings.ANTHROPIC_API_KEY.strip():
        return Readiness(NO_KEY, model, "No Anthropic key is configured. Questions answer from the graph engines.")
    try:
        import anthropic  # noqa: F401
        from anthropic.types import Model
    except ImportError:
        return Readiness(NO_SDK, model, "The anthropic package is not installed. Run pip install -r requirements.txt.")
    model_ids = {
        value
        for item in get_args(Model)
        for value in (get_args(item) or (item,))
        if isinstance(value, str)
    }
    if model not in model_ids:
        return Readiness(UNSUPPORTED_MODEL, model, "The configured model ID is not present in the installed Anthropic SDK. No model request was made.")
    return Readiness(READY, model,
                    "The model ID is supported by the installed SDK. Account-level access is verified only by an explicit model request.")


class ProviderError(Exception):
    """A provider failure, reduced to a code that is safe to return to a user."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


MESSAGES = {
    "invalid_key": "The Anthropic key was refused.",
    "forbidden": "The Anthropic key is not allowed to use this model.",
    "rate_limited": "Anthropic is rate limiting requests. Try again shortly.",
    "timeout": "Anthropic did not answer within the time limit.",
    "unavailable": "Anthropic is unavailable right now.",
    "insufficient_credits": "The Anthropic account has no credit left for this request.",
    "bad_request": "Anthropic rejected the request.",
    "unexpected": "The model call failed.",
}


def classify(exc: BaseException) -> str:
    """Map an SDK or transport exception to a code. Reads the text only to recognise it, never to echo it."""
    if isinstance(exc, TimeoutError) or type(exc).__name__ == "APITimeoutError":
        return "timeout"
    if type(exc).__name__ == "APIConnectionError":
        return "unavailable"
    status = getattr(exc, "status_code", None)
    if status == 401:
        return "invalid_key"
    if status == 403:
        return "forbidden"
    if status == 429:
        return "rate_limited"
    if isinstance(status, int) and status >= 500:
        return "unavailable"
    if status == 400:
        return "insufficient_credits" if "credit" in str(exc).lower() else "bad_request"
    return "unexpected"


@dataclass
class Usage:
    """Token counts summed over one investigation. Shown to operators only."""

    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    def add(self, input_tokens: int, output_tokens: int) -> None:
        self.requests += 1
        self.input_tokens += int(input_tokens or 0)
        self.output_tokens += int(output_tokens or 0)

    def estimated_cost_usd(self, settings: Settings) -> float | None:
        """Estimate from the configured price sheet. None until a price is set, so an unpriced build never shows an invented figure."""
        if not (settings.AIDTRACE_LLM_PRICE_INPUT_PER_MTOK or settings.AIDTRACE_LLM_PRICE_OUTPUT_PER_MTOK):
            return None
        cost = self.input_tokens * settings.AIDTRACE_LLM_PRICE_INPUT_PER_MTOK + self.output_tokens * settings.AIDTRACE_LLM_PRICE_OUTPUT_PER_MTOK
        return round(cost / 1_000_000, 6)

    def as_dict(self, settings: Settings) -> dict[str, Any]:
        return {"requests": self.requests, "input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
                "estimated_cost_usd": self.estimated_cost_usd(settings)}


class ClaudeMessages:
    """One Messages API call with the configured model, output cap and timeout. Retries are the SDK's own, capped at two."""

    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        self._settings = settings
        self._client = client

    def _sdk(self) -> Any:
        if self._client is None:
            import anthropic

            self._client = anthropic.AsyncAnthropic(
                api_key=self._settings.ANTHROPIC_API_KEY,
                timeout=self._settings.AIDTRACE_LLM_REQUEST_TIMEOUT_SECONDS,
                max_retries=2,
            )
        return self._client

    async def create(self, *, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Any:
        s = self._settings
        try:
            return await asyncio.wait_for(
                self._sdk().messages.create(
                    model=s.ANTHROPIC_MODEL,
                    max_tokens=s.AIDTRACE_LLM_MAX_OUTPUT_TOKENS,
                    system=system,
                    messages=messages,
                    tools=tools,
                ),
                timeout=s.AIDTRACE_LLM_REQUEST_TIMEOUT_SECONDS,
            )
        except TimeoutError as exc:
            raise ProviderError("timeout") from exc
        except Exception as exc:  # noqa: BLE001 - every provider failure becomes one of the fixed codes
            raise ProviderError(classify(exc)) from exc
