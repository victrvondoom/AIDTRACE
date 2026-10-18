# Browser verification (2026-10-18)

Environment limits, stated plainly: this machine has no Supabase credentials, so the real authenticated Kairos API could not start for login. A throwaway harness (outside the repo) mounted the real routers on real FalkorDB with a synthetic engineer session; the real Next frontend ran in dev mode against it through the `/api` rewrite. `next build` failed offline (Google Fonts fetch), so the **production build is unverified**.

| Check | Result |
|---|---|
| One URL: 7 workspaces switched | Pathname stayed `/hub`; no iframes; no `window.open`; no error alerts |
| Same shell | Same sidebar, header and theme throughout |
| Real backend and graph | ResolveAI showed a live revision hash and "independent Cypher check agrees"; removing evidence changed the revision and the verdict reasons |
| Engine in browser | Cybersecurity preset ran min-cut: verified yes, cut cost 4; matrix view rendered |
| Not tested | Restart persistence, failure isolation, mobile, production build, repeated-switch leak check |