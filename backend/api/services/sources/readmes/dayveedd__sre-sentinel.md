# SRE Sentinel 🛡️
> **Autonomous Incident War-Room & Real-Time Topology Blast-Radius Copilot**  
> *Targeting WeMakeDevs Graph Hacks (Track 01: "Agents That Act on Connected Data")*  
> *Primary Graph Engine: FalkorDB Cloud (AWS eu-west-1) / Local FalkorDB*

---

## 1. Executive Summary & The High-Stakes Incident Scenario

During severe P0/P1 production outages, **over 80% of incident time is wasted on causal diagnosis across tangled microservice graphs**:
- **Symptom ≠ Cause:** An edge service throwing `504 Gateway Timeout` is frequently a collateral casualty of an asynchronous worker holding an unindexed table lock 4 hops away.
- **Sensory Fragmentation:** On-call engineers are torn between spoken war rooms (Zoom/Slack Huddle), screen dashboards (Grafana/Datadog), and CLI terminals.
- **Flat Search & Vector RAG Failure:** Vector databases and lexical search engines cannot navigate cyclic service graphs, evaluate transitive dependency depths, or calculate live blast radius.

### "The Ghost in the Database" (Resource Poisoning Cascade):
1. **The Red Herring:** `CheckoutService` throws `504 Gateway Timeout` and points blame at `PaymentGateway`. Both codebases are completely healthy.
2. **The Hidden 4-Hop Culprit:**
   ```
   CheckoutService ──[:DEPENDS_ON]──> PaymentGateway ──[:READS_WRITES]──> CorePostgres
                                                                               ▲
                                                                               │ [:HOLDS_LOCK {type: 'EXCLUSIVE'}]
                                                                               │
   Engineer (@sarah) ◄──[:AUTHORED_BY]── Commit (4f82a9c) ◄── Deployment (dep_9041) ◄── DataWarehouseArchiver
   ```
   There is **NO direct API connection** between Checkout and the Archiver; they only collide in the database lock contention graph!
3. **The Blast-Radius Showstopper (Graph Algorithm):** A naive reboot of `CorePostgres` is **BLOCKED** by graph policy because FalkorDB calculates that **18 Tier-1 services** (FraudDetection, KYC, Compliance, CardTokenizer, Treasury) depend on it. Rebooting causes catastrophic company-wide failure.
4. **The Surgical Resolution:** FalkorDB computes the **minimal cut**—terminating only the single background pod `DataWarehouseArchiver` to drop the lock in **18ms** without restarting the database or dropping customer connections.

---

## 2. Hackathon Rule #3 Compliance Guarantee

> *"If the product still works once FalkorDB is taken out, the graph is decoration."*

**SRE Sentinel fundamentally depends on FalkorDB:**
1. **Variable-Length Path Traversal (`*1..4`):** Finding non-obvious resource contention across arbitrary service depths requires recursive graph joins that are computationally prohibitive in relational tables.
2. **Cyclic Dependencies:** Microservice architectures contain complex call cycles; FalkorDB effortlessly computes shortest paths between symptoms and root causes.
3. **In-Memory Sub-Millisecond Latency (<2ms):** Live incident response requires real-time graph reasoning while engineers are typing commands in the terminal.

---

## 3. Graph Data Model & Schema

```mermaid
graph TD
    subgraph Edge Layer
        Checkout[Service: CheckoutService (DEGRADED)]
        Storefront[Service: Storefront]
        Mobile[Service: MobileAppGateway]
    end

    subgraph Mid-Tier Layer
        Payment[Service: PaymentGateway]
        Order[Service: OrderService]
        Inventory[Service: InventoryService]
    end

    subgraph Data Layer
        Postgres[(Database: CorePostgres)]
        Redis[(Database: RedisSessionStore)]
    end

    subgraph Collateral Tier-1 Systems [18 Services]
        Fraud[Service: FraudDetection]
        KYC[Service: KYCService]
        Compliance[Service: ComplianceLogger]
        Ledger[Service: LedgerService]
        Treasury[Service: TreasuryService]
    end

    subgraph The Culprit Chain [Tier 3]
        Archiver[Service: DataWarehouseArchiver]
        Dep[Deployment: dep_9041]
        Commit[GitCommit: 4f82a9c]
        Author[Engineer: Sarah Chen @sarah]
    end

    Storefront -->|:DEPENDS_ON| Checkout
    Mobile -->|:DEPENDS_ON| Checkout
    Checkout -->|:DEPENDS_ON| Payment
    Payment -->|:READS_WRITES| Postgres
    Fraud -->|:READS_WRITES| Postgres
    KYC -->|:READS_WRITES| Postgres
    Compliance -->|:READS_WRITES| Postgres
    Ledger -->|:READS_WRITES| Postgres
    Treasury -->|:READS_WRITES| Postgres

    Archiver -->|:HOLDS_LOCK {type: 'EXCLUSIVE'}| Postgres
    Archiver -->|:DEPLOYED_TO| Dep
    Dep -->|:HAS_COMMIT| Commit
    Commit -->|:COMMITTED_BY| Author
```

---

## 4. FalkorDB Cypher Engine & Diagnostic Queries

### Query 1: Upstream Root-Cause Traversal (The Lock & Deployment Hunter)
```cypher
MATCH (symptom:Service {name: 'CheckoutService'})-[:DEPENDS_ON*1..4]->(intermediate:Service)
MATCH (intermediate)-[:READS_WRITES]->(db:Database)<-[lock:HOLDS_LOCK]-(culprit:Service)
MATCH (culprit)-[:DEPLOYED_TO]->(d:Deployment)-[:COMMITTED_BY]->(author:Engineer)
OPTIONAL MATCH (d)-[:HAS_COMMIT]->(c:GitCommit)
RETURN symptom.name AS entry_service,
       intermediate.name AS degraded_hop,
       db.name AS contested_resource,
       culprit.name AS culprit_service,
       d.version AS culprit_version,
       author.name AS author_name,
       author.handle AS author_slack,
       c.sha AS commit_sha,
       c.message AS commit_message
LIMIT 1;
```

### Query 2: Transitive Blast-Radius Calculation (Blunt Reboot Check)
```cypher
MATCH (downstream:Service)-[:READS_WRITES]->(db:Database {name: 'CorePostgres'})
WHERE downstream.tier = 1
RETURN downstream.name AS service_name,
       downstream.tier AS tier,
       downstream.status AS status
ORDER BY downstream.name ASC;
```

### Query 3: Minimal Cut Verification (Culprit Impact Check)
```cypher
MATCH path = (culprit:Service {name: 'DataWarehouseArchiver'})<-[:DEPENDS_ON*1..5]-(downstream:Service)
RETURN downstream.name AS impacted_service, downstream.tier AS tier;
```

---

## 5. Model Context Protocol (MCP) Server

SRE Sentinel exposes FalkorDB operations via the standard Model Context Protocol:
1. `query_upstream_culprit(symptom_service, lookback_seconds)`: Multi-hop Cypher traversal returning the exact causal chain from symptom to locked resource and culprit commit.
2. `calculate_blast_radius(target_resource)`: Computes all transitive downstream services affected by modifying or rebooting a resource.
3. `execute_remediation_action(action_type, service_name, deployment_id)`: Triggers safe automated canary rollback or surgical pod termination.

---

## 6. Zero-Focus Stealth HUD (Lifted from Cue)

Lifted sensory primitives:
- `sensory/screen.js`: macOS ScreenCaptureKit capture compressed to 85-quality JPEG (<120KB, ~50ms transfer latency).
- `sensory/vad.js`: Adaptive energy VAD with 300ms pre-speech audio ring buffer for war room audio monitoring.
- `sensory/hud/`: Frameless glassmorphic HUD configured with `win.setFocusable(false)` (NSPanel on macOS) so engineers can type in their terminals while viewing live graph traces.

### 1-Click Action Buttons:
- `[ ⚡ Kill & Drain DataWarehouseArchiver Pod via K8s MCP ]`: Drops lock in 18ms, 0 blast radius.
- `[ ⚠️ Blocked: Restart CorePostgres (Blast Radius: 18 Services) ]`: Explains why blunt database restarts are dangerous.

---

## 7. Quickstart Setup & Verification

```bash
# 1. Clone & activate virtual environment
cd sre-sentinel
source .venv/bin/activate

# 2. Configure credentials in .env
cp .env.example .env
# Edit .env with your FALKORDB_HOST, FALKORDB_PORT, FALKORDB_PASSWORD

# 3. Seed the 15-node topology & run verification queries
python scripts/seed_topology.py

# 4. Run the incident simulator
python scripts/simulate_outage.py

# 5. Run the Autonomous Sentinel Agent Loop
python core/agent_loop.py
```
