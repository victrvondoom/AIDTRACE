# Evidence Drift engine comparison

Generated from actual report data at 2026-10-18T04:39:27.722787+00:00. Direct FalkorDB: **PASS**. Kairos API: **BLOCKED**.

| Metric | Direct FalkorDB benchmark | Kairos actual API |
|---|---:|---:|
| Scenarios executed | 50 | 0 |
| Correct invalidations / impact candidates | 52 | — |
| Missed invalidations / impact candidates | 0 | — |
| False invalidations / impact candidates | 0 | — |
| Precision | 1.0000 | — |
| Recall | 1.0000 | — |
| p95 latency (ms) | 5.8080 | — |
| Memory validity | 50/50 | — |
| Tenant isolation | PASS (3/3) | NOT_RUN |

31 of 50 fixtures have a generic impact mapping. Kairos impact results are dependent reachability, not persisted decision invalidation. Memory and approval validity are unavailable for arbitrary fixtures.

API run detail: A dedicated local Kairos API origin, site-bound test token, EDB_BENCH_ site, and disposable graph store were not configured.
