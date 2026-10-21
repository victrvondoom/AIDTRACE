# AIDTRACE

**Graph Hacks 2026 · Track 02: Agent Memory and Coordination** (also fits Track 01)

AIDTRACE gives AI agents a memory they can trust. Every finding an agent records in FalkorDB is linked to the claims and source versions it rests on. When a source changes, the graph marks every dependent memory, decision and pending action as stale, and an approval given to an older decision revision can no longer authorise action.

The agent layer runs on **Claude Opus 5.5** (`claude-opus-5-5`). Claude reasons over the graph through a fixed set of read-only tools. FalkorDB decides what is true. Claude explains it.

## The problem

Agents remember things, but they cannot tell when what they remember stops being true. A supplier audit rule changes from 180 to 90 days. The agent still recalls the old rule, the old recommendation still looks approved, and nothing tells a reviewer which decisions now stand on outdated evidence.

## How the graph does the work

| Graph Hacks requirement | How AIDTRACE meets it |
|---|---|
| Follow connections across data | Source version → claim → memory → decision → action, traversed in FalkorDB with bounded depth |
| Remember across sessions | Agent memories persist in FalkorDB with source, verification state and recall history |
| Share state between agents | Handoffs record which agent produced a memory and which other agents recalled it |
| Connect people, projects and decisions | Decisions are revisioned, and each approval is bound to the exact revision a reviewer saw |
| Show the path behind an answer | Every answer cites node ids, and the provenance view draws the full dependency path |
| Separate memory per tenant | Each site has its own isolated graph, derived from the signed-in user |

## Claude Opus 5.5 agent workflow

```
Question in the workspace
        │
        ▼
Graph engines answer first (no model call)
        │  only if no deterministic route answers
        ▼
Claude Opus 5.5 ── calls read-only tools ──► FalkorDB (caller's site only)
        │            get_memory_snapshot
        │            get_action_eligibility
        │            get_graph_impact
        │            get_agent_handoffs
        │            preview_supplier_what_if
        ▼
Answer with finding, why, affected ids, next step, citations
        │
        ▼
Citation check: every id must have come from a tool result, or the answer is withheld
```

Rules the code enforces, whatever the model says:

- Claude can only read. No tool writes, approves, or runs Cypher, SQL or shell commands.
- At most 6 tool rounds per question, with a timeout and a concurrency limit.
- Text inside graph records is treated as evidence, never as instructions.
- A provider failure keeps the graph results and says plainly that no model interpretation exists.
- No request is sent to Anthropic until `AIDTRACE_LLM_ENABLED=true` and a key is set.

**Status:** the Claude integration is built and covered by 32 offline tests with a mocked model. A live run against the Anthropic API has not been verified yet, and the workspace question box is not yet connected to the Claude endpoint.

Code: `backend/api/services/aidtrace_agent/` (provider, tools, orchestrator) and `backend/api/routers/aidtrace_agent.py` (`GET /aidtrace-agent/status`, `POST /aidtrace-agent/ask`).

## The workspace

`/hub` is a single page with a CesiumJS globe of the supplier network, a graph view, lineage and a timeline. **Extensions → Investigation Workflow** walks one case in four steps:

1. **Investigate**: supplier risk, emissions and the connected graph
2. **Evidence**: the sources behind each claim, and which are superseded
3. **Decision**: whether the decision still stands, with a human approval gate
4. **Audit**: provenance from source to action, and the activity timeline

The Evidence Drift case uses synthetic, clearly labelled data.

## Run it locally

Requirements: Docker Desktop, Python 3.12, Node.js.

```powershell
# 1. Graph store
docker compose --profile local-stores up -d kairos-falkordb

# 2. Backend API on port 8100 (development harness)
.venv\Scripts\python.exe scripts\dev_harness.py

# 3. Website on port 3001
cd frontend
npx next dev -p 3001
```

Open http://localhost:3001 for the landing page and http://localhost:3001/hub for the workspace. In the workspace, run steps 1 and 2 on the left to record a decision and revise its evidence, then open the Investigation Workflow.

## Turn on Claude Opus 5.5

1. Put your key in `kairos-main\.env` (git-ignored): `ANTHROPIC_API_KEY=...`
2. Set `AIDTRACE_LLM_ENABLED=true` in the same file.
3. Restart the backend.
4. Optional connectivity check (one paid request): `$env:AIDTRACE_LIVE_SMOKE = "1"; ..\.venv\Scripts\python.exe scripts\aidtrace_agent_live_smoke.py` from `backend`.

## Modules inside AIDtrace

- **Supply-chain physics and mathematics** (`/physics/*`, `backend/domains/physics/`): cold-chain shelf life (Arrhenius, mean
  kinetic temperature), payload heat transfer (lumped capacitance), queue waits (Kingman, Little) and inventory policy (EOQ,
  safety stock). Every response names its formula and assumptions. No frontend page yet.
- **Catalyst QC** (`/catalyst/*`, `integrations/catalyst`): electrode-material batch QC from FIB-SEM images. Runs as a private
  worker in its own virtualenv because its pins conflict with Kairos's. Start it with `scripts\start_catalyst_worker.py`.
  Setup, the gateway rules and what is not yet verified: [docs/integration/CATALYST_INTEGRATION.md](docs/integration/CATALYST_INTEGRATION.md).

## Tests

```powershell
cd backend;  ..\.venv\Scripts\python.exe -m pytest tests -q
cd frontend; npx vitest run
```

## Stack

FalkorDB · FastAPI · Next.js · CesiumJS · Claude Opus 5.5 (Anthropic SDK) · Docker
