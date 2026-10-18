"""Adapter contract for independent evidence drift engine evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class AdapterResult:
    """Normalized output returned by a decision engine adapter."""

    affected_decisions: frozenset[str]
    memory_valid: bool


class EvidenceDriftAdapter(Protocol):
    """Interface implemented by optional Kairos or other engine adapters."""

    def evaluate(self, scenario: dict[str, Any]) -> AdapterResult:
        """Evaluate one scenario and return normalized decision and memory results."""
        ...
