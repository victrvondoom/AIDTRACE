"""Append-only, redacted record of what a run did. Traces can contain prompts and tool arguments,
so treat exported files as sensitive."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

REDACTED = "[REDACTED]"


@dataclass(frozen=True)
class Event:
    seq: int
    at: str
    type: str
    data: dict[str, Any]


class Trace:
    def __init__(self, *, secrets: Iterable[str] = ()) -> None:
        self._events: list[Event] = []
        # Longest first, so a secret that contains a shorter secret is replaced whole.
        self._secrets = tuple(sorted({s for s in secrets if s}, key=len, reverse=True))

    def record(self, event_type: str, **data: Any) -> Event:
        event = Event(
            seq=len(self._events) + 1,
            at=datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            type=event_type,
            data={key: self._scrub(value) for key, value in data.items() if value is not None},
        )
        self._events.append(event)
        return event

    @property
    def events(self) -> tuple[Event, ...]:
        return tuple(self._events)

    def types(self) -> list[str]:
        return [event.type for event in self._events]

    def to_dict(self) -> dict[str, Any]:
        return {"events": [asdict(event) for event in self._events]}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    def _scrub(self, value: Any) -> Any:
        if isinstance(value, str):
            for secret in self._secrets:
                value = value.replace(secret, REDACTED)
            return value
        if isinstance(value, dict):
            return {key: self._scrub(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._scrub(item) for item in value]
        return value
