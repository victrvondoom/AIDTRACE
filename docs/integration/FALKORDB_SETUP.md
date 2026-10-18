# FalkorDB in Kairos

Kairos uses the official Python FalkorDB client (`backend/requirements.txt`) through its existing graph adapters. The site-scoped Evidence Drift and agent-memory graph is `kairos_drift__<site>` by default. ResolveAI consumer cases, fraud and GreenChain use their existing named graphs in the same FalkorDB instance. Neo4j remains the industrial asset/document graph of record; this setup does not copy, replace or delete it. Graph Lab and the existing graph views provide visualization.

## Local connection

From the repository root in PowerShell:

```powershell
Copy-Item .env.example .env   # only if .env does not already exist
docker compose --profile local-stores up -d kairos-falkordb
docker compose --profile local-stores exec -T kairos-falkordb redis-cli PING
docker compose --profile local-stores exec -T kairos-falkordb redis-cli GRAPH.LIST
```

`FALKORDB_URL=redis://localhost:6380` is for a backend process on the Windows host. `FALKORDB_CONTAINER_URL=redis://kairos-falkordb:6379` is injected as `FALKORDB_URL` into the API and worker containers. The development override publishes only `127.0.0.1:6380`; the base deployment publishes no FalkorDB port. If an older `.env` has only the host URL, add `FALKORDB_CONTAINER_URL` before starting Compose. Port 6380 must be free if Compose is to own the local server.

The `local-stores` profile is opt-in. The named `kairos-falkordb_data` volume holds graph data. The local service uses append-only persistence (`appendfsync everysec`) alongside RDB snapshots. A process crash can still lose the most recent writes; a named volume is not a backup. Never use `docker compose down -v` or `make nuke` on a graph you need to keep.

The signed-in `GET /health/falkordb` route checks connectivity and whether the token's site graph exists without creating one. A new site graph can legitimately report `site_graph_exists: false` until its first write. `GRAPH.LIST` is an instance-level inventory command; do not expose it as a cross-tenant application endpoint.

## Existing FalkorDB Cloud instance (explicit opt-in)

No cloud service is purchased, provisioned or started by this repository. To use an instance you already control, set **both** `FALKORDB_URL` and `FALKORDB_CONTAINER_URL` in the untracked `.env` to that instance's authenticated `rediss://` URL. `rediss://` requests TLS; keep certificate verification enabled. URL-encode reserved characters in credentials. A host-run API reads `FALKORDB_URL`, and Compose services read `FALKORDB_CONTAINER_URL`. If an existing deployment supplies only `FALKORDB_URL`, Compose continues to honor it for compatibility; an explicit container URL takes precedence. Do not place a credential in committed Compose files or `.env.example`.

Keep `FALKORDB_GRAPH_PREFIX` unchanged when reconnecting to existing Evidence Drift memory. A different prefix selects a different set of site graphs and makes the old memory appear absent. The other domain graph names are set by their existing adapters. Check `GET /health/falkordb` and a site-scoped read after changing a connection. Do not run synthetic seed or destructive integration tests against a cloud or golden graph.

## Existing data: migration and rollback

This is a manual, opt-in procedure. No migration runs at application startup. Record the target instance, the current `FALKORDB_GRAPH_PREFIX`, all graph names, and the intended site IDs before changing anything. Obtain an authorized maintenance window and stop graph-writing requests/workers so the inventory and backup describe one state. `GRAPH.LIST` and bounded `GRAPH.RO_QUERY` counts are safe preflight reads. Keep Neo4j and every existing Falkor graph untouched.

1. **Back up the source.** For the local instance, run `BGSAVE`, wait for `rdb_bgsave_in_progress:0` and `rdb_last_bgsave_status:ok` in `INFO persistence`, then copy `/var/lib/falkordb/data/dump.rdb` from the container to a dated location **outside this repository**. Record its SHA-256 hash and the graph list. Keep the original named volume. For a managed instance, use its provider-supported backup/export and verify the restore procedure first; do not assume a local Redis snapshot is portable to that service.
2. **Dry run in isolation.** Restore the backup to a separate local FalkorDB instance and volume, never onto the current volume. Confirm graph names plus per-graph node and relationship counts with `GRAPH.RO_QUERY`. Exercise a site-scoped memory read and an action-eligibility read against that isolated copy. If any count or lineage differs, stop.
3. **Copy within one instance when the schema is unchanged.** Verify the destination name does not exist. With writes still paused, `GRAPH.COPY <old-prefix>__<site> <new-prefix>__<site>` creates a separate graph for each selected site; the [official Python client](https://github.com/FalkorDB/falkordb-py) exposes the same operation as `Graph.copy`. Repeat for every intended site, then compare labels, relationship types, counts, memory lineage, revision hashes and approval eligibility. This copy does not migrate the independent `resolve_consumer_`, `fraud_` or `greenchain_` namespaces, which remain in place.
4. **Cut over only after comparison.** Set `FALKORDB_GRAPH_PREFIX` to the new prefix in the application environment, restart the API/workers, check `/health/falkordb` for the authenticated site, and read one known memory and decision. Retain the source graph and backup. A schema transformation or cross-instance move requires a separately reviewed exporter/importer and validation; `GRAPH.COPY` is only a same-instance, unchanged-schema path.
5. **Roll back by configuration.** Pause writes, restore the previous prefix and connection URL, restart the application, and verify the original graph's memory and health. Do not delete either graph. Writes accepted after cutover are not automatically present in the old graph, so reconcile them from an audit/replay plan before resuming writes. Never restore a backup over a live graph or run `GRAPH.DELETE` as part of rollback.

These steps are a strategy, not a claim that an existing Neo4j, local FalkorDB or cloud dataset has been migrated. The application has no automatic cross-instance memory importer.

## Optional official MCP access

Kairos's API uses the Python client directly and does not require an MCP server. The [official FalkorDB MCP server](https://github.com/FalkorDB/FalkorDB-MCPServer) is a separate optional operator tool; it is absent from Compose and disabled by default. Its `FALKORDB_DEFAULT_READONLY=true` setting makes query tools default to `GRAPH.RO_QUERY`, but it is not a database authorization boundary and the server also offers mutation tools. Before attaching an agent to a non-disposable graph, create a dedicated server-enforced read-only FalkorDB account that permits only required read commands and denies `GRAPH.QUERY`, `GRAPH.DELETE`, `GRAPH.COPY` and administrative writes. Use stdio transport so no HTTP MCP endpoint is exposed. For a cloud connection, also set `FALKORDB_TLS=true` and verify the certificate and hostname. Never give this optional MCP process the application's write credential.

Primary references: [FalkorDB server](https://github.com/FalkorDB/FalkorDB), [Python client](https://github.com/FalkorDB/falkordb-py), [official MCP server](https://github.com/FalkorDB/FalkorDB-MCPServer).
