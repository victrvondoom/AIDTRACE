# Real Kairos API comparison

Generated from actual report data at 2026-10-18T05:49:23.578130+00:00. Direct FalkorDB: **PASS**. Kairos API: **PASSED**.

| Metric | Direct FalkorDB benchmark | Kairos actual API |
|---|---:|---:|
| Scenarios executed | 50 | 31 |
| Correct impacts | 52 | 40 |
| Missed impacts | 0 | 0 |
| False impacts | 0 | 0 |
| Precision | 1.0000 | 1.0000 |
| Recall | 1.0000 | 1.0000 |
| Mean latency (ms) | 7.3051 | 11.4288 |
| p95 latency (ms) | 10.0290 | 13.5793 |
| Memory validity | 50/50 | — |
| Tenant isolation | PASS (3/3) | PASSED |

31 of 50 fixtures have a generic impact mapping. Kairos impact results are dependent reachability, not persisted decision invalidation. Memory and approval validity are unavailable for arbitrary fixtures.

API run detail: Actual Kairos drift router/store/engine impact reachability only; no decision, memory, or approval validity evaluation.
Authorization scope: router site_scope with in-process test identity; Supabase JWT and OPA middleware not evaluated.
