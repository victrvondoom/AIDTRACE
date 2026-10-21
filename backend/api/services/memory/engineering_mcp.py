"""Read-only stdio MCP bridge to the engineering sandbox vault.

Configure KAIROS_ENGINEERING_SITE and FALKORDB_URL in the local MCP client. The site is
configuration owned by the operator, never supplied as a tool argument. Writes remain in
the authenticated Kairos UI so a coding agent cannot silently teach itself new policy.
"""
from __future__ import annotations

import hashlib
import os
from functools import lru_cache

from mcp.server.fastmcp import FastMCP

from api.services.drift.store import FalkorDriftStore
from api.services.memory.agent_memory import AgentMemory
from api.services.memory.engineering_vault import EngineeringMemoryVault

mcp = FastMCP("kairos-engineering-memory")


@lru_cache(maxsize=1)
def _vault() -> EngineeringMemoryVault:
    site = os.environ.get("KAIROS_ENGINEERING_SITE", "").strip()
    url = os.environ.get("FALKORDB_URL", "").strip()
    if not site or not url:
        raise RuntimeError("Set KAIROS_ENGINEERING_SITE and FALKORDB_URL before starting this MCP server.")
    isolated_site = "eng_" + hashlib.sha256(site.encode("utf-8")).hexdigest()[:32]
    return EngineeringMemoryVault(AgentMemory(FalkorDriftStore(url), isolated_site), isolated_site)


@mcp.tool()
def engineering_memory_recall(query: str = "", limit: int = 20, offset: int = 0) -> dict:
    """Recall human-authored engineering judgments; follow next_offset until null. Read-only."""
    return {"status": "READY", "vault": "engineering-sandbox",
            **_vault().recall(query, limit=limit, offset=offset)}


@mcp.tool()
def engineering_memory_rules() -> str:
    """Return the fail-closed coding rules and current engineering judgments. Read-only."""
    return _vault().export_rules()["rules"]


if __name__ == "__main__":
    mcp.run()
