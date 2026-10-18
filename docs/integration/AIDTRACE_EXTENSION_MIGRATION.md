# AIDTRACE extension migration ledger

Every legacy page and hub feature that is still useful opens as an extension inside `/hub`. The address bar never changes. This ledger records what each one
actually does today, not what its card says. Verified on 2026-10-18 against the running app at `http://localhost:3000/hub` (Next dev, API on `:8100`, FalkorDB on `:6380`).

## How it works

| Piece | File |
|---|---|
| Registry (one entry per extension: category, tabs, permission path, backend, keywords) | `frontend/src/components/aidtrace/extensions/registry.tsx` |
| Route table (every migrated legacy page, with params and an async-server-page flag) | `…/extensions/legacy-routes.ts` |
| Route host (renders an unchanged legacy page module with its pathname, params, search params and a router that navigates the workspace; intercepts links) | `…/extensions/route-host.tsx` |
| Shared context (selection, investigation, evidence, recommendation, run log) and per-supplier derivation | `…/extensions/context.tsx` |
| Extension panel (title, context line, scope note, summary header, tabs, back) | `…/extensions/panel.tsx` |
| Searchable launcher drawer (closed by default; role-restricted entries are disabled, not hidden) | `…/extensions/launcher.tsx` |
| Native, context-aware bodies (Risk Analytics, Connected Graph, Decision Validity, Provenance, Activity, Evidence-for-context) | `…/extensions/native.tsx` |
| Hosted-page chrome (decorative header slab, long intro, centred width removed) | `.aidtrace-ext` rules at the end of `frontend/src/app/globals.css` |

Four legacy pages are async server components (assets, documents, briefs, off-boarding). The host awaits them in the browser; they are ordinary async functions over client-callable APIs.

## Status

**Verified live** = opened in the running app and its data came from the real backend. **Hosted** = the real page module renders and navigates inside the workspace, but its data
cannot load here. **Blocked** = the page's backing service is not running in this environment (see "External blockers").

| Extension | Original route(s) | New component | Backend | Status | What was verified | Limits |
|---|---|---|---|---|---|---|
| GreenChain | hub feature `greenchain`, `simulations` | feature bodies in registry | `/greenchain/*`, `/agent-memory/*` | Verified live | Opens in place; scoring, globe, what-if (earlier sessions); Packaging D/B ranking flows | Candidates illustrative; live discovery needs provider keys |
| Supplier Registry | `/assets`, `/assets/register`, `/assets/bootstrap`, `/assets/:id` | hosted pages | `/assets/*` (Neo4j) | Hosted, data blocked | Shell, tabs, error state ("could not be shown. Try again") | Neo4j not running; `/api/assets` also loops through the dev proxy (see below) |
| Risk Analytics | `/overview` (KPIs, attention list) | `native.tsx › RiskAnalytics` | agent-memory snapshot (live); `/governance/*`, `/compliance/dashboard`, `/events` | Verified live (supplier part) | For the selected supplier: connected records 15, stale memories 1, blocked decisions 1, pending reviews 0, unhashed sources 0 of 5; charts highlight it | Governance/compliance/event tiles show "—" with an unavailable notice (never 0) until Neo4j/Supabase respond |
| Agent Assistant | `/copilot` | hosted page | `/search/*` (Qdrant, Elasticsearch) | Hosted, backend not verified | Full UI renders | Answers need the retrieval stores |
| Root Cause Analysis | `/rca` | hosted page | `/rca/*` | Hosted, backend not verified | Full UI renders | Scope note shown: built for equipment-failure analysis, not adapted to supplier disruption |
| Connected Graph | `/graph`, Graph Lab | `native.tsx › ConnectedGraph` + hosted `/graph` + Graph Lab feature | `/graphlab/*` over the persisted FalkorDB graph | Verified live (Dependencies) | 76 nodes / 136 edges read from FalkorDB; 19 records in Packaging B's impact; type filters and Impact only | Entity-graph tab (`/graph`) needs Neo4j |
| Event Timeline | `/events`, `/events/:id`, `/overview/cross-site` | `native.tsx › ActivityTimeline` + hosted pages | `/events/*`, agent-memory snapshot | Verified live (Activity) | Graph history plus this session's runs, newest first | Events and cross-site tabs need the event store |
| Evidence Vault | `/documents`, `/documents/ingest`, `/documents/compare`, `/documents/:id`, `/documents/:id/topology` | `native.tsx › EvidenceForContext` + hosted pages | `/documents/*`; agent-memory snapshot | Verified live (context) / data blocked (library) | "Evidence behind Packaging B": 12 sources with trust labels and Open-document links; Ingest form renders | Library/detail need Neo4j + the document store |
| Evidence Coverage | `/overview/coverage` | hosted page | `/compliance/*`, `/assets/*` | Hosted, data blocked | Shows "Couldn't load coverage. Retry" | Needs the asset graph |
| Knowledge Transfer | `/offboarding`, `/offboarding/:sessionId` | hosted pages | `/offboarding/*`, `/elicitation/*` | Hosted, data blocked | Surfaces the real backend error (`/elicitation/offboarding → HTTP 500`) | Needs its store |
| Investigation Workspaces | `/projects` | hosted page | `/projects/*` | Hosted, data blocked | Shows "Couldn't load the engineering portfolio. Retry" | Needs the asset graph |
| Field Capture | `/field/voice`, `/field/deviation`, `/field/elicitation/:id` | hosted pages | `/field/*` | Hosted | Voice and deviation tabs render | Capture submission not exercised |
| Governance | `/governance` and 10 sub-pages | `native.tsx › DecisionValidity` + hosted pages | agent-memory (live); `/governance/*` | Verified live (decisions) / queues blocked | Decision states from backend fields; Approve disabled when blocked; in-extension navigation: clicking a conflicts link kept the URL, switched tab, added Back | Queue pages need Neo4j/Supabase |
| Audit & Provenance | `/audit` | `native.tsx › Provenance` + hosted page | `/audit/*`, agent-memory snapshot | Verified live (Provenance) | Lineage and timeline render from the graph | Audit-trail tab not data-verified |
| Compliance & Controls | `/compliance`, `/compliance/audit-pack`, `/compliance/nonconformance` | hosted pages | `/compliance/*` | Hosted, data blocked | Shows "signal timed out. Retry" | Scope note shown: OISD / ISO 45001 / PESO are plant regulations, not supply-chain or cyber requirements |
| Notices & Acknowledgements | `/briefs`, `/briefs/:id` | hosted pages | `/briefs/*` | Hosted, data blocked | "could not be shown. Try again" | Needs the briefs store |
| ResolveAI | hub features `resolveai`, `consumer` | feature bodies | `/resolveai/*` | Opens without errors | Both tabs open | Without a model key its LLM agents return offline placeholders |
| Cybersecurity Analysis | hub feature `cybersecurity` | feature body | `/graphlab/analyze` | Opens without errors; **partial** | Opens | Model-only: no live security feed |
| Connected-Risk Analysis (Track 01) | hub feature `fraud` | feature body | `/fraud/*` | Opens without errors | Opens | Synthetic transfer network |
| Agent Memory | hub feature `memory` | feature body | `/agent-memory/*` | Verified live | **Defect found and fixed**: crashed on memory records that omit `confidence`/`verification_status`; now normalised | |
| Evidence Drift, Agent Operations, Reports, Capability Workbench | hub features | feature bodies | `/agent-memory/*`, `/agents/*`, `/sources/*` | Open without errors | Open | |
| Service Health | `/system-health` | hosted page | `/health/*` | Restricted | Disabled for the Engineer role, as the old route rule requires | Admin only |

## Retired from navigation (not deleted)

The sidebar's "Legacy pages", the Intelligence Hub list, the All Features catalogue and the command-palette feature list are gone. All pages remain as routes. `/overview`,
`/workspace` and `/supply-chain` redirect to `/hub`. Role-specific entries remain for roles that cannot open the workspace (field worker, compliance auditor).

## External blockers (not code defects)

* The original Kairos stack is not running here: **Neo4j** (`:7687`), **Qdrant**, **Elasticsearch**, and **Supabase** (no credentials). Backend routes for assets, documents, governance
  queues, events, compliance, briefs and health return HTTP 500 for that reason. No infrastructure was started.
* **Dev-proxy redirect loop** (pre-existing): list routes defined with a trailing slash (`/assets/`, `/documents/`) loop through Next's `/api` rewrite, because Next removes the slash and
  FastAPI re-adds it, so those calls end as "Failed to fetch". It does not affect routes without a trailing slash. It should be fixed before relying on those pages in dev.

## Tests

`extensions.test.tsx` (route table, registry shape and permissions, launcher, shared-context derivation), `route-host.test.tsx` (pathname/params/search bridge, link and router interception,
async server pages, not-found, unresolved paths), `panel.test.tsx` (context reaches the extension, cross-extension hand-off, close), and `workspace.test.tsx` (launcher closed by default,
opens in place, URL unchanged, investigation preserved on return).
