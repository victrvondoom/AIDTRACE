# Dynamic UI changes, 2026-10-18

## Implemented

- Shared `useFetch` reads refresh every 30 seconds by default, on window focus and reconnection. Hidden/offline polling pauses; requests do not overlap within a mounted hook; stale dependency responses are ignored. Passing zero retains one-shot reads.
- Graph Lab (including hub fraud, cyber and evidence views) automatically recomputes after a 400 ms debounce when graph, engine or parameters change. Superseded analysis requests abort and cannot replace newer results. Site graph analysis refreshes every 30 seconds. Manual rerun remains available.
- Hub overview workspace names are actionable and summary loading/errors have visible states and retry.
- Source Library ignores stale README responses, handles export errors, and prevents repeated export clicks while busy.
- Supply Chain uses authenticated API fetching and refreshed evaluation data. Settlement, shortfall and alternate-route outcomes come from actual response fields instead of hardcoded strings. An embedded graph workspace supports scenario, site and pasted graph investigation.

## Verification

All commands ran in an isolated Docker Node 20 container using the repository lockfile.

- TypeScript: passed.
- ESLint on changed files: passed after correcting an effect-state update.
- Production build: passed, including TypeScript and route generation.
- Final targeted tests: 13 passed (shared refresh, reactive graph analysis, and MoC retry regression check).
- Full frontend suite was not clean: first run 381 passed, 3 failed, 1 skipped; repeated run 380 passed, 4 failed, 1 skipped. Three Overview failures report an existing incomplete API mock (`getFalkorHealth` absent); the additional MoC retry failure passed in the targeted rerun. No claim of repository-wide passing tests.
- Browser: current Graph Lab rendered on isolated port 3012 with error and retry controls. End-to-end live-data verification is incomplete: existing port 8000 does not expose these routes, and a separate backend without cloud credentials returns 503 for missing Supabase configuration. No cloud credentials were supplied and no cloud data was modified.

## Limits

These changes make existing data views reactive. They do not connect new production feeds, replace synthetic scenarios with production data, implement the outstanding agent runtime or migrate unported repositories. Consumer analysis and approvals remain explicit operations; polling does not automatically approve or submit actions. Integration status labels describe implementation coverage, not current service health.
