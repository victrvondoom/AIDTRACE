"""Opt-in live smoke test for the AIDTRACE Claude integration. Run by hand, once the key is configured. Never run in CI.

It makes one paid request: a tiny connectivity ping that contains no graph data and no question. It refuses to run
unless AIDTRACE_LIVE_SMOKE=1 is set, and it never prints the key.

    AIDTRACE_LIVE_SMOKE=1 python scripts/aidtrace_agent_live_smoke.py      (from the backend directory)
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.config import Settings  # noqa: E402
from api.services.aidtrace_agent.provider import MESSAGES, ClaudeMessages, ProviderError, readiness  # noqa: E402


async def ping(settings: Settings) -> int:
    client = ClaudeMessages(settings)
    try:
        reply = await client.create(
            system="Reply with the single word: ok",
            messages=[{"role": "user", "content": "ping"}],
            tools=[],
        )
    except ProviderError as exc:
        print(f"FAILED: {exc.code}. {MESSAGES[exc.code]}")
        return 1
    text = "".join(getattr(block, "text", "") for block in reply.content if getattr(block, "type", None) == "text")
    usage = reply.usage
    print(f"model: {settings.ANTHROPIC_MODEL}")
    print(f"stop_reason: {reply.stop_reason}")
    print(f"tokens: input={usage.input_tokens} output={usage.output_tokens}")
    print(f"reply: {text.strip()[:40]!r}")
    if not text.strip():
        print("FAILED: the model returned no text.")
        return 1
    print("Live connectivity verified for this model and key.")
    return 0


def main() -> int:
    if os.environ.get("AIDTRACE_LIVE_SMOKE") != "1":
        print("Refusing to run: set AIDTRACE_LIVE_SMOKE=1. This script makes one paid Anthropic request.")
        return 2
    settings = Settings()
    state = readiness(settings)
    if not state.ready:
        print(f"Not ready: {state.state}. {state.reason}")
        return 1
    return asyncio.run(ping(settings))


if __name__ == "__main__":
    raise SystemExit(main())
