# Unified Kairos architecture

One user-facing app: `kairos-main/frontend` (Next.js). One API entry point: `kairos-main/backend/api` (FastAPI).

- **Feature host**: `frontend/src/features/feature-host.tsx`, rendered at `/hub`. A registry of workspaces (overview, ResolveAI, fraud, cybersecurity, evidence drift and memory, graph explorer, capability workbench). Switching is React state; the pathname stays `/hub`. Each workspace is lazy-loaded and wrapped in an error boundary, so one failing workspace cannot take down the shell.
- **Shared engines**: `backend/api/services/graphlab` (10 deterministic graph engines), `backend/api/services/consumer` (ResolveAI consumer-remedy engine ported from track1-agent), `backend/api/services/drift` (Evidence Drift store). All use the one FalkorDB (`FALKORDB_URL`).
- **Routers**: `/graphlab/*`, `/sources/*`, `/resolveai/consumer/*`, `/resolveai/drift/*`, `/drift/*`. Same session, role gates (`engineer|reliability|admin`), OPA action `read_resolveai`, demo-fence entries in `services/tenant.py`.
- **Tenancy**: consumer graphs are named `resolve_consumer_<site>`; the site is derived from the token, never from the request. Approver identity is the authenticated user.
- **Same-origin gateway**: `frontend/next.config.ts` rewrites `/api/*` to `API_INTERNAL_URL`. Set `NEXT_PUBLIC_API_URL=/api`. Production already has the Caddy edge in `docker-compose.yml`.
- **Launch**: `scripts/start-kairos.ps1` prints one URL.