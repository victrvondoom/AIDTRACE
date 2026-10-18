# Refusal Agent — an agent that acts on a FalkorDB call graph

**Graph Hacks 2026 (WeMakeDevs × FalkorDB) — Track: Agents That Act on Connected Data**

> An agent that reads a protocol's call graph, finds the path a real exploit
> took, and refuses to certify the contract until that path is closed.

Most graph demos answer questions about a graph. This agent **walks** the
graph and **acts** on what the walk finds: when a contract's call graph
contains a route whose weakness was used in a real exploit, the agent does
not warn, does not score — it **refuses to certify** and files a
`BLOCKED` CertificationRequest *on the graph itself*, linked to the exact
path that blocked it.

Remove FalkorDB and the product dies: "walk outward from this function,
match what you reach against real exploit shapes, and file a node on the
graph" has no table-store equivalent. The removal test passes.

---

## The agent loop

```
OBSERVE   given a contract it has not seen
   ↓      entry functions: MATCH (c:Contract)-[:HAS_FUNCTION]->(f)
TRAVERSE  walk CALLS edges outward, up to 6 hops, collecting every route
   ↓      MATCH p = (a:Function)-[e:CALLS*1..6]->(b) RETURN path
DETECT    a route blocks if any node on it carries a vulnerability whose
   ↓      SWC was used in a REAL exploit (HAS_VULNERABILITY → EXPLOITED_BY)
ACT       file CertificationRequest{status: BLOCKED} on the graph,
   ↓      linked via BLOCKED_BY_PATH to the exact functions
RECORD    the filed request is replayable: reload it, re-run the same
          traversal, get the same verdict — the evidence is on the graph,
          not in a log
```

## Quick start

```bash
# 1. FalkorDB (Docker), Cypher on host port 6381
docker run -d --name graphhacks-agent -p 6381:6379 falkordb/falkordb:latest

# 2. dependencies
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. seed the graph (public dataset: SWC registry + exploit post-mortems)
python3 -m data.seed --force

# 4. run the agent over a batch of contracts
python3 -m agent.refusal_agent

# 5. full end-to-end verification (seeds, reviews, files, replays, asserts)
python3 -m agent.verify
```

## Repository layout

```
data/
  contracts.py        # 23 contracts, 76 functions, 34 CALLS edges, libraries, auditors
  vulnerabilities.py  # 20 SWC patterns (swcregistry.io)
  exploits.py         # 10 real exploits: year, loss, chain, techniques
  seed.py             # two-pass FalkorDB seeder (nodes first, then edges)
agent/
  refusal_agent.py    # the agent: observe → traverse → detect → act → record
  replay.py           # re-derive a filed verdict from the stored evidence path
  verify.py           # end-to-end test suite against the live DB
```

## Data model

```
(Contract)-[:HAS_FUNCTION]->(Function)
(Function)-[:CALLS]->(Function)                # the call graph the agent walks
(Function)-[:HAS_VULNERABILITY {source, status}]->(Vulnerability)
(Vulnerability)-[:EXPLOITED_BY]->(Exploit)     # this SWC appears in a real exploit
(Contract)-[:USES_LIBRARY]->(Library)
(Auditor)-[:AUDITED]->(Contract)

# written by the agent:
(CertificationRequest {request_id, agent_id, status, reason, paths_examined,
                       paths_blocked, exploits_matched, filed_at, evidence_json})
(CertificationRequest)-[:FILED_AGAINST]->(Contract)
(CertificationRequest)-[:BLOCKED_BY_PATH {function}]->(Function)
```

**Sources (public data, allowed by the rules):** Smart Contract Weakness
Classification registry (swcregistry.io), public exploit post-mortems
(amounts and dates from public reporting), public contract metadata.
`HAS_VULNERABILITY.status` distinguishes evidence strength:
`exploited` (post-mortem confirmed) / `pattern` (detector-flagged) /
`theoretical` / `patched`.

## The Cypher that does the work

**1. Traverse** — every call route up to 6 hops from an entry function:

```cypher
MATCH p = (a:Function {name: $fn})-[e:CALLS*1..6]->(b:Function)
RETURN length(p) AS hops,
       [n IN nodes(p) | n.name] AS path,
       [n IN nodes(p) | n.contract] AS contracts
```
A traversal, not a lookup: the result is the set of *routes*, each with its
path list. (Dialect note: the hop bound must be a literal — a parameterized
`*1..$hops` fails with "Encountered unhandled type in inlined properties",
so it is expanded from validated Python.)

**2. Detect** — two-hop join per node on a path: function → vulnerability →
the real exploits that used it:

```cypher
UNWIND $path AS fname
MATCH (f:Function {name: fname})-[hv:HAS_VULNERABILITY]->(v:Vulnerability)
WHERE hv.status IN ['exploited', 'pattern']
OPTIONAL MATCH (v)-[:EXPLOITED_BY]->(e:Exploit)
RETURN fname, v.swc, v.title, v.severity, hv.status,
       collect(DISTINCT e.name) AS exploits, collect(DISTINCT e.loss_usd) AS losses
```
A row with no `exploits` is theoretical noise — the agent drops it. Only a
pattern that a real exploit actually used blocks certification.

**3. Library correlation** — Library → Contract → Function → Vulnerability →
Exploit, a four-hop join:

```cypher
MATCH (c:Contract {name: $contract})-[:USES_LIBRARY]->(l:Library)
MATCH (other:Contract)-[:USES_LIBRARY]->(l)
MATCH (other)-[:HAS_FUNCTION]->(of:Function)
MATCH (of)-[hv:HAS_VULNERABILITY]->(v:Vulnerability)-[:EXPLOITED_BY]->(e:Exploit)
WHERE hv.status = 'exploited'
RETURN l.name, collect(DISTINCT e.name), count(DISTINCT e) ORDER BY count(DISTINCT e) DESC
```

## Verified behavior (live FalkorDB, `python3 -m agent.verify`)

- Graph: **144 nodes, 217 edges** (23 contracts, 76 functions, 34 CALLS, 20
  vulnerabilities, 10 exploits, 10 libraries, 5 auditors)
- **12 contracts BLOCKED** with named evidence, e.g.
  `KyberSwapPool`: path `convertWithSlippage → getAmountsOut` blocked by
  SWC-128 Oracle Manipulation — the exact technique of the KyberSwap flash
  loan attack ($307M), Cream, Mango, Beanstalk, Euler ($928M combined)
- **4 contracts CERTIFIED**: no route reaches a vulnerability with a real
  exploit behind it (a theoretical SWC-103 pattern on UniswapV2Router02 does
  not block — no exploit used it)
- **Replay**: every filed BLOCKED request re-derives the same verdict
  (`match: true`)
- **Idempotent**: re-reviewing updates the request in place, no duplicates

## What this is not

- Not a vulnerability scanner: no source is analyzed, no chain is contacted.
  The agent reasons over the graph's recorded evidence and refuses when the
  evidence says to.
- Not a live audit tool: the dataset is public post-mortem data seeded into
  FalkorDB. Ingestion from Etherscan/Slither was explicitly out of scope.

## AI assistance disclosure

This project was built with AI coding assistance (Hermes Agent), disclosed
per the hackathon rules. Every query, schema decision, and verdict rule was
reviewed and verified against a live FalkorDB; the end-to-end suite
(`agent/verify.py`) is the proof it works as claimed.


---
Submitted to Graph Hacks 2026 via WeMakeDevs on 2026-10-17.
