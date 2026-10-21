"""Preflight checks for an SGLang server. Every status describes what was observed, not what is hoped."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import httpx

from .backends import SGLangBackend
from .config import validate_base_url
from .errors import BackendError


class Health(str, Enum):
    OK = "OK"
    MODEL_NOT_LISTED = "MODEL_NOT_LISTED"
    AUTH_REJECTED = "AUTH_REJECTED"
    UNREACHABLE = "UNREACHABLE"
    TIMEOUT = "TIMEOUT"
    PROTOCOL_ERROR = "PROTOCOL_ERROR"


@dataclass(frozen=True)
class DoctorReport:
    base_url: str
    status: Health
    detail: str
    models: tuple[str, ...] = ()
    requested_model: str | None = None
    generation: str | None = None  # None unless --ping was used: "OK", "FAILED (<kind>)" or "SKIPPED (...)"


async def probe(
    base_url: str,
    *,
    api_key: str | None = None,
    model: str | None = None,
    ping: bool = False,
    timeout_s: float = 10.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> DoctorReport:
    """Check GET /v1/models. With ``ping``, also run one 4-token completion."""
    base = validate_base_url(base_url)
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        async with httpx.AsyncClient(base_url=base, headers=headers, timeout=timeout_s, transport=transport) as client:
            response = await client.get("/v1/models")
    except httpx.TimeoutException:
        return DoctorReport(base, Health.TIMEOUT, f"no answer from {base} within {timeout_s:g}s", requested_model=model)
    except httpx.HTTPError as exc:
        return DoctorReport(
            base, Health.UNREACHABLE, f"cannot connect to {base} ({type(exc).__name__})", requested_model=model
        )

    if response.status_code in (401, 403):
        return DoctorReport(
            base,
            Health.AUTH_REJECTED,
            f"server rejected the API key (HTTP {response.status_code})",
            requested_model=model,
        )
    if response.status_code != 200:
        return DoctorReport(
            base, Health.PROTOCOL_ERROR, f"GET /v1/models returned HTTP {response.status_code}", requested_model=model
        )
    try:
        models = tuple(str(item["id"]) for item in response.json()["data"])
    except (ValueError, KeyError, TypeError):
        return DoctorReport(
            base, Health.PROTOCOL_ERROR, "GET /v1/models did not return the OpenAI model list", requested_model=model
        )

    if model is not None and model not in models:
        served = ", ".join(models) or "nothing"
        return DoctorReport(
            base,
            Health.MODEL_NOT_LISTED,
            f"server answers but does not list {model!r}; it serves: {served}",
            models=models,
            requested_model=model,
        )

    generation = await _ping(base, api_key, model, timeout_s, transport) if ping else None
    detail = (
        f"server answers and lists {model!r}"
        if model is not None
        else f"server answers and serves {len(models)} model(s); pass --model to check one"
    )
    return DoctorReport(base, Health.OK, detail, models=models, requested_model=model, generation=generation)


async def _ping(
    base: str,
    api_key: str | None,
    model: str | None,
    timeout_s: float,
    transport: httpx.AsyncBaseTransport | None,
) -> str:
    if model is None:
        return "SKIPPED (no model given)"
    async with SGLangBackend(
        base_url=base, model=model, api_key=api_key, timeout_s=timeout_s, transport=transport
    ) as backend:
        try:
            reply = await backend.chat(
                [{"role": "user", "content": "Reply with the word ok."}], temperature=0.0, max_tokens=4
            )
        except BackendError as exc:
            return f"FAILED ({exc.kind})"
    return "OK" if reply.content else "FAILED (empty_reply)"
