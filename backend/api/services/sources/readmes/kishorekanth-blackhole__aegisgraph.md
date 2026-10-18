# AegisGraph: Autonomous Blast-Radius & Cascading Exploit Immunizer

[![FalkorDB](https://img.shields.io/badge/Graph_Database-FalkorDB_GraphBLAS-red.svg)](https://falkordb.com)
[![Hackathon](https://img.shields.io/badge/Hackathon-Graph_Hacks_Track_1-blue.svg)](https://wemakedevs.org)
[![Author](https://img.shields.io/badge/Author-Kishore_Kanth-purple.svg)](https://github.com/kishorekanth-blackhole)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **Submission for Graph Hacks: Context for AI Agents (Track 1: Agents That Act on Connected Data)**  
> **Lead Architect & Developer:** Kishore Kanth ([@kishorekanth-blackhole](https://github.com/kishorekanth-blackhole))  
> **Live Web App:** [AegisGraph Command Center](https://ais-pre-47k5ojpja734rsi23ogflm-637186347104.asia-southeast1.run.app)

---

## 1. Problem Statement & The Graph Difference

In enterprise cloud security and infrastructure, catastrophic breaches rarely happen in a single leap. Instead, attackers exploit **multi-hop transitive privilege combinations** (e.g. `Compromised Pod -> StagingServiceRole -> CrossAccountDeployer -> Production RDS Vault`).

### Why Traditional Vector RAG Fails:
- **Vector search** is designed for semantic keyword similarity.
- A staging pod has virtually **0.14 cosine similarity** to a production customer database vault.
- Vector RAG chunk retrieval is **100% blind to transitive graphs**, missing critical 3-to-5 hop attack chains and causing catastrophic blind spots.

### Why FalkorDB Wins:
- FalkorDB stores infrastructure relationships as a **sparse linear algebra adjacency matrix (GraphBLAS)**.
- Traverses complex multi-hop paths via `openCypher` in **under 8 milliseconds**.
- Enables autonomous agents to not just answer questions, but **execute topological mutations that self-heal compromised infrastructure**.

---

## 2. Multi-Scenario Topological Threat Lab

AegisGraph evaluates three real-world multi-hop graph domains:

1. **Cloud IAM Lateral Movement:** 3-hop AWS/Kubernetes `PassRole` escalation compromising 450,000 customer PII records.
2. **Fintech Anti-Money-Laundering (AML) Mule Ring:** 4-hop circular smurfing cycle draining capital through crypto DEX bridges to sanctioned vaults.
3. **Kubernetes Software Supply Chain Zero-Day:** 3-hop transitive dependency injection where a poisoned NPM package extracts cluster root KMS master keys.

---

## 3. Autonomous Multi-Agent Council Architecture

AegisGraph coordinates three specialized agents that act directly on FalkorDB:

1. 🔍 **Agent Alpha (Topological Recon Sentinel):** Ingests alerts and evaluates multi-hop reachability via `MATCH p = shortestPath(...)`.
2. 🛡️ **Agent Beta (Surgical Remediation Engine):** Calculates the **minimum graph cut** to sever the attack chain with 0 disruption to healthy services.
3. ⚖️ **Agent Gamma (Verification & Compliance):** Re-queries the graph to confirm 0 reachable paths remain and writes a cryptographic proof hash.

---

## 4. Key openCypher Queries

### A. Multi-Hop Shortest Path Detection
```cypher
MATCH (seed:Server {id: 'pod-staging-101'})
MATCH (crown:Resource {sensitivity: 'CRITICAL'})
MATCH path = shortestPath((seed)-[*1..4]->(crown))
RETURN [n in nodes(path) | n.name] as attackChain, length(path) as hops;
MATCH (s:Role {name: 'StagingServiceRole'})-[r:CAN_ASSUME]->(t:Role {name: 'CrossAccountDeployer'})
DELETE r
CREATE (s)-[:REVOKED_BY_AGENT {reason: 'PrivEsc Prevention', auditHash: '0x8a7f4c91'}]->(t)
MATCH (pod:Server {id: 'pod-staging-101'}) SET pod.status = 'QUARANTINED';
docker run -p 6379:6379 -it --rm falkordb/falkordb
pip install falkordb
python seed_graph.py
python agent_runner.py