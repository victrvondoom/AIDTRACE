# Blood Network: Graph Coordinator (Graph Hacks)

New Graph Hacks work started on 15 October 2026. Proposed track: Agents That Act on Connected Data.

This is a separate, synthetic-only improvement to Blood Network, not a production medical service. It does not import the original app's donor list, medical uploads, contact details or requests. Fictional token IDs only. No messages are sent. Group equality and `demoEligible` are demonstration rules, not clinical compatibility or medical clearance.

## What the graph does

A bounded rule-driven agent reads connected requests, facilities and donors. It atomically chooses a demo donor and records a simulated contact. Pending contact blocks further action. A fictional acceptance marks the request coordinated and stops. Under the escalation rule chosen by the participant on 17 October 2026 (variant C), the agent is limited to the request's own facility (maximum 1 hop): referral edges exist in the model but are never followed, so after a decline with no other eligible donor at that facility the agent stops instead of escalating. The alternative rules (follow referrals, no referral route, second donor unavailable) remain as selectable variants in `variants/`. The path length and facility are returned as the explanation. The next session reads graph-stored attempt history. There is no matching fallback if FalkorDB is unavailable.

Status, 17 October: unit tests and the actual FalkorDB integration test pass; the mobile demo UI is built and endpoint-tested; the demo video is recorded (docs/graph-hacks-demo-final.mp4, 36 s, shows the participant-chosen facility-limited rule); the participant walkthrough is complete and his contribution is recorded below. Published and submitted to Graph Hacks on 17 October 2026 with the participant's explicit approval. Amar's verification and contribution are still required.

## Graph model

- `Request {id, synthetic, status}` -> `NEEDS` -> `DemoGroup {id}`
- `Request` -> `AT` -> `Facility {id, label, synthetic}`
- `Facility` -> `REFERS_TO` -> `Facility`
- `Donor {id, synthetic, available, demoEligible}` -> `AVAILABLE_AT` -> `Facility`
- `Donor` -> `HAS_GROUP` -> `DemoGroup`
- `Request` -> `ATTEMPTED {outcome, facility, hops}` -> `Donor`

`queries/next-action.cypher` is the multi-hop selection plus action-memory write. `queries/outcome.cypher` records a simulated reply. `queries/history.cypher` reads persisted memory. Inputs are fixed fixture IDs and allowlisted outcomes, passed as parameters. There is no free-form Cypher or personal-data ingestion endpoint.

## Run locally

Docker route: requires Docker and Node 22+. The commands below are documented setup; this draft was tested through the embedded route further below, not Docker. Run from this directory. Never expose the unauthenticated demo database outside localhost.

```sh
docker run --name blood-graph-demo --rm -p 127.0.0.1:6379:6379 falkordb/falkordb:latest
# In a second terminal:
npm ci
FALKORDB_URL=falkor://127.0.0.1:6379 npm run demo
npm test
FALKORDB_TEST_URL=falkor://127.0.0.1:6379 npm run test:integration
```

The database container above is intentionally temporary. Restarting the app, not the container, preserves graph history. A persistent production deployment needs database volumes, authentication, backups and a separate review. The integration test deletes only its dedicated `blood_network_synthetic_test` graph and refuses nonlocal hosts. The demo uses `blood_network_synthetic_graph_hacks` and its seed does not delete attempt history. Restart the temporary container for a clean demonstration.

Expected fresh-instance story: donor 1 at facility A is selected; a simulated decline is recorded; donor 2 at referral facility B is selected; blocked and different-group donors are never selected. A pending outcome prevents another contact. Run the integration test to verify acceptance stops further actions.

## Mobile demo UI

`npm run db` starts a real local FalkorDB through FalkorDBLite (loopback only, synthetic data), and `npm run ui` serves a phone-friendly page at http://127.0.0.1:3000 (localhost only). The page shows the fixture graph, then drives the same coordinator: seed, next action, simulated decline/accept, graph memory, and a simulated-outage switch that shows the fail-closed stop. It was endpoint-tested against the real server on 16 October: first selection donor 1 (1 hop), pending-contact stop, decline -> donor 2 through the referral edge (2 hops), outage returns the fail-closed error, accept stops coordination, and history reads back both attempts.

## Testing status, 16 October

- 9 unit tests passed (adapter/validation/outage behavior, using explicit test doubles).
- 13 original app tests passed, unchanged.
- 1 actual FalkorDB integration test passed, 0 skipped, through FalkorDBLite 0.3.0 with native Redis 8.10.2. After the 17 October rule choice it verifies facility-limited selection (referral never followed), pending-action stop, exclusions, attempt memory and outcome immutability.
- npm audit: zero findings at initial install.
- UI endpoints verified against real FalkorDB through the embedded route (see "Mobile demo UI").
- Repository made public and submitted to Graph Hacks on 17 October 2026 with the participant's explicit approval.

## Limits

Demo only; one fixed request, two candidate donors, one facility under the chosen rule. No LLM, clinical matching, real contacts, authentication UI or high-concurrency claims. Graph query execution and action sequencing are verified on a real local server; production concurrency and recovery are not. Outage behavior has adapter unit coverage, but a live outage demonstration is still needed. The ordinary Cloudinary app remains an earlier project and is not the Graph Hacks submission; only this new graph coordinator and its later additions should be judged.

## AI-use and participant contribution

AI assistance (Instinct) was used to prepare the graph model, adapter, queries, tests and demo UI. Amarjith Sah proposed Blood Network and selected it as the project to improve.

Walkthrough completed 17 October 2026 (~1:50 AM IST, WhatsApp voice notes). Before seeing the demo run, he correctly predicted all three behaviors in his own words: (1) demo-donor-1 at facility A is selected first, (2) a decline makes the agent follow the referral to donor-2 at facility B, (3) a pending reply means no second donor is contacted - no duplicates, wait per policy. He then observed the live graph-backed run and compared it against his predictions. His chosen escalation rule (variant C, max 1 hop - never follow referrals), in his own words: "Agent sirf apni facility tak limited choose karunga. Kyun? Agent Facility A se bahar referral follow nahi karega. Donor-1 decline karega toh agent ruk jayega. Donor-2 Facility B par available hone ke baad bhi contact nahi hoga. Isse hum test kar sakte hain ki graph traversal aur facility-level restrictions ka behavior kaise change hota hai." The variant was applied, re-verified against a real FalkorDB server (updated integration test passes), and he was shown the changed behavior for confirmation.

## Sources

- Rules: https://www.wemakedevs.org/hackathons/falkordb/rules
- Brief: https://www.wemakedevs.org/hackathons/falkordb
- Node client: https://github.com/falkordb/falkordb-ts
- Setup: https://docs.falkordb.com/getting-started/
- Parameterized queries: https://docs.falkordb.com/commands/graph.query

## Verified no-Docker integration route

On Linux x64 / Node 22, the official `falkordblite` development dependency starts the actual FalkorDB module, not a mocked query engine. The npm package may still require a local `redis-server` binary: its optional prebuilt Redis dependency was unavailable during this run. With Redis available on PATH:

```sh
npm ci
npm run test:embedded
```

Or provide a compiled Redis binary without installing anything globally:

```sh
REDIS_SERVER_PATH=/absolute/path/to/redis-server npm run test:embedded
```

The test wrapper binds TCP only to 127.0.0.1:16379, runs the existing real-server test, and closes the server in a finally block. Keep that port unused. It uses disposable synthetic graphs, not the original app database. This is a development/test route, not a multi-user production deployment.

Native build used: official stable source from https://download.redis.io/redis-stable.tar.gz, reporting Redis 8.10.2. The top-level aggregate build produced the core binary but failed on unrelated bundled search/JSON/timeseries modules. Core-only `make -C src -j2 MALLOC=libc OPT=-O2 redis-server` completed successfully. No root install was needed. FalkorDBLite supplied its own FalkorDB module. Record and pin a supported server/module combination before broader release.

Setup sources: https://docs.falkordb.com/operations/falkordblite/falkordblite-ts.html and https://redis.io/docs/latest/operate/oss_and_stack/install/archive/install-redis/install-redis-from-source/ .
