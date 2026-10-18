# Dependency and runtime conflicts

## Resolved for the drift foundation

| Component | Kairos pin/state | Integration choice | Evidence and limit |
|---|---|---|---|
| Redis Python client | `redis==5.0.6` (also used by Celery) | Retain pin | Do not move Celery's broker client to satisfy a newer graph client without a separate compatibility review. |
| FalkorDB Python client | `falkordb==1.0.10` | Pin and use `FalkorDB.from_url()` | The Kairos image reports the exact client API; standalone URLs are passed through `from_url`, while the constructor's `url` argument is for cluster configuration. |
| FalkorDB server | Local server reports module version `4.22.1` | Pin the tested image by immutable digest in Compose | The server was exercised on 2026-10-17. The Compose service remains under `local-stores`; no production graph cutover is implemented. |
| Kairos graph of record | Neo4j | Retain | Existing assets, documents and operational relationships remain in Neo4j. The new FalkorDB graph is separate and reserved for decision dependencies. |
| Site isolation | Kairos role/site context | One FalkorDB graph per validated site id | The future API must source `site_id` from the verified token (`dependencies.site_scope`), never a query parameter. |

## Remaining review

- The [FalkorDB Docker image is licensed under SSPLv1](https://hub.docker.com/r/falkordb/falkordb). Review its obligations for the planned commercial deployment and distribution model before production use. This repository adds a local development service only.
- Graph migration, backups, restore drills, metrics, and production topology are not implemented.
- No service route or Kairos UI currently writes drift records or invokes impact traversal; this is a persistence foundation, not an end-to-end feature.
- The graph traversal reads one hop at a time, caps depth and total discovered nodes/edges, uses read-only graph queries for impact discovery, and raises on truncation so a partial set cannot be presented as complete.
- The database service is not started by default. Use the `local-stores` profile for local Compose development.
