# Single-origin API gateway

Browser calls go to `/api/*` on the Kairos origin. `next.config.ts` forwards them to `API_INTERNAL_URL` (default `http://localhost:8000`). Verified: `GET http://localhost:3010/api/graphlab/scenarios` returned the scenario list through the rewrite.
Settings: `NEXT_PUBLIC_API_URL=/api`, `API_INTERNAL_URL=http://localhost:<private api port>`, `CORS_ORIGINS` only needs the web origin. An absolute `NEXT_PUBLIC_API_URL` still works unchanged. Not changed: the Caddy edge in `docker-compose.yml`.