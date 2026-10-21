"""Runtime settings read from the environment, validated before any network call."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

from .errors import ConfigError

DEFAULT_BASE_URL = "http://127.0.0.1:30000"  # SGLang's default serving port


def validate_base_url(url: str) -> str:
    """Return ``url`` without a trailing slash, or raise ConfigError for anything but plain http(s)."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ConfigError(f"base URL must look like http://host:port, got {url!r}")
    try:
        parts.port  # noqa: B018 - raises ValueError for a malformed port
    except ValueError as exc:
        raise ConfigError(f"base URL has an invalid port: {url!r}") from exc
    if parts.username or parts.password:
        raise ConfigError("base URL must not embed credentials; set SGLANG_API_KEY instead")
    if parts.query or parts.fragment:
        raise ConfigError("base URL must not include a query string or fragment")
    return url.rstrip("/")


@dataclass(frozen=True, repr=False)
class Settings:
    """Connection and concurrency settings. Environment variables:

    SGLANG_BASE_URL, SGLANG_MODEL, SGLANG_API_KEY, ORCH_REQUEST_TIMEOUT_S, ORCH_MAX_CONCURRENCY.
    """

    sglang_base_url: str = DEFAULT_BASE_URL
    sglang_model: str | None = None
    sglang_api_key: str | None = None
    request_timeout_s: float = 60.0
    max_concurrency: int = 8

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if environ is None else environ
        try:
            timeout = float(env.get("ORCH_REQUEST_TIMEOUT_S", "60"))
            concurrency = int(env.get("ORCH_MAX_CONCURRENCY", "8"))
        except ValueError as exc:
            raise ConfigError(
                "ORCH_REQUEST_TIMEOUT_S must be a number and ORCH_MAX_CONCURRENCY an integer"
            ) from exc
        settings = cls(
            sglang_base_url=env.get("SGLANG_BASE_URL") or DEFAULT_BASE_URL,
            sglang_model=env.get("SGLANG_MODEL") or None,
            sglang_api_key=env.get("SGLANG_API_KEY") or None,
            request_timeout_s=timeout,
            max_concurrency=concurrency,
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        validate_base_url(self.sglang_base_url)
        if not 1 <= self.request_timeout_s <= 3600:
            raise ConfigError("ORCH_REQUEST_TIMEOUT_S must be between 1 and 3600 seconds")
        if not 1 <= self.max_concurrency <= 256:
            raise ConfigError("ORCH_MAX_CONCURRENCY must be between 1 and 256")

    def __repr__(self) -> str:
        key_state = "set" if self.sglang_api_key else "unset"
        return (
            f"Settings(sglang_base_url={self.sglang_base_url!r}, sglang_model={self.sglang_model!r}, "
            f"sglang_api_key=<{key_state}>, request_timeout_s={self.request_timeout_s}, "
            f"max_concurrency={self.max_concurrency})"
        )
