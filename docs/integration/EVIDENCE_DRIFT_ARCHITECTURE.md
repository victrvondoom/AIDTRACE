# Evidence Drift Cascade: implementation boundary

## Current flow

1. Kairos verifies role and derives the caller site from the authenticated user. The public demo is hard-bound to the showcase site and its synthetic asset ID.
2. The synthetic integration journey records document/source versions, claims, an agent-memory node, decision, plan, proposed action and audit event in the site's FalkorDB graph.
3. A higher-authority verified source supersedes an earlier source and extracted claim.
4. The bounded deterministic reverse-dependency traversal identifies only linked claims, memories, decisions, plans and actions.
5. CausalLatch re-evaluates a typed decision precondition against the newer claim.
6. The synthetic action is suspended and an audit-chain hash is stored. No external action is executed.

## Limits

The current scenario is deterministic and synthetic. It does not ingest a real source document, invoke a ResolveAI language model or specialist, import Track 1 code, suspend a real action, or provide production recovery/retention guarantees. Its fixed IDs and source observations make the scenario idempotent inside a site graph. A separate synthetic prefix keeps it apart from operational records.

## Next integration gate

Add a document-authorized ingestion contract with source hash/version, authority evidence and idempotency receipt; then connect a bounded ResolveAI investigation adapter that can only return cited claims and cannot set final verification or authorize action. Follow with human approval and independent outcome verification. Do not let an LLM mutate graph status or permissions.
