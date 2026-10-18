# Test evidence (2026-10-18)

Environment: Windows, Python 3.12, FalkorDB at 127.0.0.1:6380. Dependencies the project pins but this machine lacked were installed to a temp folder, not globally.

| Command | Result |
|---|---|
| `scripts/verify-kairos.ps1` backend set: graphlab, sources, consumer, greenchain (+54 original), fraud (+11 original), resolveai_platform, drift, authz boundary, tenant isolation | **297 passed** |
| `npx tsc --noEmit` (frontend) | clean |
| `npx eslint` on new frontend code | clean |
| `ruff` on new Python | clean except style notes in copied original fraud modules |
| `npx vitest run` | 379 passed, 3 failed: `overview/page.test.tsx` (missing `getFalkorHealth` mock from other in-progress work, not this change) |
| `tests/test_drift.py` | 3 failures that predate this work (stale expectations against the unchanged engine) |
| Browser (real Next frontend, real routers, real FalkorDB, synthetic session) | pathname stayed `/hub` across all workspaces; GreenChain scoring, transport, server verification, what-if, FalkorDB save; fraud trace and approval; platform shown NOT_CONNECTED; min-cut verified |

**Not run:** production build (`next build` fails offline fetching Google Fonts); login against a real Supabase session; restart persistence; mobile; failure isolation; the RESOLVE-AI-main worker; live provider calls; a clean-machine run of `start-kairos.ps1`.