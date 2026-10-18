# ResolveAI integration inventory

## Product boundary

Kairos remains the canonical product and owns the user experience, authentication, permissions, governance, workflows, and deployment. ResolveAI is a candidate investigative intelligence subsystem. Its capabilities must be exposed through Kairos's existing interfaces and controls; it must not introduce a second user-facing application identity.

## Source review

| Capability | Source location | Observed implementation | Destination | Decision |
|---|---|---|---|---|
| Kairos application and UX | `kairos-main/frontend`, `kairos-main/backend/api` | Next.js application with role-aware shell; FastAPI API with OPA, tenant and demo fences | Remains canonical | KEEP |
| Kairos temporal graph | `kairos-main/backend/api/services/graph.py`, `backend/api/dependencies.py` | Neo4j-backed industrial asset/document knowledge graph | Retain as canonical graph until a separately reviewed migration | KEEP |
| ResolveAI case workflow | `RESOLVE-AI-main/backend/app/agents/orchestrator/case_workflow.py` | Multi-step consumer case investigation and review workflow | Potential internal intelligence adapter after authorization and contract mapping | DEFER |
| ResolveAI multi-domain workflow | `RESOLVE-AI-main/backend/app/agents/orchestrator/multi_domain_workflow.py` | Concurrent domain fan-out, per-domain workflow runs and merged reports | Potential capability behind Kairos API and UI | DEFER |
| ResolveAI domain router | `RESOLVE-AI-main/backend/app/agents/role_agents/domain_router.py` | Domain candidate classification | Potential investigative routing capability | DEFER |
| ResolveAI case persistence/auth | `RESOLVE-AI-main/backend/app/database`, `backend/app/core` | Separate case persistence and authentication/configuration | Kairos contracts would be required; no second shell or auth authority | ISOLATE |
| ResolveAI graph and vector adapters | `RESOLVE-AI-main/backend/app` (graph, indexing, retrieval services) | Separate graph/vector integration paths | No cross-store migration until schema, tenancy and cloud-write plan is approved | DEFER |

## Licensing and provenance gate

No `LICENSE` or `NOTICE` file was found in the ResolveAI checkout, including its frontend. Its README credits the author but does not state reuse terms. On 2026-10-17, the user explicitly confirmed that full permission has already been granted and directed implementation to proceed. Work may proceed under that authorization; preserve source attribution and keep the written grant with project records before distributing combined artifacts. No ResolveAI source code has been copied in the current implementation slice.

Kairos has its own proprietary license. Any distribution of the combined product must preserve Kairos ownership notices and follow the user's ResolveAI authorization and attribution terms.

## Integration conflicts

| Area | Kairos | ResolveAI | Resolution |
|---|---|---|---|
| Product identity | Kairos industrial intelligence | ResolveAI consumer justice | Keep Kairos identity; present any authorized capability as a Kairos workflow |
| Authentication and authorization | Kairos roles, OPA middleware, tenant/site scope | Independent app auth and user scope | Kairos must remain the single authority; map identity only after a reviewed contract |
| Domain model | Assets, sites, documents, operational events | Citizens, cases, institutions, regulatory domains | Keep domain models bounded; add an explicit adapter only for an approved use case |
| Graph and retrieval | Neo4j, Qdrant, Elasticsearch | Neo4j, Qdrant, separate schemas/config | No indiscriminate merging or live-store writes; define ownership and tenant boundaries first |
| Runtime/API | Kairos FastAPI routes | Separate FastAPI API and frontend | Integrate as an internal module or separately governed service; never mount a second product shell |

## Recommended next gate

1. Keep the user's authorization associated with the exact code, assets and data selected for reuse.
2. Select one narrowly defined investigative use case that fits Kairos users and operating context.
3. Specify Kairos-owned request, response, identity, tenant and provenance contracts before implementation.
4. Build an isolated adapter and tests without touching cloud stores; preserve Kairos's existing routes and UI.
5. Evaluate FalkorDB as an additional graph infrastructure only after local compatibility and migration assessment. Kairos currently uses Neo4j as its graph of record; no production migration is authorized or implemented.

No ResolveAI source code has been copied or modified as part of this inventory.
