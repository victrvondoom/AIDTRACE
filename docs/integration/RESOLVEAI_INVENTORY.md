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

The ResolveAI root contains no `LICENSE` file. The repository README credits its author, and the frontend contains `LICENSE_PROPRIETARY.md`, which states all rights reserved and prohibits copying, modification, and derivative works without prior written permission. Treat source reuse as **not authorized** unless the owner grants written permission covering the intended integration and redistribution. Do not copy source code, prompts, corpus files, or assets into Kairos before that review. A clean-room adapter built from independently specified behavior can be considered separately, with provenance recorded.

Kairos includes a proprietary license as well. Any distribution of the combined product must preserve both projects' ownership notices and comply with both licenses; this inventory does not grant rights to either codebase.

## Integration conflicts

| Area | Kairos | ResolveAI | Resolution |
|---|---|---|---|
| Product identity | Kairos industrial intelligence | ResolveAI consumer justice | Keep Kairos identity; present any authorized capability as a Kairos workflow |
| Authentication and authorization | Kairos roles, OPA middleware, tenant/site scope | Independent app auth and user scope | Kairos must remain the single authority; map identity only after a reviewed contract |
| Domain model | Assets, sites, documents, operational events | Citizens, cases, institutions, regulatory domains | Keep domain models bounded; add an explicit adapter only for an approved use case |
| Graph and retrieval | Neo4j, Qdrant, Elasticsearch | Neo4j, Qdrant, separate schemas/config | No indiscriminate merging or live-store writes; define ownership and tenant boundaries first |
| Runtime/API | Kairos FastAPI routes | Separate FastAPI API and frontend | Integrate as an internal module or separately governed service; never mount a second product shell |

## Recommended next gate

1. Obtain written authorization for the exact ResolveAI code/assets/data intended for reuse.
2. Select one narrowly defined investigative use case that fits Kairos users and operating context.
3. Specify Kairos-owned request, response, identity, tenant and provenance contracts before implementation.
4. Build an isolated adapter and tests without touching cloud stores; preserve Kairos's existing routes and UI.
5. Evaluate FalkorDB as an optional graph infrastructure change only after a local compatibility and migration assessment. Kairos currently uses Neo4j and the ResolveAI plan does not authorize a production migration.

No ResolveAI source code has been copied or modified as part of this inventory.
