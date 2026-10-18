# Agent runtime consolidation

| Runtime | State |
|---|---|
| Track 01 investigator (deterministic planner + Claude tool loop) | Ported to `backend/domains/fraud`; deterministic planner runs natively with a recorded event trace (tool calls, graph queries, proposals) shown in the UI. Claude planner needs `ANTHROPIC_API_KEY` (not configured). |
| Track 01 MCP server | Ported; exposes five tools and no approve/execute tool (checked from source). Cannot import beside Kairos's pinned pydantic 2.7.4, so it must run as a separate private process. |
| GreenChain Dedalus agents | Ported (`agents.py`, `tools.py`); reachable at `/greenchain/search`; needs Dedalus and search keys; closed to the demo role. Not run. |
| RESOLVE-AI-main LangGraph agents (47 files) | Ported into the private worker; reachable at `/resolveai/platform/agents/*`. Not run (needs its services and a model key). |
| Kairos existing agents | Unchanged. |

**Shared guardrails already in place:** an agent can propose but never execute; code derives the action set; a human approves under their own identity; approvals are re-validated against current evidence (fraud) or the evidence revision (consumer).
**Not done:** one common runtime interface (task, handoff, memory, trace) over the four frameworks. They coexist behind separate routers.