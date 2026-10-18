# SecondAct

A pop-art creative planning app for artists working with limited resources. Choose filmmaking, theatre, photography or fashion design; describe an idea, materials, budget and dates; then get a Gemini plan grounded in a live FalkorDB inventory.

## Run locally

Requires Node.js 22.9+ and a reachable FalkorDB instance.

1. In the backend folder, run `npm ci --ignore-scripts`.
2. Copy `backend/.env.example` to `backend/.env` and supply your database connection, password and Gemini key. Never commit this private file.
3. Run `npm run seed` from the backend folder to create the fictional demo inventory.
4. Run `npm start` and open http://127.0.0.1:4318/.

`GEMINI_MODEL` is configurable. The fashion demo was verified with `gemini-3.5-flash-lite`; choose a model available to your API project. Manual inventory search works without a Gemini key. Cloud connectivity and available provider quota are required for their respective services.

## What works

- Curtain-and-spotlights intro, a crash zoom through the logo, and an immediate Skip button.
- Local profile creation with six portrait choices; edit or log out through the profile menu. Logging out restarts the intro and clears the local profile while retaining saved briefs.
- Four creative worlds with brief click animations, compact color-matched text hover effects, keyboard shortcuts and reduced-motion support. Each visit starts without a selected world.
- Project briefs saved on the device, smooth native-input caret movement and responsive layouts.
- Gemini chooses resource-search tools and uses graph results to produce production steps, costs, assumptions and unresolved needs.
- Direct resource searches with date, quantity, purpose and budget constraints, connected alternatives and equipment dependency checks.
- Expand **Why these choices?** to see the actual tool trace and resource paths.

## Why FalkorDB is central

FalkorDB stores resources, creative uses, owning clubs, materials, bookings and equipment requirements. Searches follow connected uses to find suitable resources and alternatives. A camera body is rejected as an available kit when its required lens is booked. The backend calculates stock throughout the requested dates and verifies the combined plan cost. If the graph is unavailable, inventory queries fail instead of substituting a hard-coded answer.

See [the graph data model](backend/GRAPH-MODEL.md), [the Cypher search queries](backend/search.mjs), and [backend setup and API details](backend/README.md).

## Try an example

**Fashion Designer:** title: Rajput Queen dress; vision: Indian Rajasthani period costumes with peacock motif.; resources: Fabric, design.; budget: ₹2,000; dates: 16–18 October 2026. Make a plan, inspect its resource checks, then search **Costumes and textiles** and **Sewing** for the same dates. AI wording and choices can vary.

**Photography:** use **Try a ₹500 portrait brief**, then generate a plan. Its October 25–27 dates demonstrate booked fabric and graph-connected alternatives. The manual **Try the backdrop demo** also exposes these availability checks without an AI call.

## Validation

Run from the backend folder:

```text
npm test                  # deterministic stock and plan-validation tests
npm run check:db          # read-only database connection check
npm run check:inventory   # live resource, alternative and dependency checks
npm run check:ai          # small Gemini generation check; consumes quota
npm run check:planner     # live Gemini + FalkorDB workflow; consumes quota
```

## Project layout

- `index.html`, `styles.css`: interface, responsive layout and animation.
- `app.js`: profiles, selection, brief persistence and manual inventory search.
- `planner.js`: submits and renders creative plans and graph evidence.
- `interactions.js`: input caret behavior and short selection-art animations.
- `intro-engine.js`, `intro.js`: stage choreography, playback and cleanup.
- `assets/`: six active image/brand assets only. See [asset notes](ASSETS.md).
- `backend/`: API server, database client, agent tools, graph seed, checks and tests. The lockfile is retained for reproducible installs.

Local recordings, the offline visual reference and archived design experiments belong in `extras/` and are excluded from Git. Credentials, installed dependencies and logs are also excluded.

## Prototype scope

Inventory, clubs and bookings are fictional. Profiles and briefs are stored in the browser; there is no production authentication, cloud project storage, persistent graph-based agent memory or real borrowing transaction. Plans check availability but do not reserve resources. Resource totals exclude unpriced needs such as travel, consumables and externally sourced embellishments. The backend sends the brief and relevant fictional inventory to Gemini, without the local profile. This is currently a local demo; a fresh checkout can run using the instructions above.
