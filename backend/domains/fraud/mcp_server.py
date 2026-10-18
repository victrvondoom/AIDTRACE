"""MCP server that exposes the fraud-graph tools to any MCP client (Claude Code, Claude Desktop, ...).

Run:  python -m app.mcp_server        (stdio transport)

Exposed: read tools plus propose_freeze. Approval and execution are deliberately NOT exposed over MCP,
so an external agent can propose an action but cannot carry it out.
"""
from mcp.server.fastmcp import FastMCP

from domains.fraud.store import GraphStore
from domains.fraud.tools import GraphTools

mcp = FastMCP("track1-fraud-graph")
_tools: GraphTools | None = None


def _graph() -> GraphTools:
    global _tools
    if _tools is None:
        _tools = GraphTools(GraphStore())
    return _tools


@mcp.tool()
def flagged_transactions() -> list[dict]:
    """List flagged transactions and the account each came from."""
    return _graph().flagged_transactions()


@mcp.tool()
def account_profile(account_id: str) -> dict:
    """Devices, cards and IP addresses linked to one account."""
    return _graph().account_profile(account_id)


@mcp.tool()
def ring_members(account_id: str) -> list[dict]:
    """Accounts linked to this one through shared device or card, each with the shortest graph path."""
    return _graph().ring_members(account_id)


@mcp.tool()
def weak_links(account_id: str) -> list[dict]:
    """Accounts that share only an IP with this one. Weak evidence, never a basis for action."""
    return _graph().weak_links(account_id)


@mcp.tool()
def propose_freeze(account_id: str) -> dict:
    """Propose freezing the strong-link ring around an account. Creates a PROPOSED action for human approval."""
    return _graph().propose_freeze(account_id, run_id="mcp")


if __name__ == "__main__":
    mcp.run()
