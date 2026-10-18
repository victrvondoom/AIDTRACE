# Frontend entry points found (2026-10-18)

| Root | Port seen | Status |
|---|---|---|
| `kairos-main/frontend` (Next.js) | 3000 (existing dev server) | **Canonical.** Only deliverable UI. |
| `track1-agent/frontend` (Next.js; `/`, `/consumer`, `/capabilities`) | 3000/3001 | Reference source. Consumer console ported to `features/resolveai/consumer-workspace.tsx`. Not started by Kairos. |
| `RESOLVE-AI-main/frontend` (108 files) | not running | Reference source. **Not ported.** |

Backends seen: `kairos-main/backend` (8000), `track1-agent/backend` (8000/8001). Ports collide when both start, which is the sprawl this work removes: Kairos now needs one web port and one private API port.
Not yet audited: hardcoded `localhost` links across the three trees (only the new code was checked).