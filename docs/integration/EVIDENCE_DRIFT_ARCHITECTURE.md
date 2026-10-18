# Evidence Drift Cascade: implementation boundary

## Current flow

1. Kairos verifies role and derives the caller site from the authenticated user. The public demo is hard-bound to the showcase site and its synthetic asset ID.
2. The synthetic integration journey records document/source versions, claims, an agent-memory node, decision, plan, proposed action and audit event in the site's FalkorDB graph.
3. A higher-authority verified source supersedes an earlier source and extracted claim.
4. The bounded deterministic reverse-dependency traversal identifies only linked claims, memories, decisions, plans and actions.
5. CausalLatch re-evaluates a typed decision precondition against the newer claim.
6. Kairos appends an immutable decision revision by compare-and-set. A prior synthetic human review stays pinned to the revision and dependency hash it reviewed.
7. The action gate compares that review hash with the current revision. A mismatch suspends the synthetic action and records the before/after hashes in the audit chain. No external action is executed.
8. The ResolveAI panel lets an operator select Broad, Targeted or Hyperfocus scope and request document, text, voice, image, video or telemetry modalities. The deterministic focus plan keeps impact traversal and revision-bound action checks complete at every level, while changing the investigation emphasis. A channel-by-channel map shows the existing Kairos document/image OCR, Work Order voice-note, and operational-event entrypoints as separate flows that are not yet linked to this ResolveAI case; video has no connected processor.

## Limits

The current scenario is deterministic and synthetic. It does not ingest an uploaded document, invoke a ResolveAI model or specialist, import Track 1 code, suspend a real action, or provide production recovery/retention guarantees. Focus selection changes the deterministic plan emphasis but does not change live agent execution budgets because the agent runtime is not connected. Document/text are synthetic graph representations, not parsed uploads. Document/image, voice and operational-event processors exist elsewhere in Kairos but have no case adapter in this flow; video has no connected processor. Fixed IDs and source observations make the scenario idempotent inside a site graph. A separate synthetic prefix keeps it apart from operational records.

## Next integration gate

Add a document-authorized ingestion contract with source hash/version, authority evidence and idempotency receipt; then connect a bounded ResolveAI investigation adapter that can only return cited claims and cannot set final verification or authorize action. Replace the synthetic review receipt with an authenticated review workflow and add independent outcome verification. Do not let an LLM mutate graph status or permissions.
