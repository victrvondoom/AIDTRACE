
# HeatPath — Graph-Powered Urban Heat Investigation Agent

HeatPath is a graph-powered investigation agent built with Python and FalkorDB. It compares two urban heat hotspot records by traversing connected risks, supporting evidence, nearby facilities, interventions, and previous investigation records.

HeatPath is designed to avoid unsupported prioritization. When the available records do not justify a defensible decision, it returns `INSUFFICIENT_EVIDENCE` rather than forcing a winner.

## Problem

Urban heat prioritization cannot reliably depend on temperature alone. Investigators need to examine connected risk factors, supporting evidence, data provenance, verification status, and gaps in the available records.

## Solution

HeatPath uses graph relationships to:

- Retrieve hotspot records and their connected risks.
- Trace supporting evidence, nearby facilities, and interventions.
- Identify unverified hotspot records and unsupported risk claims.
- Compare two hotspots using explicit decision-safety checks.
- Return an insufficient-evidence result when required evidence is missing or unverified.
- Retrieve previous investigations and save a persistent audit record for each run.

Investigation history is currently used as context and is not allowed to override current evidence. Historical memory does not yet influence the decision engine.

## Hackathon Track

Proposed track: Agents That Act on Connected Data

HeatPath uses FalkorDB as its graph-backed investigation layer. It traverses relationships between heat zones, risk factors, evidence, nearby facilities, and interventions to construct investigation reports. It also stores investigation history in the graph for contextual reference.

The agent applies conservative decision rules and returns "INSUFFICIENT_EVIDENCE" rather than selecting a hotspot when the available data is unverified or a validated prioritization policy is absent.

Current scope: The demonstration uses synthetic hotspot records. It is a prototype, not a validated real-world urban heat prioritization system.

## Graph Architecture

The synthetic graph uses the following node types:

- `HeatZone` — hotspot records and their metadata.
- `RiskFactor` — connected risk factors.
- `Evidence` — records intended to support an investigation.
- `Facility` — nearby facilities.
- `Intervention` — potential responses to identified risks.
- `InvestigationHistory` — persistent investigation audit records.

Key relationships include:

- `HAS_RISK`
- `SUPPORTED_BY`
- `NEARBY_FACILITY`
- `HAS_INTERVENTION`

Investigation history is stored separately from the hotspot evidence graph.

## Graph Queries

HeatPath uses Cypher-style graph queries through the FalkorDB Python client.

1. Retrieve a hotspot

The agent looks up a hotspot by its ID and retrieves its name, temperature, measurement date, and data-verification status.

```
MATCH (h:HeatZone {id: $hotspot_id})
RETURN h.id, h.name, h.temperature_c,
       h.measurement_date, h.data_status
```

2. Traverse connected risk factors

```
MATCH (h:HeatZone {id: $hotspot_id})
      -[:HAS_RISK]->(r:RiskFactor)
RETURN r.id, r.name, r.severity, r.data_status
```

3. Retrieve linked evidence

```
MATCH (h:HeatZone {id: $hotspot_id})
      -[:SUPPORTED_BY]->(e:Evidence)
RETURN e.id, e.name, e.confidence,
       e.source_type, e.data_status
```

4. Retrieve nearby facilities and interventions

```
MATCH (h:HeatZone {id: $hotspot_id})
      -[:NEARBY_FACILITY]->(f:Facility)
RETURN f.id, f.name, f.facility_type, f.data_status

MATCH (h:HeatZone {id: $hotspot_id})
      -[:HAS_INTERVENTION]->(i:Intervention)
RETURN i.id, i.name, i.data_status
```

These queries are parameterized by hotspot ID. Their results populate the investigation report used by the decision engine.

### Decision safeguards

The decision engine checks whether both hotspot records exist, whether their data is verified, whether measurement dates are comparable, and whether directly linked verified evidence exists. Even when these checks pass, it does not select a winner until a validated prioritization policy is configured.

The current demonstration uses synthetic records; these queries do not establish real-world evidence or validate actual heat-risk priorities.

## Decision-Safety Behavior

HeatPath is designed to:

- Avoid selecting a winner when a hotspot is missing or unverified.
- Avoid treating synthetic data as verified real-world evidence.
- Identify missing or insufficient supporting evidence.
- Avoid using temperature alone as a basis for prioritization.
- Preserve the reasons behind a decision in an audit record.

The current decision engine conservatively returns `INSUFFICIENT_EVIDENCE` even when preliminary checks pass, because a validated prioritization policy has not yet been configured.

## Data and Limitations

HeatPath currently uses synthetic records only. Names such as “Synthetic Hotspot A” and “Fictional thermal observation A” are test fixtures, not observations of actual locations.

A metadata check is not proof that evidence is authentic. Missing dates indicate unknown freshness, not automatically stale evidence.

HeatPath is a prototype, not a validated real-world urban heat prioritization system. Its decision engine conservatively returns ```"INSUFFICIENT_EVIDENCE"``` when required evidence is missing, unverified, synthetic, or not directly comparable. Even when preliminary checks pass, the system does not select a winner because a validated prioritization policy has not yet been configured.

### Testing and Verification

The automated test suite contains five tests covering:

- Missing hotspot records.
- Synthetic data.
- Unverified hotspot records.
- Different measurement dates.
- Verified records without a validated prioritization policy.

All five automated tests passed in the latest recorded test run.

Additional manual checks confirmed that the agent retrieves and persists investigation history, that shared and unique connected graph records are distinguished in a controlled comparison, and that past investigation history is not an input to the current decision function. A focused regression check also confirmed repeatable decisions for identical current reports and no forced winner without a prioritization policy.

These checks validate the tested implementation paths; they do not establish the authenticity of evidence, the accuracy of real-world risk assessments, or the correctness of every possible graph and memory scenario. Broader testing with independently verified real-world data and a validated prioritization policy remains future work.

## Technology

- Python
- FalkorDB graph database
- `falkordb` Python client
- `python-dotenv`
- Google Colab
- GitHub

## Setup

1. Clone this repository.
2. Install the dependencies.
3. Configure the FalkorDB connection using environment variables.
4. Create or populate the expected synthetic graph before running the agent.

Install dependencies:

```bash
pip install -r requirements.txt
```

Configure the following environment variables for your FalkorDB instance:

- `FALKORDB_HOST`
- `FALKORDB_PORT`
- `FALKORDB_USERNAME`
- `FALKORDB_PASSWORD`
- `FALKORDB_GRAPH_NAME`
- `FALKORDB_SSL`

Do not commit passwords, access tokens, or other credentials to GitHub.

Run the agent:

```bash
python heatpath_agent.py --a zone_a --b zone_b
```

The command prints the hotspot investigation reports, previous investigations, decision result, and newly saved investigation ID. Each successful run writes a new `InvestigationHistory` record.

**Important:** The graph must already contain the expected synthetic hotspot records ("zone_a" and "zone_b") before running the agent. For a fresh setup, configure the FalkorDB environment variables and run "python seed_synthetic_data.py" to populate the synthetic graph. Then run the agent using the command shown above. Each successful agent run saves a new "InvestigationHistory" record.

## AI Assistance Disclosure

ChatGPT was used to assist with project planning, troubleshooting, test interpretation, and documentation.
