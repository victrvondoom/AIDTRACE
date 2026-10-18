# Evidence Drift Benchmark Laboratory

Standalone, deterministic fixtures and a FalkorDB traversal harness for testing evidence-to-decision dependency invalidation. It does not import or modify Kairos application code. Every database run creates a new graph whose name begins with `EDB_TEST_`, refuses to reuse an existing graph, and deletes its graph when the run finishes unless `--keep-graph` is set.

## Install and run

From this directory, install the isolated dependencies and generate the fixed 50-scenario fixture set:

```powershell
python -m pip install -r requirements.txt
python generate_fixtures.py --seed 98 --count 50
```

Run the fixtures against a dedicated local FalkorDB test instance:

```powershell
python benchmark.py --falkordb-url redis://127.0.0.1:6379
```

To regenerate and run in one command:

```powershell
python benchmark.py --regenerate-fixtures --seed 98 --count 50 --falkordb-url redis://127.0.0.1:6379
```

The benchmark writes `reports/benchmark-latest.json`. Run unit and configured integration tests with:

```powershell
$env:FALKORDB_URL = 'redis://127.0.0.1:6379'
python -m pytest tests -q
```

The FalkorDB integration test skips when `FALKORDB_URL` is unset. It refuses non-loopback URLs. The command line also blocks remote URLs unless `--allow-remote-test-db` is supplied for a dedicated remote test instance. The graph prefix and existing-graph check apply in either mode.

If no test server is configured, fixture/oracle validation still runs and the report marks FalkorDB `BLOCKED`; database metrics remain null or absent. The process exits with code 2 so a blocked graph run cannot be mistaken for a successful FalkorDB benchmark.

## Scenario coverage

The default seed produces 50 scenarios across supplier evidence supersession, emissions estimate aging, supplier relationship changes, cybersecurity evidence, agent memory recall and staleness, direct and multi-hop decision invalidation, independent support, irrelevant updates, cycles, duplicate events, conflicting sources, cross-tenant isolation, and approval invalidation.

Each fixture carries tenant and scenario graph nodes, directed relationships, original and updated evidence, update events, explicit expected affected and unaffected decision IDs, expected memory validity, and a plain-language explanation. `generate_fixtures.py` uses a per-scenario seed derived from the base seed, so the JSON stays stable for the same seed and count.

## What the benchmark measures

The harness loads parameterized Cypher into its isolated graph. It traverses source evidence through `SUPPORTS`, `DEPENDS_ON`, `APPROVES`, and `DESCRIBES` relationships up to 12 hops, subtracts decisions that retain current independent support, adds directly challenged conclusions, and checks memory nodes sourced from invalidated evidence. Queries scope both source and returned decisions through tenant ownership.

The JSON report separates:

- Independent Python fixture traversal validation against the explicit scenario oracle.
- Actual FalkorDB decision precision/recall, correctly identified impacts, missed and false invalidations, graph counts, and traversal latency.
- Actual memory validity, duplicate event replay stability, and cross-tenant isolation.
- Source-verified Kairos API reachability evaluation, only through `compare_engines.py`.

Fixture and FalkorDB traversal correctness do not establish that Kairos's production engine was evaluated. `benchmark.py` records Kairos as `NOT_RUN`. The comparison tool reports it separately.

## Compare with the actual Kairos API

`kairos_contracts.md` maps the routes found in Kairos source. The generic `/drift/impact/{site_id}` route reports dependent reachability. It does not mutate decision validity or expose arbitrary memory/approval validity. A hard-coded ResolveAI demo exists, but cannot accept these 50 fixtures. The comparison reports unsupported semantics instead of treating graph reachability as a full evidence-change outcome.

### Real in-process API run

The preferred runner mounts Kairos's unchanged `backend/api/routers/drift.py` in memory. It overrides only settings and the test identity dependency; the identity is an in-process bearer-token-gated, non-admin engineer assigned to a fresh `EDB_BENCH_` site. The handler calls Kairos's real FalkorDB store and impact engine. The runner never opens a listening port or calls the applications already running on ports 3000/8000. It requires a local FalkorDB test instance and creates a fresh `EDB_BENCH_` graph, verifies it did not exist, and deletes only that graph.

From this directory on Windows, create an isolated Python 3.12 environment and run the full suite plus live API measurement:

```powershell
uv venv --python 3.12 .venv
uv pip install --system-certs --python .venv\Scripts\python.exe -r requirements-isolated-api.txt
$env:FALKORDB_URL = 'redis://127.0.0.1:6379'
.venv\Scripts\python.exe -B -m pytest -p no:cacheprovider tests -q
.venv\Scripts\python.exe -B run_isolated_api.py --falkordb-url redis://127.0.0.1:6379
```

The run writes `reports/kairos-api-live-results.json`, updates `reports/kairos-api-evaluation.json`, and writes `reports/real-api-comparison.md`. Each scenario records its expected and actual decision impacts, HTTP status, latency, TP/FP/FN, precision, recall, and repeat consistency. The source file hashes, graph counts, cleanup state, and route probes are included. The previously measured direct FalkorDB result comes from `reports/benchmark-latest.json`; it is never copied into the API column.

The live run on the inspected source executed **31/31 compatible fixtures**. The other 19 remain `UNSUPPORTED`. `/drift/impact/pure` is shadowed by the earlier `/drift/impact/{site_id}` route in the current router and cannot accept fixture edges. The in-process identity tests route-level 401 and site-scope 403 behavior; it does not test Supabase JWT verification or OPA middleware. Generic graph upsert replay is tested for duplicate fixtures, but evidence-event idempotency, supersession, memory validity, decision validity, and approval validity remain outside the available generic route.

### Authenticated external API mode

Run direct FalkorDB afresh and generate the comparative reports. Without a configured API this runs fixture/contract validation and marks Kairos `BLOCKED` with null metrics:

```powershell
python compare_engines.py --run-direct --falkordb-url redis://127.0.0.1:6379
```

Authenticated read-only preflight requires a pre-provisioned, site-bound engineer or reliability test identity. Provide its bearer token through an environment variable; the tool never prints it:

```powershell
$env:KAIROS_BENCH_TEST_TOKEN = '<test bearer token>'
python compare_engines.py --api-base-url http://127.0.0.1:8000 --api-site-id EDB_BENCH_LOCAL01
```

Write-based API evaluation additionally requires a **dedicated local** Kairos instance configured to use an empty disposable FalkorDB and a test identity assigned to the named `EDB_BENCH_` site. Set the actual API graph prefix and exact FalkorDB URL; the runner refuses any existing graph and deletes only the graph it created:

```powershell
$env:KAIROS_BENCH_DEDICATED_LOCAL_TEST = 'YES'
python compare_engines.py --run-direct --falkordb-url redis://127.0.0.1:6379 `
  --api-base-url http://127.0.0.1:8000 --api-site-id EDB_BENCH_LOCAL01 `
  --execute-local-test --dedicated-local-test `
  --api-falkordb-url redis://127.0.0.1:6380 --api-graph-prefix kairos_drift
```

Use a second site-bound test bearer token in `KAIROS_BENCH_FOREIGN_TEST_TOKEN` to test HTTP 403 cross-site isolation. The dedicated Kairos graph store should be separate from the direct benchmark store. Outputs are `reports/kairos-api-evaluation.json` and `reports/comparison.md`; `reports/benchmark-latest.json` remains the direct benchmark measurement. API latency is HTTP request time, while the direct column is graph query/traversal time.

The former generic `HttpJsonEvidenceDriftAdapter` remains as an extension point for a separately defined future JSON API. It is not Kairos's current route contract and is not invoked by either benchmark command.

## Report interpretation

`PASS`, `FAIL`, and `BLOCKED` are distinct. A blocked/unavailable database produces no FalkorDB pass or graph measurements. Latency values are measured per run and can vary with the test host; the fixture seed, scenario IDs, and graph topology are reproducible. Kairos API evaluation is reported separately from the local graph traversal.
