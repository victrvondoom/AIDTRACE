# Integration progress checkpoint

**Updated:** 2026-10-18
**Canonical product:** Kairos
**Current workstream:** Site-scoped ResolveAI Evidence Drift with revision-bound review

## Working implementation

- Kairos remains the canonical application; ResolveAI is routed inside Kairos. Existing Neo4j, Supabase, Qdrant and Elasticsearch services remain separate and were not migrated.
- The Evidence Drift graph is site-scoped in FalkorDB. The typed contract validates labels, relationships, identifiers and property values; impact discovery uses bounded read-only graph queries and deterministic traversal.
- `GET` and `POST /resolveai/drift/demo` read and run an isolated synthetic evidence change. It creates source versions, claims, a two-agent memory handoff, a typed decision, revision chain, human review receipt, plan, action state and audit hash.
- Decision revisions append through a FalkorDB compare-and-set head update. A review receipt is immutable and pinned to its reviewed graph hash. If current evidence changes that hash, the action remains suspended.
- The frontend ResolveAI page exposes the synthetic cascade, revision lineage, approval mismatch, and selectable Broad/Targeted/Hyperfocus plans. Its channel map names Kairos's separate document/image OCR, Work Order voice and operational event entrypoints, identifies that they lack a ResolveAI case adapter, and marks video processing unavailable.
- Every focus level preserves the full bounded impact traversal and revision-bound action gate; focus changes investigation emphasis, not safety coverage. The live agent runtime and execution budgets are not connected.
- Existing `/drift` endpoints now use one route prefix, staff role checks, authenticated site scope and the showcase write fence. Their OPA read action maps to Kairos's existing `read_resolveai` role policy.
- First Domino's revision and review-lineage behavior has been adapted against Kairos contracts. No First Domino source code, clinical rule, frontend or runtime dependency was copied.
- Beyondions root-cause agent source was inspected and classified reference-only; its unbounded service graph and Groq/Streamlit runtime do not fit this deterministic slice.

## Source inventory

- Repository identities in the master ledger: 98.
- Source-audit JSON records: 71 (70 implementation audits plus one verified empty-source record); remaining nonempty source inspections: 27.
- First Domino behavior adaptations verified in Kairos: 1.
- Beyondions source integrations: 0 (reviewed and classified reference-only).
- Other reviewed repositories awaiting integration decisions: 68.
- Repositories without source review: 27; one additional checkout is verified empty and recorded as `NO_UPSTREAM_IMPLEMENTATION`.
- Direct upstream source code copied into the current slice: 0.
- User-attested owner permission is recorded for all 98 identities; grant scope is not independently verified. First Domino has no license file.

## Verification evidence

- Combined `backend/tests`, `tests/test_authz_boundary.py`, and `tests/test_tenant_isolation.py`: **177 passed, 5 skipped**, using local FalkorDB 4.22.1 and isolated synthetic test graphs.
- The expanded run exposed and fixed a decision-gate precedence defect: known expired/stale blockers now take `HOLD` precedence over missing-evidence summaries. The test now distinguishes graph-node findings from missing-type findings.
- Frontend `npm run build`: passed after the focus contract and modality-readiness map were added; Next.js compile, TypeScript and page generation completed.
- Two existing dependency deprecation warnings remain in the test environment (`gotrue` and Starlette's `TestClient` integration).
- Python module syntax compilation: passed before the latest API route-boundary edits; covered by the passing backend import/test run afterward.
- No external plant, security or financial action was executed. No cloud store was read or written. The demo creates only synthetic records in a local FalkorDB site graph.

## Current limits

- The synthetic case does not ingest an uploaded document, invoke a live ResolveAI specialist, or run an LLM. Agent focus levels are graph trace metadata, not an active agent orchestrator.
- Live multimodal case ingestion (document/image, voice and telemetry), video processing, production case ingestion, authenticated human review, external action adapters and independent recovery verification are not connected by this slice. The modality panel only reports existing separate Kairos entrypoints; it does not imply case-level adapter integration.
- No full 98-source integration, commercial license/grant scope review, production FalkorDB operations, backup/restore drill, independent novelty claim or benchmark is complete.
- Existing shared working-tree changes remain uncommitted; no commit was created because the checkout already contains unrelated user changes and untracked source-audit work.

## Next integration actions

1. Add authenticated, idempotent evidence ingestion with source hash, source authority, source version and independent audit receipt.
2. Add real reviewer approval bound to the current dependency hash and an independent outcome-verification worker.
3. Connect a bounded ResolveAI adapter that returns cited claims only and cannot set permissions, evidence validity or action eligibility.
4. Add case-scoped adapters to existing document/image, voice and event ingestion; then evaluate a video processor and multi-agent runtime budgets. Current focus levels drive the deterministic investigation plan only.
5. Audit and adapt the next distinct source only after reading its implementation, tests, dependency and license state; keep the machine-readable queue current.
6. Continue the remaining 27 source audits and review the 68 other audited repositories; keep the empty source excluded from capability counts.

**Git state:** uncommitted working tree preserved; no reset, clean, destructive migration or commit performed.
