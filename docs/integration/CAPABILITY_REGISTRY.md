# Kairos capability registry

The registry must distinguish callable behavior from route discovery and roadmap entries. A page, source repository, health check or workflow preview alone does not establish an integrated engine.

| Capability | Product boundary | Current state | Evidence |
|---|---|---|---|
| Asset and document operations | Kairos | Existing application workflows | Existing routes and API modules |
| ResolveAI orchestration | Kairos internal subsystem | Kairos-native synthetic investigation flow is callable; standalone ResolveAI specialist runtime is not yet called by Kairos | RESOLVEAI_INVENTORY.md; backend/api/routers/resolveai.py |
| FalkorDB dependency graph | Kairos | Site-scoped graph persists the synthetic evidence, agent memory, decision revisions, review receipt, action state and audit record | EVIDENCE_DRIFT_ARCHITECTURE.md; backend/api/services/drift/store.py |
| Evidence impact traversal | Kairos | Deterministic bounded traversal over persisted graph relationships | backend/api/services/drift/engine.py |
| CausalLatch condition evaluation | Kairos | Typed precondition and authority algorithms; demo invokes them on synthetic evidence | backend/api/services/drift/model.py |
| Agent memory propagation | Kairos | Two persisted agent/session records demonstrate a synthetic memory handoff; production agent runtime, live case ingestion and real multimodal processing are not connected | backend/api/services/drift/demo_workflow.py |
| Decision revision lineage | Kairos | Compare-and-set append of immutable decision revisions; each revision stores a SHA-256 graph dependency digest | backend/api/services/drift/store.py; backend/api/services/drift/demo_workflow.py |
| Revision-bound human review | Kairos | Review receipt remains pinned to its reviewed graph revision; mismatch blocks the dependent demo action | backend/api/services/drift/demo_workflow.py; backend/tests/test_drift_store.py |
| Agent focus trace | Kairos | Deterministic Broad, Targeted and Hyperfocus plans keep the bounded safety traversal complete and change investigation emphasis. UI maps document/image OCR, Work Order voice, operational event and video readiness; separate Kairos pipelines are not attached to the ResolveAI demo case. This is not an active agent runtime | backend/api/services/drift/model.py; backend/api/services/drift/demo_workflow.py; frontend/src/app/(app)/resolveai/_components/drift-demo-panel.tsx |
| Cyber / fraud investigation | Kairos | Frontend workflow preview; no detection model or production case engine integrated. Beyondions root-cause agent reviewed as reference-only pending a bounded Kairos tool-trace adapter | frontend/src/app/(app)/resolveai/page.tsx; SOURCE_PROVENANCE.md |
| Fine-tuning | Kairos | Not connected in this deployment | /health/model-catalog response |
| 98-source capability packs | Kairos | 71 source records (70 implementation audits and one verified empty upstream); First Domino's revision-bound review behavior adapted and tested; Beyondions reviewed as reference-only; 68 other audited leads and 27 unaudited leads remain pending | INTEGRATION_QUEUE.json; SOURCE_PROVENANCE.md |

Update this registry only when a route demonstrably invokes the capability and its behavior has relevant test evidence.
