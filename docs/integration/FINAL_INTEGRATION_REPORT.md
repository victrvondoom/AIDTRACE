# Kairos / ResolveAI integration report

**Status: IN PROGRESS — this is a checkpoint, not a completion claim.**  
**Updated:** 2026-10-18

## Product boundary

Kairos remains the canonical product and owns the application experience, identity, roles and workflow. ResolveAI is exposed within Kairos. FalkorDB stores this workstream's site-scoped evidence-dependency graph; existing Neo4j and other data services were not migrated.

## Delivered in this checkpoint

- A real local FalkorDB path records a synthetic source change, claims, cross-agent memory handoff, decision, immutable decision revisions, review receipt, plan, action state and audit hash.
- A compare-and-set revision writer rejects stale head changes and replays the same revision idempotently.
- The action remains suspended when the stored human-review receipt is tied to an older graph revision.
- ResolveAI UI offers Broad, Targeted and Hyperfocus plans plus a channel readiness map for Document, Text, Voice, Image, Video and Telemetry. It names Kairos's separate document/image OCR, Work Order voice and event ingestion routes, but clearly shows that those routes are not yet case-linked; video has no connected processor. Only synthetic source/text fixtures are used by this case.
- All focus levels preserve the bounded impact closure and revision-bound action gate; focus changes the deterministic investigation emphasis. The live agent runtime is still not connected.
- First Domino's revision-pinning/review-lineage behavior was adapted into Kairos. Exact commit, source paths, no-license status, owner-permission attestation and test evidence are in `SOURCE_PROVENANCE.md` and `98_SOURCE_MASTER_LEDGER.csv`. No upstream source lines or application shell were copied.
- Beyondions' root-cause agent was inspected and classified `REFERENCE_ONLY` pending a bounded ResolveAI tool-trace adapter; its unbounded graph traversals and Groq/Streamlit runtime were not imported.
- Existing drift routes now have canonical prefixes, staff authorization, site scope, OPA read mapping and demo write fences.
- Verification: 177 backend/authz/tenant tests passed, 5 skipped; Next.js production build passed. See `TEST_EVIDENCE.md`.

## Source progress

- 98 repository identities in the source ledger.
- 71 source records present (70 implementation audits plus one verified empty upstream); 27 nonempty identities still need source inspection.
- One audited source's revision/review behavior is adapted and tested; one is documented as reference-only; 68 other audited sources await integration review.
- The other repositories are not counted as integrated. User permission is recorded as `USER_ATTESTED_OWNER_PERMISSION`; it has not been independently verified. First Domino has no license file, and the actual commercial grant scope is not documented here.

## Outstanding product work

- Connect an actual authenticated evidence-ingestion route with source hash, authority proof, temporal version and idempotency receipt.
- Replace the fixed scenario with a bounded ResolveAI adapter that returns cited claims and cannot set evidence validity, permissions or action eligibility.
- Build authenticated human review and independent outcome verification for current evidence revisions.
- Connect real agent orchestration, persistent production memory and modality-specific document/voice/image/video/telemetry parsers.
- Continue the 98-source queue, source-license/dependency/security review, and capability-specific integrations.
- Validate backups, restore, monitoring, deployment, commercial licensing, browser interactions and production readiness.

No production or external action was executed. No cloud store was written. The local working tree remains uncommitted to preserve unrelated user changes already present in the checkout.
