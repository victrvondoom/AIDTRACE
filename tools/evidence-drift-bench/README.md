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
- Optional Kairos Evidence Drift API evaluation.

Fixture and FalkorDB traversal correctness do not establish that Kairos's production engine was evaluated. A Kairos API result is produced only when `--kairos-api-url` is explicitly configured.

## Optional Kairos API adapter

The generic HTTP JSON adapter sends each scenario's graph and evidence inputs without its expected results. It accepts an explicitly supplied endpoint with this response contract:

```json
{
  "affected_decisions": ["scenario-001:decision:primary"],
  "memory_valid": false
}
```

Run it with `--kairos-api-url https://test-host.example/evidence-drift/evaluate`. If the endpoint needs bearer authentication, set `KAIROS_BENCH_BEARER_TOKEN` in the environment. The adapter does not assume a Kairos route or alter application code.

## Report interpretation

`PASS`, `FAIL`, and `BLOCKED` are distinct. A blocked/unavailable database produces no FalkorDB pass or graph measurements. Latency values are measured per run and can vary with the test host; the fixture seed, scenario IDs, and graph topology are reproducible. Kairos API evaluation is reported separately from the local graph traversal.
