# ThreatPath: Graph-Native Defensive Security Investigation Agent

[![Live Application](https://img.shields.io/badge/Live_Application-threatpath--production.up.railway.app-0284c7?style=for-the-badge&logo=railway)](https://threatpath-production.up.railway.app)
[![GitHub Repository](https://img.shields.io/badge/GitHub-SaswatSRoy%2FThreatPath-181717?style=for-the-badge&logo=github)](https://github.com/SaswatSRoy/ThreatPath)
[![Graph Hacks 2026](https://img.shields.io/badge/Graph_Hacks_2026-Track_01:_Agents_That_Act_on_Connected_Data-0284c7?style=for-the-badge)](https://graphhacks.devpost.com/)
[![Database: FalkorDB](https://img.shields.io/badge/Database-FalkorDB_6.0.2-c084fc?style=for-the-badge&logo=redis)](https://docs.falkordb.com/)
[![Tests: 59 Passed](https://img.shields.io/badge/Tests-59_Passed_(100%25)-10b981?style=for-the-badge)](tests/)
[![Docker: Multi--Stage_Production](https://img.shields.io/badge/Docker-Multi--Stage_Prod_Verified-38bdf8?style=for-the-badge&logo=docker)](Dockerfile)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue?style=for-the-badge)](LICENSE)

> **ThreatPath** is an autonomous defensive security investigation agent built natively on **FalkorDB** for **Graph Hacks 2026 (Track 01 — Agents That Act on Connected Data)**. It investigates suspicious security alerts by traversing multi-hop causal paths across identities, events, hosts, process trees, network indicators, MITRE ATT&CK techniques, known exploited vulnerabilities (CISA KEV), and critical business assets.
>
> **Live Deployed Application:** [https://threatpath-production.up.railway.app](https://threatpath-production.up.railway.app)  
> **Source Repository:** [https://github.com/SaswatSRoy/ThreatPath](https://github.com/SaswatSRoy/ThreatPath)

---

## 1. Primary Track Declaration
- **Track**: **Track 01 — Agents That Act on Connected Data**
- **Core Proof**: ThreatPath proves that FalkorDB graph traversals directly dictate the investigation outcome, classification, and defensive response. The system includes a mandatory **Graph-Ablation Test** proving that removing a physical graph edge in FalkorDB directly alters the security assessment.

---

## 2. Key Features

- **Multi-Hop Evidence Traversal**: Automatically follows causal relationships from alerts through events, hosts, process executions, and external C2 indicators.
- **Deterministic Heuristic Assessment**: Uses transparent, testable rules to classify compromise (`likely_compromise`, `suspicious`, `insufficient_evidence`) and prioritize remediation (`critical`, `high`, `medium`, `low`) independently of LLM hallucinations.
- **Vulnerability vs. Exploitation Distinction**: Strictly distinguishes between vulnerable software exposure (e.g. Apache Struts CVE-2023-50164 / CISA KEV) and verified compromise.
- **Custom Scenario Lab**: Built-in JSON scenario authoring, offline schema/domain validation, live Cytoscape graph preview, and session-isolated persistence allowing analysts to test synthetic scenarios beyond pre-seeded alerts.
- **Human-in-the-Loop Approval Gate**: Consequential actions (e.g., isolating production jump boxes or disabling accounts) enforce strict human authorization before simulated execution.
- **Simulated Fleet Verification**: Simulates containment actions against a verified sandbox fleet and validates resulting state telemetry before confirming success.
- **Official Model Context Protocol (MCP) Server**: Exposes 8 domain-specific investigation tools via the official Python MCP SDK (`mcp 2.x`).
- **Interactive Cytoscape.js Workspace**: Real-time visual graph representation with node property inspection, layout switching, and responsive telemetry panels.
- **Complete Test Suite & Provenance Persistence**: 59 automated unit, integration, ablation, and scenario validation tests passing (100%) against live FalkorDB queries.

---

## 3. Architecture Overview

```
+-----------------------------------------------------------------------------------------+
|                                    THREATPATH WORKSPACE                                  |
|                                                                                         |
|  +--------------------+         +-----------------------+         +-------------------+ |
|  |   Alert Queue &    |         | Interactive Evidence  |         |   Deterministic   | |
|  | Scenario Selector  | ------> |     Graph Canvas      | ------> | Assessment Engine | |
|  |  (A, B, C, D)      |         |    (Cytoscape.js)     |         |    & Scoring      | |
|  +--------------------+         +-----------------------+         +-------------------+ |
|                                                                             |           |
|                                                                             v           |
|  +--------------------+         +-----------------------+         +-------------------+ |
|  | Verification Check | <------ |  Simulated Execution  | <------ | Human-in-the-Loop | |
|  | (Host Isolated)    |         |   (Sandboxed Fleet)   |         |   Approval Gate   | |
|  +--------------------+         +-----------------------+         +-------------------+ |
+-----------------------------------------------------------------------------|-----------+
                                                                              |
                                     FastAPI REST API / MCP Protocol          |
                                     (127.0.0.1:8000 / stdio)                 |
                                                                              v
+-----------------------------------------------------------------------------------------+
|                                   BACKEND ENGINE                                        |
|                                                                                         |
|   +-----------------------+   +------------------------+   +------------------------+   |
|   |  Autonomous Agent     |   | FalkorDB-Native Tools  |   | Response Policy Engine |   |
|   |  Orchestrator         |   | & Official MCP Server  |   | (ALLOW / APPROVE / BLK)|   |
|   +-----------------------+   +------------------------+   +------------------------+   |
+-------------------------------------------|---------------------------------------------+
                                            | falkordb-py client (tcp 127.0.0.1:6379)
                                            v
+-----------------------------------------------------------------------------------------+
|                                  FALKORDB ENGINE                                        |
|                                                                                         |
|      Dedicated Database Graph: [ threatpath_dev ]                                       |
|      (Alert) --> [:HAS_EVENT] --> (Event) --> [:OCCURRED_ON] --> (Host)                 |
|                                     |                             |                     |
|                                     v                             v                     |
|                               (Technique)                     (Process)                 |
|                                                                   |                     |
|                                                                   v                     |
|                                                              (Indicator)                |
|      Preserved Practice Data: [ social ] (Untouched)                                    |
+-----------------------------------------------------------------------------------------+
```

---

## 4. FalkorDB Graph Schema & Semantics

ThreatPath uses a dedicated graph named **`threatpath_dev`**, preserving all existing database graphs.

### Schema Relationships:
```
(Alert)-[:HAS_EVENT]->(Event)
(Event)-[:INVOLVES_IDENTITY]->(Identity)
(Event)-[:OCCURRED_ON]->(Host)
(Event)-[:INVOLVES_PROCESS]->(Process)
(Host)-[:EXECUTED]->(Process)
(Process)-[:CONNECTED_TO]->(Indicator)
(Event)-[:MAPS_TO]->(Technique)
(Host)-[:RUNS]->(Software)
(Software)-[:AFFECTED_BY]->(Vulnerability)
(Host)-[:CAN_ACCESS]->(Asset)
(Investigation)-[:INVESTIGATES]->(Alert)
(Investigation)-[:RECOMMENDED_ACTION]->(ResponseAction)
```

See [docs/GRAPH_MODEL.md](docs/GRAPH_MODEL.md) for full node property schemas and relationship semantics.

---

## 5. Why FalkorDB is Essential

1. **Sub-Millisecond Graph Traversal**: Relational databases require expensive 5-way SQL joins to connect an alert to its external C2 IP. In FalkorDB, path traversals (`Alert -> Event -> Host -> Process -> Indicator`) execute in under 1.2 milliseconds.
2. **First-Class Cypher Path Matching**: Cypher's `MATCH p = (a:Alert)-[*1..4]-(target)` pattern matching enables rapid bounded graph expansion for incident root-cause analysis.
3. **Graph Ablation Demonstrability**: Because the topology directly drives the assessment, deleting a single edge in FalkorDB changes the deterministic classification from `likely_compromise` to `suspicious`.

---

## 6. Primary Cypher Queries

### Multi-Hop Attack Path Traversal
```cypher
MATCH p = (a:Alert)-[:HAS_EVENT]->(e:Event)-[:OCCURRED_ON]->(h:Host)-[:EXECUTED]->(pr:Process)-[:CONNECTED_TO]->(ind:Indicator)
WHERE a.id = $alert_id
RETURN p, pr, ind, h;
```

### High-Value Asset Reachability
```cypher
MATCH p = (a:Alert)-[:HAS_EVENT]->(e:Event)-[:OCCURRED_ON]->(h:Host)-[:CAN_ACCESS]->(ast:Asset)
WHERE a.id = $alert_id
RETURN p, h.hostname AS hostname, ast.id AS asset_id, ast.name AS asset_name,
       ast.criticality AS criticality, ast.data_classification AS classification;
```

### Software & CISA KEV Vulnerability Exposure
```cypher
MATCH p = (a:Alert)-[:HAS_EVENT]->(e:Event)-[:OCCURRED_ON]->(h:Host)-[:RUNS]->(s:Software)-[:AFFECTED_BY]->(v:Vulnerability)
WHERE a.id = $alert_id
RETURN p, s.name AS software, s.version AS version, v.cve_id AS cve_id,
       v.cvss_score AS cvss_score, v.cisa_kev AS cisa_kev, v.description AS description;
```

See [docs/CYPHER_QUERIES.md](docs/CYPHER_QUERIES.md) for complete parameterized query specifications.

---

## 7. Model Context Protocol (MCP) Integration

ThreatPath implements a genuine MCP server (`backend/agent/mcp_server.py`) using the official Python MCP SDK (`mcp 2.x`).

### Registered MCP Tools:
- `get_alert_context(alert_id: str)`: Resolves immediate alert envelope.
- `trace_attack_path(alert_id: str)`: Discovers multi-hop execution and C2 paths.
- `check_asset_exposure(alert_id: str)`: Identifies reachability to high-value assets.
- `get_indicator_context(alert_id: str)`: Retrieves threat intel and reputation scores.
- `find_related_alerts(alert_id: str)`: Correlates alerts sharing hosts or identities.
- `record_investigation(...)`: Persists investigation provenance into FalkorDB.
- `simulate_response(action_type, target_entity)`: Proposes simulated defensive containment.
- `execute_response(action_id)`: Executes containment against simulated fleet.
- `verify_response(action_id)`: Verifies resulting telemetry on simulated endpoints.

---

## 8. Four Synthetic Scenarios

| Scenario | Alert ID | Description | FalkorDB Ground Truth | Outcome |
| :--- | :--- | :--- | :--- | :--- |
| **Scenario A** | `alert-sec-001` | Suspicious Interactive Logon & Beaconing | RDP Logon -> Jump Host -> Encoded PowerShell -> C2 IP (198.51.100.44) -> Access to Customer DB | **Likely Compromise** (Critical Priority, Host Isolation Proposed) |
| **Scenario B** | `alert-sec-002` | Off-Hours Login from Anomalous Geolocation | Single SSO auth on Auth Gateway. Zero child processes, zero external IOCs | **Insufficient Evidence** (Low Priority, Missing Evidence Flagged) |
| **Scenario C** | `alert-sec-003` | Critical RCE Disclosure (Struts CVE-2023-50164) | Host runs vulnerable software with access to Payment API, but zero malicious executions | **Suspicious (Exposure Only)** (High Priority, Not Compromised) |
| **Scenario D** | `alert-sec-004` | Repeated Password Spray Failures | Failed SSH logins on Staging Bastion. Independent scanner IOC in DB is disconnected | **Insufficient Evidence** (Disconnected Entities Not Correlated) |

---

## 9. Custom Scenario Lab & Versioned Schema

ThreatPath provides a **Custom Scenario Lab** enabling analysts to compose, validate, preview, save, and investigate synthetic cybersecurity scenarios beyond the four pre-seeded alerts.

### 9.1 Primary Workflow
1. **Open Custom Scenario Lab**: Click the **"Scenario Lab"** button in the navigation header.
2. **Author or Edit JSON**: Use the built-in JSON editor or click **"Load Template"** to populate the canonical endpoint scenario.
3. **Validate**: Click **"Validate Scenario"**. The offline validator verifies schema structure, ID uniqueness, allowed labels, and domain endpoint constraints, surfacing actionable errors and warnings.
4. **Preview Graph**: Valid scenarios generate an interactive Cytoscape.js graph preview showing proposed node categories and directed edges before touching the database.
5. **Save Scenario**: Click **"Save Scenario"**. The backend idempotently persists the nodes and relationships into FalkorDB, scoped to your session ID (`X-Session-ID`).
6. **Investigate**: Open the saved scenario directly in the ThreatPath workspace to execute multi-hop evidence traversal, deterministic assessment, and simulated response recommendations.

### 9.2 Versioned Scenario Schema (`1.0`)

Custom scenarios must adhere to schema version `1.0`:

```json
{
  "schema_version": "1.0",
  "name": "Suspicious PowerShell Execution",
  "description": "A synthetic investigation involving unusual process execution on a workstation.",
  "alert": {
    "id": "alert-custom-001",
    "title": "Suspicious PowerShell Execution",
    "severity": "HIGH",
    "status": "NEW",
    "description": "A workstation generated an alert after executing an unusual PowerShell command.",
    "source": "CUSTOM_SCENARIO"
  },
  "entities": [
    {
      "id": "event-custom-001",
      "label": "Event",
      "properties": {
        "event_type": "PROCESS_EXECUTION",
        "description": "Unusual PowerShell execution observed",
        "timestamp": "2026-03-29T10:15:00Z"
      }
    },
    {
      "id": "host-custom-001",
      "label": "Host",
      "properties": {
        "hostname": "workstation-17",
        "environment": "endpoint"
      }
    },
    {
      "id": "process-custom-001",
      "label": "Process",
      "properties": {
        "name": "powershell.exe",
        "command_line": "powershell.exe -NoProfile -ExecutionPolicy Bypass -Command Write-Host 'Synthetic Test'"
      }
    }
  ],
  "relationships": [
    {
      "from": "alert-custom-001",
      "type": "HAS_EVENT",
      "to": "event-custom-001"
    },
    {
      "from": "event-custom-001",
      "type": "OCCURRED_ON",
      "to": "host-custom-001"
    },
    {
      "from": "host-custom-001",
      "type": "EXECUTED",
      "to": "process-custom-001"
    }
  ]
}
```

### 9.3 Canonical Allowed Labels & Relationship Constraints

To prevent graph corruption and Cypher injection, labels and relationship types are enforced through strict server-side allowlists:

- **Allowed Node Labels**: `Alert`, `Event`, `Host`, `Process`, `Indicator`, `Identity`, `Software`, `Vulnerability`, `Asset`, `Technique`.
- **Allowed Relationship Types & Endpoint Constraints**:
  - `(Alert)-[:HAS_EVENT]->(Event)`
  - `(Event)-[:INVOLVES_IDENTITY]->(Identity)`
  - `(Event)-[:OCCURRED_ON]->(Host)`
  - `(Event)-[:INVOLVES_PROCESS]->(Process)`
  - `(Host)-[:EXECUTED]->(Process)`
  - `(Process)-[:CONNECTED_TO]->(Indicator)`
  - `(Event)-[:MAPS_TO]->(Technique)`
  - `(Host)-[:RUNS]->(Software)`
  - `(Software)-[:AFFECTED_BY]->(Vulnerability)`
  - `(Host)-[:CAN_ACCESS]->(Asset)`

### 9.4 Session Scoping & Isolation

- **Session Ownership**: Each custom scenario and its constituent graph entities are scoped to the client's `X-Session-ID`.
- **Cross-Session Isolation**: Custom scenarios authored by Session A cannot be viewed, listed, or traversed by Session B.
- **Global Demo Alerts**: Seeded demonstration alerts (`alert-sec-001` through `alert-sec-004`) have `session_id IS NULL` and remain globally available to all users.
- **Security Boundary**: The client-generated `X-Session-ID` is an isolation mechanism for multi-user demonstration environments, not cryptographically verified authentication. It prevents concurrent evaluator collisions in demo deployments.

---

## 10. Quickstart & Setup Instructions

### Prerequisites
- Linux / macOS
- Docker (with local FalkorDB running: `docker ps`)
- Python 3.12+
- Node.js v20+ & npm

### Step 1: Environment Setup & Dependencies
```bash
# Initialize Python virtual environment
python3 -m venv venv
source ./venv/bin/activate

# Install backend dependencies
pip install --upgrade pip
pip install falkordb fastapi uvicorn pydantic pydantic-settings python-dotenv pytest httpx mcp

# Install frontend dependencies
npm --prefix ./frontend install
```

### Step 2: Configure Environment
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Default configuration connects to local FalkorDB at `127.0.0.1:6379` using dedicated graph `threatpath_dev`.

### Step 3: Seed Synthetic Scenarios into FalkorDB
```bash
python3 -m backend.seed
```

### Step 4: Run the Test Suite (Including Graph Ablation & Validation Tests)
```bash
pytest tests/ -v
```

### Step 5: Start the Backend Server
```bash
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

### Step 6: Start the Frontend Workspace
```bash
npm --prefix ./frontend run dev
```
Open **`http://localhost:5173`** in your browser.

---

## 11. Production Multi-Stage Docker Build

ThreatPath packages both the compiled React frontend and the FastAPI backend into a single self-contained, production-grade container image:

```bash
# 1. Build the production multi-stage image
docker build -t threatpath:prod .

# 2. Run the production container on port 8000
docker run -p 8000:8000 \
  -e FALKORDB_HOST=127.0.0.1 \
  -e FALKORDB_PORT=6379 \
  -e FALKORDB_GRAPH=threatpath_dev \
  -e APP_ENV=production \
  threatpath:prod
```
The unified container serves compiled React static assets directly from `/` and handles API requests under `/api/...` on the same origin with zero cross-origin configuration.

---

## 12. Cloud Deployment (Railway Ready)

ThreatPath is fully configured for deployment on Railway or any Docker-compatible PaaS platform:

- **Single Web Service**: Directly deploys from the root `Dockerfile` with automatic dynamic port binding (`$PORT`) and graceful signal propagation.
- **Private FalkorDB Service**: Uses official pinned `falkordb/falkordb-server:6.0.2`, mounted to a persistent volume at `/var/lib/falkordb/data`, protected by Redis password authentication (`REDIS_ARGS=--requirepass ${{ FALKORDB_PASSWORD }} --appendonly yes`), with zero public network exposure.
- **Dedicated Demo Graph**: Uses isolated graph `threatpath_demo`.
- **Durable Simulation State**: Simulated containment and incident state transitions are persisted in FalkorDB and survive container restarts.
- **Multi-User Demo Isolation**: Sessions are isolated by demo session ID so multiple judges never corrupt each other's investigations.
- **Safe In-Network Remote Seeding**: Dedicated idempotent seed utility with strict safeguards run inside Railway's private network (via container terminal or one-off seeder job):
  ```bash
  python -m scripts.seed_remote --confirm
  ```

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for step-by-step Railway dashboard provisioning instructions and checklists.

---

## 13. REST API Endpoints

### Core Alerts & Investigations
- `GET /api/health` — Verifies FalkorDB connectivity and operational mode.
- `GET /api/alerts` — Lists registered security alerts in FalkorDB (filtered by session).
- `GET /api/alerts/{alert_id}` — Retrieves an individual alert.
- `POST /api/investigations` — Triggers graph-native autonomous investigation.
- `GET /api/investigations/{id}` — Retrieves investigation record (persisted across restarts).
- `GET /api/investigations/{id}/evidence` — Retrieves structured evidence & Cytoscape graph.

### Response Actions & Approval Gate
- `POST /api/actions/{id}/approve` — Analyst approval gate.
- `POST /api/actions/{id}/deny` — Analyst denial gate.
- `POST /api/actions/{id}/execute` — Executes containment on simulated fleet.
- `GET /api/actions/{id}/verify` — Verifies simulated endpoint telemetry.

### Custom Scenario Lab
- `POST /api/scenarios/validate` — Validates custom scenario schema and generates offline Cytoscape preview.
- `POST /api/scenarios` — Validates and idempotently persists custom scenario scoped to `X-Session-ID`.
- `GET /api/scenarios` — Lists custom scenarios belonging to caller's `X-Session-ID`.
- `GET /api/scenarios/{id}` — Retrieves custom scenario by ID.
- `GET /api/scenarios/template` — Returns canonical starter scenario template.

---

## 14. Security & Safety Boundaries

- **Zero Production Risk**: All containment actions are strictly simulated. ThreatPath never isolates real endpoints, modifies real network controls, or executes arbitrary shell commands.
- **Strict Parameterization & Allowlists**: All Cypher queries use parameterized inputs. Custom scenario ingestion verifies all node labels and relationship types against strict server-side allowlists, preventing query injection.
- **Credential Protection**: Database passwords and API keys are never exposed in tool arguments or logged.
- **Isolated Private Database**: The production database has no public domain or TCP proxy.
- **Approval Gate**: Consequential actions (host isolation, account disablement) strictly require manual approval before execution.
- **Session Scoping**: Custom scenarios and alerts are scoped to `X-Session-ID`, providing multi-user isolation during demonstration evaluations.

---

## 15. Known Limitations & Engineering Notes

1. **Deterministic Rule Engine (No Black-Box Scoring)**: ThreatPath's assessment engine operates on explicit, testable heuristic factor weights (ranging from 0.05 to 0.95). Scores provide transparent, explainable triage ranking rather than calibrated Bayesian probabilities.
2. **Simulated Response Fleet**: Consequential actions (`SIMULATE_ISOLATE_HOST`, `SIMULATE_DISABLE_ACCOUNT`, `SIMULATE_ESCALATE_INCIDENT`) modify a sandboxed, state-persisted fleet simulation in FalkorDB and local memory. ThreatPath never executes destructive commands or modifies real cloud/EDR infrastructure.
3. **LLM Provider Default**: The production deployment operates by default with `LLM_PROVIDER=mock`, utilizing deterministic rule-based generation for incident narratives without external API key dependencies. External LLM providers (`openai`, `anthropic`, `gemini`) are supported optionally.
4. **Remote Seeding Validation Mismatch Resolved**: Previous builds checked for a legacy relationship label `HAS_TECHNIQUE` during post-seed verification. `scripts/seed_remote.py` now validates the canonical `MAPS_TO` relationship and verifies semantic `(Event)-[:MAPS_TO]->(Technique)` connectivity and alert-event linkage, covered by 6 automated regression tests in `tests/test_seed_validation.py`.
5. **Session Isolation Boundary**: Client-supplied `X-Session-ID` headers partition custom scenarios and simulated fleet states for concurrent evaluation sessions. It is designed for demonstration multi-tenancy and is not a cryptographically verified authentication system.

---

## 16. AI-Assisted Development Disclosure

In accordance with Graph Hacks 2026 rules:
- ThreatPath was designed and engineered with assistance from **Google Antigravity**.
- All FalkorDB Cypher queries, graph schemas, deterministic scoring rules, approval gates, multi-stage Docker builds, scenario validators, and simulation verifiers were designed for this project, audited against live FalkorDB containers, and validated through 59 automated unit, integration, and ablation tests.
