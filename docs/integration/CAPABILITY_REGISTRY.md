# Kairos capability registry

The registry must distinguish callable behavior from route discovery and roadmap entries. A page, source repository, health check or workflow preview alone does not establish an integrated engine.

| Capability | Product boundary | Current state | Evidence |
|---|---|---|---|
| Asset and document operations | Kairos | Existing application workflows | Existing routes and API modules |
| ResolveAI orchestration | Kairos internal subsystem | Source reviewed; its case workflows are consumer/insurance domain-specific and are not yet called by Kairos | RESOLVEAI_INVENTORY.md |
| FalkorDB dependency graph | Kairos | Site-scoped graph adapter; local synthetic evidence path added in this workstream | EVIDENCE_DRIFT_ARCHITECTURE.md |
| Evidence impact traversal | Kairos | Deterministic bounded traversal over persisted graph relationships | backend/api/services/drift/engine.py |
| CausalLatch condition evaluation | Kairos | Typed precondition and authority algorithms; demo invokes them on synthetic evidence | backend/api/services/drift/model.py |
| Agent memory propagation | Kairos | Synthetic graph demonstration only; production agent runtime and live case ingestion are not connected | backend/api/services/drift/demo_workflow.py |
| Cyber / fraud investigation | Kairos | Frontend workflow preview; no detection model or production case engine integrated | frontend/src/app/(app)/resolveai/page.tsx |
| Fine-tuning | Kairos | Not connected in this deployment | /health/model-catalog response |
| 98-source capability packs | Kairos | Source-audit queue exists; integration review is incomplete | INTEGRATION_QUEUE.json |

Update this registry only when a route demonstrably invokes the capability and its behavior has relevant test evidence.
