# FalkorDB integration report — 2026-10-18

## Scope and repository audit

Kairos is the existing product in `kairos-main`. Its frontend is Next.js/React (`frontend/`), its API is Python/FastAPI (`backend/api/`), and its graph-backed workflows are already spread across Evidence Drift, ResolveAI consumer cases, GreenChain decisions, and the fraud runtime. The backend also uses Neo4j for the separate industrial asset/document graph, plus Supabase, Qdrant, Elasticsearch, Redis, and Temporal for their existing roles. This work did not move or delete those stores.

FalkorDB was already a load-bearing part of this application: `falkordb==1.0.10` is pinned to stay compatible with Kairos's Redis 5 client dependency; `FalkorDriftStore` uses the official Python client, one graph per authenticated site, allowlisted labels and relationships, parameterized values, bounded impact traversal, and revision-bound approvals. `AgentMemory` stores source versions, claims, memories, sessions, decisions and influence links. FastAPI exposes site-scoped memory, Graph Lab and `/health/falkordb` endpoints. The frontend already has Graph Lab and hub graph views, so no second visualization product was created.

## Changes completed

| Area | Implementation |
| --- | --- |
| Local and cloud configuration | `.env.example` distinguishes a host `FALKORDB_URL` from Compose's `FALKORDB_CONTAINER_URL`. Compose keeps local FalkorDB profile-gated, exposes `6380` on loopback in the development override, uses the existing named data volume, and configures append-only persistence for new/recreated containers. An existing cloud instance can be selected with authenticated `rediss://` URLs; no cloud service is provisioned. The shared FastAPI client is now initialized under a lock and closed at shutdown. |
| Persistent memory integrity | Reusing a superseded source or claim ID, or a stale memory ID, now fails. New memory checks the current source status and verification before it can be described as verified. A verified-only recall mode excludes unverified memory before recording influence. |
| Complete lineage and retrieval | `memory_lineage` selects a bounded number of memories, retrieves complete claim/source fanout for them, and fails closed if the row budget is exceeded. Recall fails closed when a site's memory count exceeds its safety bound instead of silently omitting later memories. |
| Agent context | `POST /agent-memory/context` and the existing shared `/agents/tools/invoke` interface expose bounded, exact-fact-key, verified context with claim IDs, source version IDs, document IDs, hashes, blocked reasons and the recorded recall session. The payload is labelled untrusted graph memory. This is an agent retrieval interface; it does not silently inject graph text into Copilot's existing evidence and citation gate. |
| Graph API and UI | Existing node upsert/read/update, edge link/unlink, site export, traversal, supersession and revision APIs remain in place. The site Cypher console uses `GRAPH.RO_QUERY`, requires one bounded query and never uses a write-capable query method. The site graph response, relationship distribution, graph inspector fields and link labels were corrected. Scenario data is labelled as a sandbox in the UI. |
| Data preservation | No startup migration, graph reset, paid provision, or cloud write was performed. The setup guide gives a read-first backup, isolated restore rehearsal, same-instance `GRAPH.COPY` prefix cutover and configuration rollback. The existing Neo4j graph stays separate. |

The evidence graph treats supersession and withdrawn/stale status as the deletion lifecycle for governed records. Physical deletion of evidence nodes is deliberately not exposed as a general CRUD endpoint because it would remove provenance; isolated synthetic graphs retain their existing cleanup path.

## Verification performed

- Local container `kairos-falkordb` answered `PING`. Tests used `FALKORDB_TEST_URL=redis://localhost:6380`, random `pytest_*` graph prefixes and site IDs, and `KAIROS_SKIP_TEST_CLEANUP=1` so the repository's broader teardown did not touch other stores.
- Focused graph and memory suite: **36 passed** (`test_agent_memory.py`, `test_agents_runtime.py`, `test_sources_catalog.py`, `test_drift_store.py`). Four additional focused cases passed for pool reconnection, full claim fanout, site-scoped context, and read-only graph querying. The standalone API health/site-graph test and the graph metadata test then passed (**2 passed**); these runs overlap, so their counts should not be summed as unique tests.
- Targeted Ruff: passed. Python compile check: passed. `docker compose --profile local-stores config --quiet`: passed with a temporary empty `.env`, which was removed. `git diff --check`: passed.
- Frontend `tsc --noEmit`: passed. Focused hub/lineage tests: **24 passed**. Next.js production build: passed and emitted the existing `/graph`, `/graph-lab` and `/hub` routes.

## Limits and deployment follow-up

- Cloud TLS/authentication and recovery have not been tested against a paid or existing FalkorDB Cloud instance. The local test verifies Redis client pool reconnection after a disconnect; it does not simulate a prolonged outage or server failover.
- The currently running `kairos-falkordb` container reports `appendonly no`: it predates the Compose change. Back up its existing volume and recreate it through the updated Compose configuration before claiming AOF durability for that instance. No container with existing data was restarted in this work.
- The backup/restore and `GRAPH.COPY` cutover procedure is documented but was not run on real memory data. There is no automatic Neo4j-to-FalkorDB or cross-instance importer.
- The official FalkorDB MCP server is documented as optional and disabled by default. Kairos uses the official Python client directly; no MCP server was started or given application credentials.
- The fraud runtime still declares no shared persistent memory, and automatic injection of graph context into every LLM workflow is not claimed. The new retrieval route and tool are functional for callers that use them. The complete repository suite and a deployed browser session were not run; the tests above cover the changed local graph/API/frontend paths.

See [FALKORDB_SETUP.md](./FALKORDB_SETUP.md) for local setup, cloud opt-in, backup, migration and rollback commands.
