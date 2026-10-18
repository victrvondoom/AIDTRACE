# Kairos Evidence Drift API contract map

Source inspected read only in `kairos-main/backend/api` on 2026-10-18. Routes are mounted in `main.py` (`/auth`, `/resolveai`, and the drift router's own `/drift` prefix). This map describes code present at inspection time; a running service must still be verified separately.

| Route | Request | Response | Authentication / scope | Benchmark use |
|---|---|---|---|---|
| `GET /auth/me` | Bearer token | Verified user dict with `user_id`, `role`, `site_id` | `CurrentUserDep` | Verify explicit test identity; reject `admin`, `demo`, connector and dev-bypass users. |
| `GET /drift/health` | Bearer token | `{"reachable": bool, "site_graph_exists": bool}` | `CurrentUserDep`, engineer/reliability/admin; token site | Read-only preflight. |
| `POST /drift/nodes/{site_id}` | `{"label": Label, "node_id": str, "properties": object}` | `{"node_id": str, "label": str, "status": "created"}` | Staff role; `tenant.guard_site` and `site_scope(write=True)` | Only in gated disposable local test. Graph node upsert; **not evidence ingestion**. |
| `POST /drift/edges/{site_id}` | `{"source_label": Label, "source_id": str, "target_label": Label, "target_id": str, "relationship": Rel, "kind": "logical"/`"policy"`/`"context"`, "properties": object}` | `{"source_id": str, "target_id": str, "relationship": str, "status": "linked"}` | Same as nodes | Only in gated disposable local test. Edges point dependent to dependency. |
| `POST /drift/impact/{site_id}` | `{"changed_ids": [str]}` | `{"impacted": [{"node_id": str, "depth": int, "path": [str]}], "traversal_limited": false, "site_id": str}` | Staff role; site-scoped graph read | Actual dependent reachability only. No status mutation or unaffected list. HTTP 422 on traversal budget. |
| `POST /drift/impact/pure` | `{"changed_ids": [str]}` | List of impact paths | Staff role | Not fixture compatible: implementation sets `edges=[]`; request has no edge field. |
| `GET /resolveai/drift/demo` | Bearer token | Fixed synthetic case status map, decision head/revision, approval and session details | Staff role; token site | Read-only contract probe of **one fixed case**; cannot score 50 fixtures. |
| `POST /resolveai/drift/demo` | Optional `{"focus_level": "HYPERFOCUS", "input_modalities": ["DOCUMENT", "TEXT"]}` | Fixed synthetic supersession result including `impact_paths`, `decision_status`, `statuses`, `human_review`, `action_eligibility` | Staff role; token site; demo fenced to showcase | Hard-coded case only. Benchmark does not call it or treat it as arbitrary fixture evaluation. |
| `POST /documents/ingest` | Multipart `file`, `document_type`, optional `asset_id`, `source_system`, `authority_level`, `occurred_at` | HTTP 202 with vault `document_id` and `job_id` | Authenticated caller; asset/demo guards and authority cap | Separate document vault/Temporal ingestion, not a drift graph fixture loader. Not called. |
| `POST /documents/{document_id}/supersede` | JSON `{"new_document_id": str}` | `{"status": "superseded", "edges_closed": int, "blast_radius": object, "moc_required": bool, ...}` or HTTP 202 `pending_moc_approval` | Authenticated caller; document visibility guards; authority 1–3 requires reliability/admin and approved MoC | Changes Supabase/Neo4j/ES/Qdrant records. Not called: no isolated arbitrary fixture contract and no safe disposable vault configured. |

## Source contracts and boundaries

- `services/drift/model.py` defines `Label` values `Document`, `SourceVersion`, `Claim`, `Memory`, `Decision`, `DecisionRevision`, `Plan`, `ActionProposal`, `Approval`, etc. Traversal follows `SUPPORTED_BY`, `DERIVED_FROM`, `DEPENDS_ON` with edge kind `logical` or `policy`. Metadata relationships such as `SUPERSEDES` do not themselves propagate impact.
- `services/drift/store.py` selects `FALKORDB_GRAPH_PREFIX + "__" + site_id` (default prefix `kairos_drift` from `config.py`). `find_impacts` reads bounded, parameterized Cypher edges, then computes a deterministic dependent closure. `upsert_node` and `link` merge into that site's graph. The impact route returns potential dependents; its own docstring says callers should mark stale and re-evaluate.
- `services/drift/demo_workflow.py` contains `run_evidence_supersession`, `evaluate_conditions` use, stale memory setup, revision append, approval revision check, and action suspension for fixed `DEMO-DRIFT-*` IDs. There is no general authenticated evidence supersession/revision request schema for the 50 fixtures in these routes. There is no arbitrary decision-status, memory-status, or approval-status read route in the drift router.
- `dependencies.py` verifies the bearer token through Supabase Auth; role and site come from `app_metadata`. It also accepts an internal API key as an admin connector and can allow a dev user with no token when dev bypass is configured. This harness rejects those identities. `site_scope` pins engineer/reliability users to their assigned site; another real site is HTTP 403. The adapter never uses administrator credentials.
- `middleware/opa.py` also maps drift and ResolveAI sensitive reads to the `read_resolveai` policy action and enforces configured writes. Successful bearer verification alone does not guarantee policy permission; HTTP 403 remains an expected authorization result.
- Document ingestion/supersession is a separate vault/search workflow with real write side effects. It is outside this benchmark.

## What is scored

The compatible subset translates fixture evidence to `SourceVersion`, a synthetic `Claim` supported by it, and dependent `Decision`/`Memory` nodes. `POST /drift/impact/{site_id}` then measures direct and transitive **impact reachability** against fixture decision IDs. Unaffected decisions are inferred from the fixture's complete local decision set minus returned impacted IDs; the API does not return them separately. Duplicate path entries are deduplicated after schema validation.

Independent support, authority conflict, irrelevant-change materiality, arbitrary approval revalidation, and current memory/decision validity have no comparable generic route. Cross-site authorization can be checked only with a separate site-bound test identity. The fixed ResolveAI demo proves only its own hard-coded case and is excluded from fixture metrics. No API outcome is inferred from the direct FalkorDB result.

## Live-write preconditions

Default comparison performs fixture/contract validation and no Kairos write. Authenticated dry-run performs `GET /auth/me` and `GET /drift/health` only. Live fixture loading requires explicit `--execute-local-test`, `--dedicated-local-test`, `KAIROS_BENCH_DEDICATED_LOCAL_TEST=YES`, a loopback API origin, a bearer token for a non-admin engineer/reliability identity assigned an `EDB_BENCH_` site, the exact local FalkorDB URL and graph prefix configured in that API, and an empty dedicated graph store. The runner deletes only its known graph created during that run. It never deletes unknown graphs.
