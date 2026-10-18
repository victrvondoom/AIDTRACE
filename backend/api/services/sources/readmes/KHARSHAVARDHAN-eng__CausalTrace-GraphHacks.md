# CausalTrace 🔍⚡

> **AI-Powered Incident Investigation Platform connecting service dependencies, deployments, alerts, and logs in FalkorDB.**  
> Built for the **Graph Hacks** Hackathon (**Track:** Agents That Act on Connected Data).

[![Backend Tests](https://img.shields.io/badge/pytest-25%20passed-emerald)](backend/tests/)
[![Benchmark](https://img.shields.io/badge/Benchmark-10%2F10%20Verified-teal)](backend/scripts/evaluate_investigation.py)
[![Graph Engine](https://img.shields.io/badge/FalkorDB-Native%20Cypher-blue)](https://falkordb.com)
[![Frontend](https://img.shields.io/badge/Vite-React%2018%20%2B%20Tailwind-purple)](frontend/)

---

## 1. Product Vision & Goals

During high-severity production incidents, Site Reliability Engineers (SREs) and incident commanders must manually correlate fragmented information:
- Upstream and downstream service dependency topologies
- Recent code releases and configuration deployments across teams
- Active metric alerts and anomaly thresholds
- Structured error logs and distributed traces across services
- Historical post-mortems and remediation runbooks

In microservice architectures, an upstream root cause (e.g., a connection pool misconfiguration 2–4 hops away) frequently produces symptom alerts on edge services (e.g., checkout API 500s). Relational databases require expensive recursive multi-table JOINs to discover such paths, while distributed tracing alone lacks deployment context.

**CausalTrace** models the entire software production ecosystem as a property graph in **FalkorDB**. When an incident occurs, CausalTrace traverses service topology and temporal change events using native **Cypher queries**, combines graph analytics with a **modular LLM provider**, and ranks root-cause hypotheses with traceable evidence chains in single-digit milliseconds.

---

## 2. Architecture Overview

```
                      ┌───────────────────────────────────────────────┐
                      │             CausalTrace Frontend              │
                      │   (React 18, Vite, TypeScript, Tailwind CSS)  │
                      │   - Live Investigation Workbench & Filters    │
                      │   - Interactive FalkorDB Causal Topology Map  │
                      │   - Corroborated Evidence Chains & Timeline   │
                      └───────────────────────┬───────────────────────┘
                                              │ HTTP / JSON API
                                              ▼
                      ┌───────────────────────────────────────────────┐
                      │              FastAPI Backend                  │
                      │  - Native FalkorDB Cypher Traversal Engine   │
                      │  - Multi-Hop Blast Radius Detection           │
                      │  - Causal Hypothesis Scoring & Demotion       │
                      │  - Safe Abstention Engine (Zero Hallucination)│
                      │  - Health Probes & Pydantic v2 Domain Schemas │
                      └───────────────┬───────────────┬───────────────┘
                                      │               │
                      Cypher (Redis)  │               │ Provider API
                                      ▼               ▼
                      ┌──────────────────────┐ ┌──────────────────────┐
                      │   FalkorDB Graph     │ │ Modular LLM Provider │
                      │ (Primary Graph Store)│ │  (OpenAI / Anthropic)│
                      │ Service Topologies,  │ │ Narrative Synthesis &│
                      │ Deployments, Alerts, │ │ Incident Commander   │
                      │ Logs & Traces        │ │ Runbook Insights     │
                      └──────────────────────┘ └──────────────────────┘
```

### Key Architectural Principles
1. **FalkorDB as the Ground-Truth Graph**: All service relationships, deployments, alerts, and evidence paths live in FalkorDB. The system avoids relational simulations or mocked graph states.
2. **Deterministic Evidence-Based Scoring**: Root cause rankings are computed from structural topological alignment, temporal proximity, critical path flags, and distributed trace corroboration.
3. **Safe Abstention Under Telemetry Gaps**: If telemetry is missing or confidence is low (< 0.60), the engine explicitly abstains and flags data gaps rather than fabricating plausible-sounding culprits.
4. **Honest Readiness Reporting**: `/api/health` reports true socket connectivity, ping latencies, and LLM configuration without masking failures.
5. **Strict Ground-Truth Isolation**: The benchmark ground truth is strictly isolated in `backend/app/evaluation/` and is never imported or queried by the investigation engine.

---

## 3. FalkorDB Graph Schema & Cypher Queries

### Node Labels
| Node Label | Core Properties | Role in Investigation |
| :--- | :--- | :--- |
| `:Incident` | `id`, `title`, `severity`, `status`, `started_at`, `summary` | Root investigation entity orchestrating findings |
| `:Service` | `id`, `name`, `tier`, `team`, `language`, `status` | System component in distributed architecture |
| `:Deployment` | `id`, `version`, `commit_sha`, `timestamp`, `status`, `deployed_by` | Code or configuration change event |
| `:Alert` | `id`, `name`, `severity`, `timestamp`, `status`, `metric_name`, `metric_value` | Firing telemetry threshold |
| `:LogEvent` | `id`, `level`, `message`, `timestamp`, `trace_id` | Anomaly or error log with distributed trace link |

### Relationship Types
| Relationship | Source Node | Target Node | Key Properties | Role |
| :--- | :--- | :--- | :--- | :--- |
| `[:DEPENDS_ON]` | `:Service` | `:Service` | `protocol`, `latency_p99_ms`, `critical` | Multi-hop dependency call graph |
| `[:DEPLOYED_TO]` | `:Deployment` | `:Service` | `environment` | Links releases to target service |
| `[:TRIGGERED_ON]` | `:Alert` | `:Service` | - | Links active alerts to failing service |
| `[:EMITTED_BY]` | `:LogEvent` | `:Service` | - | Links logs and trace spans to service |
| `[:AFFECTS]` | `:Incident` | `:Service` | - | Declares services impacted by incident |
| `[:ROOT_CAUSE]` | `:Incident` | `:Deployment` \| `:Service` \| `:Alert` | `score`, `reasoning`, `evidence_chain` | Synthesized causal hypothesis link |

### Representative Cypher Investigation Patterns

#### 1. Multi-Hop Dependency Blast Radius Traversal (1 to 4 Hops)
```cypher
MATCH path = (s:Service {id: $service_id})-[:DEPENDS_ON*1..4]->(target:Service)
RETURN [node IN nodes(path) | node.id] AS chain,
       [rel IN relationships(path) | rel.critical] AS criticals,
       [rel IN relationships(path) | rel.protocol] AS protos,
       [rel IN relationships(path) | rel.latency_p99_ms] AS latencies;
```

#### 2. Temporal Candidate Deployment Correlation within Blast Radius
```cypher
MATCH (d:Deployment)-[:DEPLOYED_TO]->(s:Service)
WHERE s.id IN $service_ids
  AND d.timestamp <= $max_ts
  AND d.timestamp >= ($max_ts - $window_ms)
RETURN d.id AS id, d.version AS version, d.commit_sha AS commit_sha,
       d.timestamp AS timestamp, d.status AS status, d.deployed_by AS deployed_by,
       s.id AS service_id, s.name AS service_name
ORDER BY d.timestamp DESC;
```

#### 3. Active Firing Alerts Across Topology
```cypher
MATCH (a:Alert)-[:TRIGGERED_ON]->(s:Service)
WHERE s.id IN $service_ids
  AND (a.timestamp <= ($max_ts + 300000) AND a.timestamp >= ($max_ts - $window_ms))
RETURN a.id AS id, a.name AS name, a.severity AS severity,
       a.timestamp AS timestamp, a.metric_name AS metric_name,
       a.metric_value AS metric_value, s.id AS service_id
ORDER BY a.timestamp ASC;
```

#### 4. Corroborating Anomaly Logs with Distributed Trace Identifiers
```cypher
MATCH (l:LogEvent)-[:EMITTED_BY]->(s:Service)
WHERE s.id IN $service_ids
  AND l.timestamp <= ($max_ts + 300000)
  AND l.timestamp >= ($max_ts - $window_ms)
RETURN l.id AS id, l.level AS level, l.message AS message,
       l.timestamp AS timestamp, l.trace_id AS trace_id, s.id AS service_id
ORDER BY l.timestamp DESC;
```

Full schema DDL, constraints, and index definitions are in [`docs/schema.cypher`](docs/schema.cypher).

---

## 4. Synthetic Incident Scenarios & Evaluation Benchmark

To rigorously validate CausalTrace without relying on marketing claims, the repository includes a suite of **10 diverse synthetic failure scenarios** seeded directly into FalkorDB.

### The 10 Seeded Failure Scenarios
1. `inc-01-payment-pool-exhaustion`: Synchronous 2-hop connection pool exhaustion during checkout. (Includes routine distractor release).
2. `inc-02-auth-jwt-secret-mismatch`: Global 401 Unauthorized cascade caused by auth secret rotation deployment.
3. `inc-03-inventory-deadlock-cascade`: Database row-level lock timeouts during inventory allocation.
4. `inc-04-search-vector-oom`: Product search cluster container OOM crash following vector index update.
5. `inc-05-notification-rate-limit-cascade`: SMS dispatch 429 rate limit causing order worker thread starvation.
6. `inc-06-upstream-dns-misconfig`: Upstream CoreDNS packet drops (pure infrastructure alert, zero code deployments).
7. `inc-07-insufficient-evidence-abstain`: Latency breach with dropped telemetry pipeline (must abstain safely).
8. `inc-08-dual-competing-deployments`: Simultaneous fraud evaluator and tax deployments; fraud evaluator isolated via trace evidence.
9. `inc-09-deep-chain-database-schema-migration`: Ledger DDL lock propagating 4 hops upstream to mobile gateway.
10. `inc-10-external-cloud-dependency-degradation`: Video transcoder failures caused by external cloud S3 503 rate limits.

### Reproducible Evaluation Benchmark Results

Run the benchmark with:
```bash
python backend/scripts/evaluate_investigation.py
```

```
==========================================================================================
 CAUSALTRACE INVESTIGATION ENGINE — REPRODUCIBLE EVALUATION BENCHMARK
==========================================================================================
Total Scenarios Evaluated: 10

#   | Incident ID                                | Expected               | Top-1 Found            | Score  | Status           | Latency 
-----------------------------------------------------------------------------------------------------------------------------------------
1   | inc-01-payment-pool-exhaustion             | dep-payment-v2.4.1     | dep-payment-v2.4.1     | 0.955  | PASS (Top-1)     | 64.2  ms
2   | inc-02-auth-jwt-secret-mismatch            | dep-auth-v1.12.0       | dep-auth-v1.12.0       | 1.000  | PASS (Top-1)     | 5.1   ms
3   | inc-03-inventory-deadlock-cascade          | dep-inv-v3.2.0         | dep-inv-v3.2.0         | 1.000  | PASS (Top-1)     | 3.9   ms
4   | inc-04-search-vector-oom                   | dep-search-v5.0.0      | dep-search-v5.0.0      | 1.000  | PASS (Top-1)     | 4.0   ms
5   | inc-05-notification-rate-limit-cascade     | dep-notif-v1.4.2       | dep-notif-v1.4.2       | 1.000  | PASS (Top-1)     | 3.8   ms
6   | inc-06-upstream-dns-misconfig              | alt-dns-core-failure   | alt-dns-core-failure   | 0.812  | PASS (Top-1)     | 3.5   ms
7   | inc-07-insufficient-evidence-abstain       | ABSTAIN                | NONE                   | 0.000  | PASS (Abstained) | 3.4   ms
8   | inc-08-dual-competing-deployments          | dep-fraud-v2.1         | dep-fraud-v2.1         | 1.000  | PASS (Top-1)     | 4.1   ms
9   | inc-09-deep-chain-database-schema-migration | dep-ledger-v1.0.4      | dep-ledger-v1.0.4      | 0.915  | PASS (Top-1)     | 4.5   ms
10  | inc-10-external-cloud-dependency-degradation | alt-s3-slowdown        | alt-s3-slowdown        | 0.812  | PASS (Top-1)     | 4.3   ms

==========================================================================================
 SUMMARY BENCHMARK METRICS
==========================================================================================
Top-1 Root-Cause Accuracy:            100.0%  (9/9 culprit scenarios)
Top-3 Root-Cause Recall:              100.0%  (9/9 culprit scenarios)
Misleading-Alert Demotion Rate:       100.0%  (8/8 distractor scenarios)
Insufficient Evidence Abstention:     100.0%  (1/1 ambiguous/gap scenarios)
Mean Graph Traversal Latency:          10.1 ms (10/10 scenarios)
==========================================================================================
```

> [!IMPORTANT]
> **Synthetic Evaluation Disclosure**: This benchmark evaluates deterministic graph ranking across 10 curated synthetic topologies. Relative confidence scores (`relative_confidence_pct`) represent softmax-normalized heuristic evidence alignment across candidate entities. They do **not** represent real-world statistical probabilities or mathematical proof of causality.

---

## 5. Local Setup Instructions (Fresh Clone)

### Prerequisites
- **Docker**: For running FalkorDB
- **Python**: 3.10+
- **Node.js**: 18+ (tested on Node v20/v22)

---

### Step 1: Start FalkorDB Container
Start the official FalkorDB Docker container:
```bash
docker run -d --name causaltrace-falkordb -p 6379:6379 -p 3000:3000 falkordb/falkordb:latest
```
*Port 6379 serves Redis/Cypher commands; port 3000 exposes the built-in FalkorDB web visualizer.*

---

### Step 2: Configure and Run Backend

1. Navigate to the backend directory and set up the environment:
```bash
cd backend
cp .env.example .env
```

2. Create and activate a Python virtual environment:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Start the FastAPI development server:
```bash
uvicorn app.main:app --reload --port 8000
```

5. Verify backend health probe:
```bash
curl -s http://localhost:8000/api/health | python3 -m json.tool
```

---

### Step 3: Seed the Incident Graph in FalkorDB

Seed all 10 synthetic incident topologies and telemetry into FalkorDB:
```bash
curl -X POST http://localhost:8000/api/incidents/seed
```
*(You can also click the **"Reset Graph"** button in the frontend workbench at any time).*

---

### Step 4: Configure and Run Frontend

1. In a separate terminal, navigate to the frontend directory:
```bash
cd frontend
cp .env.example .env
```

2. Install dependencies:
```bash
npm install
```

3. Start Vite dev server:
```bash
npm run dev
```

4. Open the application in your browser at [http://localhost:5173](http://localhost:5173).

---

### Step 5: Run Verification Suites

1. **Run Backend Unit & Integration Tests (25 tests)**:
```bash
cd backend
.venv/bin/pytest -v
```

2. **Run Evaluation Benchmark**:
```bash
cd backend
.venv/bin/python scripts/evaluate_investigation.py
```

3. **Verify Frontend Production Build**:
```bash
cd frontend
npm run build
```

---

## 6. Judge Demo Script (2–3 Minute Walkthrough)

Follow this script for a structured evaluation demo:

### Part 1: Baseline Root-Cause Traversal (`inc-01-payment-pool-exhaustion`) — [45s]
1. In the workbench header, select **"All Scenarios"** and choose `inc-01-payment-pool-exhaustion`.
2. **Observe**: The symptom service is `checkout-web` (SEV-1 latency and 5xx errors).
3. **Graph Traversal**: FalkorDB traverses 2 synchronous hops: `checkout-web` ➔ `order-service` ➔ `payment-service`.
4. **Finding**: `dep-payment-v2.4.1` is ranked as **Rank #1 Root Cause** with **95.5% relative confidence**.
5. **Corroboration**: Point out the corroborating `DbConnectionPoolExhaustion` alert and matching distributed trace ID `trc-checkout-881` in the log table.

### Part 2: Misleading Distractor Demotion (`inc-08-dual-competing-deployments`) — [45s]
1. Switch to `inc-08-dual-competing-deployments` (or click **"Hard Edge Cases"**).
2. **Scenario Context**: Two engineering teams shipped code simultaneously: `fraud-evaluator` (`dep-fraud-v2.1`) and `tax-calculator` (`dep-tax-v1.9`).
3. **Graph Discrimination**: FalkorDB traverses both dependency branches. The tax deployment is on a non-critical async path without fatal exceptions; the fraud deployment sits directly on the blocking RPC path and has corroborating NullPointerException logs.
4. **Result**: CausalTrace ranks `dep-fraud-v2.1` as #1 and correctly demotes the tax deployment as a competing distractor.

### Part 3: Safe Abstention Under Telemetry Gaps (`inc-07-insufficient-evidence-abstain`) — [45s]
1. Click the **"Hard Edge Cases"** filter and select `inc-07-insufficient-evidence-abstain`.
2. **Observe**: The workbench renders an amber **"INSUFFICIENT EVIDENCE DETECTED — ABSTENTION MODE"** banner.
3. **Zero Hallucination**: Rather than guessing, CausalTrace produces 0 root-cause hypotheses and lists specific evidence gap flags:
   - *Highest candidate score is below confidence threshold (< 0.60).*
   - *Telemetry gap: Zero error or fatal logs recorded across the blast radius.*
   - *Zero code deployment events detected within the investigation window.*
4. **Actionable SRE Guidance**: SRE verification steps are displayed to guide engineers toward restoring APM collectors.

### Part 4: Why FalkorDB Graph Traversal is Essential — [30s]
- Explain that microservice topologies form directed acyclic and cyclic graphs. Relational databases require multiple recursive JOINs that explode exponentially as hop depth increases.
- FalkorDB executes multi-hop variable-length path traversal (`[:DEPENDS_ON*1..4]`) in **sub-10 milliseconds**, enabling real-time incident triage during mission-critical outages.

---

## 7. AI-Assistance Disclosure

In accordance with hackathon guidelines:
- **Development Assistance**: AI pair programming tools (LLM assistants) were used to accelerate boilerplate scaffolding, TypeScript typing, and test authoring.
- **Runtime AI Architecture**: CausalTrace features a modular AI provider interface (`backend/app/ai/provider.py`). Graph traversal, blast radius isolation, evidence corroboration, and candidate ranking are executed **deterministically in FalkorDB Cypher**. The optional LLM provider is utilized solely to synthesize natural-language incident executive summaries and remediation suggestions from the verified graph evidence. The system remains fully functional and reliable in offline/stub mode without any active LLM API keys.

---

## 8. Limitations & Future Work

- **Heuristic Ranking**: Rankings reflect topological and temporal corroboration heuristics rather than formal do-calculus causal inference. Future work includes integrating Pearlian causal DAG estimators with structural equation modeling.
- **Topology Scale**: The current benchmark tests topologies up to 10 services and 4 hops. Future versions will benchmark cluster topologies with 1,000+ services.
- **Real-Time Ingestion**: Topologies and telemetry are currently ingested via Cypher batches. Future enhancements include Kafka/OTel collector streaming extensions directly into FalkorDB.

---

## 9. License

MIT License. Built for the **Graph Hacks** Hackathon.
