# Unified Platform Baseline

Audit date: 2026-10-19; re-verified 2026-10-20 (rows marked 10/20 in the verification table)  
Checkout: `aidtrace-workspace` at `f86445ae2f1ef728570139e6ba8e839adf90099a`  
Product boundary: existing Kairos application with AIDTRACE, Evidence Drift, Agent Memory, GreenChain, Fraud, ResolveAI, and legacy industrial integrations.

## Repository state

The working tree was already dirty when this implementation started. It contains changes across the backend, frontend, docs, and feature routes, plus untracked work. The worktree was preserved; no reset, cleanup, commit, or push was performed. On 2026-10-20, `git status --short` still lists 95 changed or untracked paths on `aidtrace-workspace` at the same HEAD (`f86445a`). This report describes the inspected checkout and its combined working tree, not a clean branch baseline.

The active worktree is `kairos-main` on `aidtrace-workspace`. Two sibling worktrees are marked prunable and were left untouched: `kairos-main-evidence-drift-bench` and `kairos-main-supplier-csv-validator`. Remotes are `aidtrace` (`victrvondoom/AIDTRACE`) and `origin` (`vsrupeshkumar/aidtrace-kairos`).

## Application entrypoints and routes

- Frontend: Next.js app in `frontend/`; the authenticated app layout is under `frontend/src/app/(app)/`.
- Engineering memory: `/agent-sandbox` renders the existing Agent Sandbox with a prominent voice capture, transcript review, save, memory list, and `AGENTS.md` plus MCP configuration export.
- Coordination: `/coordination` API router is mounted by `backend/api/main.py` alongside the existing APIs.
- Existing platform routes remain mounted for Evidence Drift, `/agent-memory`, `/aidtrace-agent`, `/agents`, `/greenchain`, `/fraud`, `/graphlab`, `/resolveai`, `/assets`, `/documents`, `/governance`, `/compliance`, and related Kairos functions.
- The workspace also contains `/procurement` and the existing ResolveAI page; their presence does not establish live data or specialist capability readiness.

## Storage, voice, and isolation

Operational evidence and coordination use the configured `FalkorDriftStore`. Coordination writes runs, tasks, events, findings, checkpoints, and dependency links to the authenticated site's graph. API requests return 503 when FalkorDB is absent or unavailable; production coordination has no process-local memory fallback. Task claiming uses graph compare-and-set.

Engineering judgments use a dedicated FalkorDB graph derived from the authenticated site identifier. It is a separate graph namespace in the configured FalkorDB service, not a separate database daemon or Firecracker/VM sandbox. Persistence and recovery therefore depend on that FalkorDB service's storage volume and backup policy. The voice endpoint sends audio to the configured Groq Whisper service, does not save the recording, and requires transcript review before a human saves guidance.

The `kairos-engineering-memory` MCP server is read-only. It returns only `VALID` judgments, pages through a complete vault scan, and fails closed on graph errors or a vault larger than 10,000 records. Rules export includes current active judgments and instructions to query all MCP result pages before work. MCP must be configured in each coding-agent client and the exported rules must be installed where that agent reads repository instructions. The application cannot force an unconfigured third-party agent to consult memory or literally prevent forgetting.

## Graph and coordination behavior

The existing Evidence Drift engine remains the source of source-version lineage, memory provenance, invalidation, decision revisions, and approval eligibility. Changes here add immutable create-once graph nodes, atomic task-property compare-and-set, and paged memory reads; they do not replace the drift engine.

The AIDTRACE coordination slice is deliberately bounded:

- Worker A reads only exact supplied IDs from the site's graph and cites only nodes that exist.
- Worker B reports registry readiness; it does not execute a domain analysis.
- The deterministic summary labels unavailable specialist work `BLOCKED` and records that domain analysis was not performed.
- Run/task/event/checkpoint state is graph-backed. Retry state, cancellation, and lease recovery are explicit.
- Timeout cancellation stops result persistence, but cannot forcibly terminate an already-running Python thread. Current worker functions are read-only.
- Broad deletion/unlearning returns HTTP 501 with `data_changed: false` until deletion can be verified across every applicable storage layer. No receipt or successful deletion is fabricated.
- `scripts/aidtrace_unified_demo.py` runs existing Evidence Drift and coordination modules against an explicitly configured disposable FalkorDB URL and a fresh namespace. It does not seed default app data or delete the generated graph.

## Capability status

Status describes implemented backend operations, not UI or specification presence.

| Pack | Current status | Evidence boundary / remaining prerequisites |
|---|---|---|
| Platform core | `OPERATIONAL` for registry lookup and deterministic summary; graph lookup is `CONFIGURATION_REQUIRED` | Graph lookup requires reachable FalkorDB; no domain analysis is implied. |
| A: Supply / GreenChain | `PARTIAL` | Existing GreenChain modules remain; connect graph evidence and verify complete routed workflow against a live graph and service. |
| B: Cybersecurity | `PLANNED` | Need authorized SBOM/lockfile and advisory inputs, reachable call paths, dependency constraints, then an isolated test runner before any repair claim. |
| C: Finance / AML | `PARTIAL` | Existing Fraud domain remains; need authorized transactions, evidence-linked tracing, policy gates, role/tenant tests, and human review. No account freeze or filing action is enabled here. |
| D: Incident response / SRE | `PLANNED` | Need authenticated telemetry and service topology adapters, revision-aware runbooks, durable replay, and approval-gated recovery. |
| E: Cloud / DevSecOps | `PLANNED` | Need policy engine and authorized manifests; execute checks in an isolated runner. No deploy or production mutation adapter is registered. |
| F: Research / data engineering | `PLANNED` | Need versioned source contracts, reproducible sandbox execution, duplicate/provenance checks, quarantine, and measured comparison against a baseline. |
| G: Disaster / environment | `PLANNED` | Need authoritative timestamped sensor and geospatial sources plus human-validated escalation. No radiation or disaster frequency inference is active. |
| H: Kairos industrial | `PARTIAL` | Existing Kairos and legacy store integrations are retained; specialist graph evidence adapters and live service verification remain. |
| I: Business / support | `PLANNED`; engineering memory is `PARTIAL` | Memory capture and export are implemented, but each coding agent still needs client-side MCP/rules configuration and live graph verification. |

## Current external services and credentials

At the audit, only PostgreSQL port 5432 was listening (PID 9760). No listener was found on Redis/FalkorDB 6379/6380, API ports 8000/8001, frontend ports 3000/3001, Qdrant 6333, or Elasticsearch 9200. Docker is installed but the Docker Desktop Linux engine pipe is unavailable. These checks establish local listener state only; they do not verify service health, application connectivity, or remote deployment. Re-checked 2026-10-20: the only listener on the checked ports is PostgreSQL on 5432, and the Docker Desktop Linux engine pipe (`dockerDesktopLinuxEngine`) is still absent, so no FalkorDB container can start from this machine.

The codebase also retains Neo4j, Qdrant, Elasticsearch, Supabase/PostgreSQL, Redis, and legacy integration dependencies. Do not remove these to force a Falkor-only demo. An `ANTHROPIC_API_KEY` is present locally, but `AIDTRACE_LLM_ENABLED` is false and no paid API request was made; account-level model access remains unverified. Voice transcription needs the configured Groq credential. MCP clients need a FalkorDB URL and an operator-owned site identifier.

The code and `.env.example` default is `claude-opus-5`; current local settings override it to `claude-opus-5-5`, while the LLM feature switch remains off. The Anthropic SDK is pinned at 1.14.0. Anthropic's [current model-status documentation](https://docs.anthropic.com/en/docs/about-claude/model-deprecations) lists Opus 5 as active and does not list Opus 5.5; account access was not tested. The Anthropic adapter and graph-only fallback remain separate modes. SGLang is not installed or configured here, and no latency, throughput, or cost benchmark supports a claim for adding it.

## Verification performed on this checkout

Rows marked 10/20 were re-run on 2026-10-20. Other rows are from the 2026-10-19 audit and were not re-run.

| Check | Result | Scope and limitation |
|---|---|---|
| Targeted backend pytest (10/20) | 78 passed, 23 skipped, 0 failed | Files: `test_coordination`, `test_coordination_api`, `test_coordination_falkordb_integration`, `test_engineering_vault`, `test_graph_chat`, `test_evidence_drift_contracts`, `test_evidence_drift_engine`, `test_aidtrace_agent`, `test_agent_memory`, `test_drift_store`. Run with the repository `.venv` (Python 3.12.10, pytest 9.1.1, pinned requirements), from `backend/` with `PYTHONDONTWRITEBYTECODE=1 ../.venv/Scripts/python.exe -m pytest -p no:cacheprovider tests/...`. Running from the repo root failed collection (`No module named 'api'`) because `backend/pytest.ini` was empty. Fixed 2026-10-20: it now sets `pythonpath = . ..`, and both invocations collect. No import shims were used. All 23 skips are FalkorDB integration tests that need `FALKORDB_TEST_URL` or `AIDTRACE_COORDINATION_TEST_URL`: 15 agent memory, 7 drift store, 1 coordination. The 10/19 run used isolated temp dependencies and a test-only shim; this run did not. |
| FalkorDB integration tests (10/20) | 23 skipped, 0 run | Every FalkorDB-backed case in the targeted files was skipped because no graph URL was set and no FalkorDB is listening (see the Docker status above). Persistence, compare-and-set, site isolation, and drift-store behaviour against a real graph remain unverified. |
| Frontend Vitest (10/20) | 466 passed across 98 files | Repository frontend suite, re-run with `npx vitest run` in `frontend/`. Matches the 10/19 result. |
| Full backend pytest (10/20) | 270 passed, 69 skipped, 0 failed | `backend/tests` as a whole, from `backend/`. Skips are environment-gated (FalkorDB, worker, and service integration). Includes the 75 orchestration tests below. |
| Orchestration tests (10/20) | 75 passed | `backend/tests/test_orchestration_*.py`: protocol and status-code mapping with a mocked transport; the agent loop and tool grants; scheduling; a fake SGLang server on a real localhost socket; the CLI. No live SGLang server was used. |
| ESLint (10/20) | 0 errors, 12 warnings | `npx eslint .` in `frontend/`. Warnings are unused variables, hook dependencies, and `window.location` navigation. Not changed. |
| TypeScript (10/20) | `npx tsc --noEmit` exit 0 | Frontend typecheck, re-run 2026-10-20. |
| Targeted ESLint | Passed | Coordination workspace, engineering-memory panel, and lab API types. |
| Frontend production build | `npm run build` passed | Next.js compiled and generated all 16 static pages; this does not verify backend connectivity or deployment. |
| Python bytecode compile | Passed | Changed coordination, memory, router, and demo modules. |
| MCP module import | Passed 10/19 in an isolated environment; not re-run 10/20 | `mcp` is pinned only in `backend/requirements-mcp.txt`. It is deliberately kept out of `backend/requirements.txt` because the MCP SDK needs a newer pydantic than the 2.7.4 pin. The `.venv` therefore has no `mcp` and must not be used to start an MCP server. Covers `api/services/memory/engineering_mcp.py` and the existing `domains/fraud/mcp_server.py`. No MCP client session or live graph call was made. |
| `git diff --check` | Passed | Tracked diff whitespace check. |
| Unified demo | Not executed | It safely refused to start because `AIDTRACE_DEMO_FALKORDB_URL` is not set. No demo outcome is claimed. |
| Live Anthropic call / deployment | Not verified | A key is configured but no API call was made; no graph service or Docker engine is available. |

The full backend suite and deployment were not verified. Test results above are not proof of production readiness.

Not run on 2026-10-20, with reasons:

- Root `tests/` integration suite. Its `conftest.py` expects a live API on `localhost:8000` (`make dev`). Its session teardown runs `scripts/purge_test_data.py`, which deletes test-prefixed records from whatever database is configured. Nothing confirms that database is disposable, and the directive forbids touching production Postgres, so the suite was not run.
- Unified demo and FalkorDB persistence tests. Both need a disposable FalkorDB URL that does not exist on this machine.

## Dependency-aware integration plan

1. **Common graph and evidence foundation.** Start an isolated, disposable FalkorDB service (the repository `.venv` already imports the pinned backend requirements as of 2026-10-20; `mcp` is not among them); run the opt-in persistence/CAS test; verify graph naming, site isolation, retries, and backups. Add live health probes and a stable evidence envelope that preserves source IDs, timestamps, status, provenance, and revision. Do not use synthetic graph adapters as production proof.
2. **Engineering memory and Kairos industrial (I/H).** Configure the MCP server for the same approved site graph, install the exported rules at the repository/client boundary, and verify read-only recall, stale-memory exclusion, pagination, voice transcript review, and volume recovery. Map existing industrial evidence to the common contract while retaining Neo4j/Qdrant/Elasticsearch where still required.
3. **Supply and finance (A/C).** Connect existing GreenChain and Fraud operations one at a time through registered adapters. For each, validate real input provenance, tenant access, deterministic totals/paths, replay, freshness invalidation, and human approval before consequential actions. Do not assert legal deadlines or measured outcomes without primary-source evidence and representative benchmarks.
4. **Cybersecurity (B).** Implement read-only lockfile/SBOM/advisory ingestion and exact reachability paths first. Only then run candidate upgrades in a disposable, network-restricted sandbox with resource limits and smoke-test receipts. Docker is currently unavailable; do not run untrusted installs on the host.
5. **SRE and cloud operations (D/E).** Connect authorized telemetry and policy sources, store deployment/runbook revisions, and test replay/fault injection in a non-production environment. Add approval-gated recovery only after diagnostics are verified; keep production deploy credentials out of the registry until scoped and audited.
6. **Research/data and environment (F/G).** Add source contracts, provenance and duplicate detection, quarantine, reproducible experiments, authoritative geospatial/sensor observations, uncertainty bounds, and human-reviewed escalation. No personal purchase-intent inference, unsupported radiation estimates, or automated emergency dispatch.
7. **Business/support swarm (I).** Reuse the engineering memory boundary for reviewed knowledge with explicit tenant and client setup. Add support adapters only when source access, lifecycle, retention, audit, and escalation rules are tested.
8. **Model/observability evaluation.** Keep the bounded Anthropic adapter and deterministic graph path. An opt-in SGLang backend now exists in `backend/orchestration/` (standalone, OpenAI-compatible API, documented in its README). It is tested against a fake server and a local socket, not a live SGLang server. Benchmark identical structured tasks on the real model and hardware before claiming an improvement. Trace real run/task/model/tool spans without secrets or unsupported telemetry.
