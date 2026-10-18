"""Generic JSON-over-HTTP adapter for a future Kairos Evidence Drift endpoint."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from adapters.base import AdapterResult


class HttpJsonEvidenceDriftAdapter:
    """Send fixture inputs to an explicitly configured HTTP JSON endpoint."""

    def __init__(self, endpoint: str, bearer_token: str | None = None, timeout_seconds: float = 10.0) -> None:
        """Set the endpoint and optional bearer credential."""
        self.endpoint = endpoint
        self.bearer_token = bearer_token
        self.timeout_seconds = timeout_seconds

    def evaluate(self, scenario: dict[str, Any]) -> AdapterResult:
        """Post a scenario without its expected results and parse the response contract."""
        payload = {
            key: scenario[key]
            for key in (
                "scenario_id",
                "scenario_type",
                "tenant_id",
                "source_evidence_id",
                "updated_evidence_id",
                "original_evidence",
                "updated_evidence",
                "events",
                "nodes",
                "relationships",
            )
        }
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        request = Request(self.endpoint, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError) as exc:
            raise RuntimeError(f"Evidence Drift API request failed: {exc}") from exc
        if not isinstance(result, dict):
            raise TypeError("Evidence Drift API must return a JSON object")
        affected = result.get("affected_decisions")
        memory_valid = result.get("memory_valid")
        if not isinstance(affected, list) or not all(isinstance(value, str) for value in affected):
            raise TypeError("API response must include affected_decisions as a list of strings")
        if not isinstance(memory_valid, bool):
            raise TypeError("API response must include memory_valid as a boolean")
        return AdapterResult(frozenset(affected), memory_valid)
