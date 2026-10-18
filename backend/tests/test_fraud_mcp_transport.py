"""MCP transport check for the fraud server, run in a SEPARATE interpreter.

The MCP SDK needs a newer pydantic than the one Kairos pins (2.7.4), so the server cannot import inside the Kairos
environment. This test seeds a throwaway synthetic graph, starts `python -m domains.fraud.mcp_server` over stdio with an
interpreter that has `mcp` + `falkordb` (set MCP_TEST_PYTHON; see backend/requirements-mcp.txt), and calls its tools
through a real MCP client. It skips when that interpreter or FalkorDB is not available."""
from __future__ import annotations

import json
import os
import random
import subprocess
from pathlib import Path

import pytest

from domains.fraud import seed
from domains.fraud.store import GraphStore

URL = os.environ.get("FALKORDB_TEST_URL", "")
PY = os.environ.get("MCP_TEST_PYTHON", "")
pytestmark = pytest.mark.skipif(not (URL and PY), reason="set FALKORDB_TEST_URL and MCP_TEST_PYTHON (interpreter with mcp + falkordb)")
BACKEND = str(Path(__file__).resolve().parents[1])

CLIENT = r'''
import asyncio, json, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main(backend, url, graph):
    params = StdioServerParameters(command=sys.executable, args=["-m", "domains.fraud.mcp_server"],
        env={"PYTHONPATH": backend, "FALKORDB_URL": url, "FRAUD_GRAPH_NAME": graph, "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", "")})
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as session:
            await session.initialize()
            text = lambda res: "".join(c.text for c in res.content)
            out = {"tools": sorted(t.name for t in (await session.list_tools()).tools),
                   "ring": text(await session.call_tool("ring_members", {"account_id": "RA3"})),
                   "decoy": text(await session.call_tool("propose_freeze", {"account_id": "HH1"}))}
            print("RESULT" + json.dumps(out))
asyncio.run(main(*sys.argv[1:4]))
'''


def test_mcp_server_serves_reads_and_propose_only_over_stdio() -> None:
    graph = "fraud_mcp_transport_test"
    store = GraphStore(URL, graph)
    try:
        seed.load(store, seed.build_dataset(random.Random(seed.SEED)))
        done = subprocess.run([PY, "-c", CLIENT, BACKEND, URL, graph], capture_output=True, text=True, timeout=120,
                              env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"})
        line = next(row for row in done.stdout.splitlines() if row.startswith("RESULT"))
        result = json.loads(line[len("RESULT"):])
    finally:
        store.reset_synthetic_graph()
    assert result["tools"] == ["account_profile", "flagged_transactions", "propose_freeze", "ring_members", "weak_links"]
    assert "RA1" in result["ring"]  # the planted ring is found through the MCP tool
    assert "rejected" in result["decoy"]  # the household decoy is refused by policy, not by the caller
