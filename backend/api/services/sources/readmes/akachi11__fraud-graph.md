# FraudGraph

**AI-powered fraud investigation agent that reasons over connected financial data using FalkorDB graph database.**

Built for [Graph Hacks: Context for AI Agents](https://graphhacks.devpost.com/) — Track 1: Agents That Act on Connected Data.

> **Live Demo:** [fraud-graph-self.vercel.app](https://fraud-graph-self.vercel.app)

---

## What It Does

FraudGraph is an AI agent that investigates financial fraud by traversing a graph of accounts, transactions, merchants, and devices. Ask it to investigate an account, and it will:

1. **Query the graph** — pull account details, transaction history, device fingerprints
2. **Trace money flows** — follow multi-hop paths through the transaction network to detect layering and circular flows
3. **Detect patterns** — identify structuring (amounts just below reporting thresholds), velocity anomalies, device sharing, geo mismatches
4. **Take action** — flag suspicious accounts, escalate fraud cases, create alerts — all written back to the graph
5. **Explain its reasoning** — every finding is presented with the graph paths that led to it

The graph visualization updates in real-time as the agent investigates, highlighting the nodes and connections under scrutiny.

## Why Graph?

Fraud hides in connections. A traditional database sees individual transactions. A graph database sees the **network** — that Viktor and Olga share a device registered in a different country, that money flows in circles between three accounts, that five "unrelated" people all transact at the same shell company.

FalkorDB makes these multi-hop traversals fast. The agent's tools wrap Cypher queries that would be expensive joins in SQL but are native operations in a graph.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Next.js App                          │
│                                                         │
│  ┌──────────────┐    ┌──────────────────────────────┐   │
│  │  Chat Panel   │    │    Graph Canvas (Canvas 2D)  │   │
│  │  useChat hook │◄──►│    Force-directed simulation │   │
│  └──────┬───────┘    └──────────────────────────────┘   │
│         │                                               │
│  ┌──────▼───────┐                                       │
│  │  /api/chat    │  AI Agent (Gemini + 7 tools)         │
│  │  ToolLoopAgent│──────────────────────┐               │
│  └──────┬───────┘                      │               │
│         │                              │               │
│  ┌──────▼───────┐               ┌──────▼──────┐        │
│  │  /api/graph   │               │  /api/seed   │        │
│  └──────┬───────┘               └──────┬──────┘        │
└─────────┼──────────────────────────────┼────────────────┘
          │                              │
   ┌──────▼──────────────────────────────▼──────┐
   │              FalkorDB (Graph DB)            │
   │         Cypher queries over Redis           │
   └────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│              MCP Server (stdio)                         │
│  Same 7 tools + 2 resources exposed via MCP protocol   │
│  Any MCP-compatible agent (Claude, Cursor, etc.) can    │
│  connect and investigate fraud through the graph        │
└─────────────────────────────────────────────────────────┘
```

## Track 1 Criteria

| Criteria | How FraudGraph Addresses It |
|---|---|
| **Multi-hop reasoning** | `trace_money_flow` follows 1-4 hop chains through Account→Transaction→Account paths. Circular flow detection finds money returning to its origin. |
| **Graph queries as agent tools** | 7 tools wrap Cypher queries: `query_graph`, `investigate_account`, `trace_money_flow`, `detect_patterns`, `flag_account`, `escalate_case`, `get_graph_schema` |
| **Tool selection through MCP** | Standalone MCP server exposes all tools via stdio transport. Any MCP client discovers and selects them. |
| **Actions based on graph data** | `flag_account` updates risk scores and creates alerts. `escalate_case` creates FraudCase nodes and links suspect accounts. Both write back to the graph. |
| **Explainable results** | Agent produces markdown reports with tables showing the graph paths it traversed and the evidence at each hop. |

## Graph Schema

```
(Account)-[:SENT]->(Transaction)-[:RECEIVED_BY]->(Account)
(Transaction)-[:AT]->(Merchant)
(Account)-[:USES]->(Device)
(Account)-[:FLAGGED_IN]->(FraudCase)
(Account)-[:HAS_ALERT]->(Alert)
(Account)-[:SHARES_DEVICE]->(Account)
```

**6 node types:** Account (30), Transaction (167), Merchant (26), Device (20), FraudCase (4), Alert (3)

**4 injected fraud patterns:** money laundering ring, identity theft cluster, card fraud network, synthetic identity ring

## Agent Tools

| Tool | Type | Description |
|---|---|---|
| `query_graph` | Read | Execute any Cypher query against the fraud graph |
| `investigate_account` | Read | Deep dive — account details, transactions, devices, fraud cases, alerts, shared devices |
| `trace_money_flow` | Read | Multi-hop money chain traversal with circular flow detection |
| `detect_patterns` | Read | 6 pattern detectors: shared devices, high-risk merchants, structuring, velocity, geo mismatch, new accounts |
| `get_graph_schema` | Read | Live node/relationship counts |
| `flag_account` | **Write** | Update risk score/status, create alert node |
| `escalate_case` | **Write** | Create FraudCase node, link to suspect accounts |

## Getting Started

### Prerequisites

- Node.js 20+
- Docker (for FalkorDB)
- [Google AI API key](https://aistudio.google.com/apikey)

### Setup

```bash
# Clone the repo
git clone https://github.com/akachi11/fraud-graph.git
cd fraud-graph

# Install dependencies
npm install

# Start FalkorDB
docker run -p 6379:6379 -it --rm falkordb/falkordb

# Configure environment
cp .env.example .env.local
# Edit .env.local with your Gemini API key

# Start the dev server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) and click **Seed Data** to populate the graph with synthetic fraud data.

### MCP Server

The MCP server exposes the same tools for any MCP-compatible AI agent:

```bash
npm run mcp
```

Add to your MCP client config (e.g., Claude Desktop):

```json
{
  "mcpServers": {
    "fraudgraph": {
      "command": "npx",
      "args": ["tsx", "mcp-server.ts"],
      "cwd": "/path/to/fraud-graph",
      "env": {
        "FALKORDB_HOST": "localhost",
        "FALKORDB_PORT": "6379"
      }
    }
  }
}
```

## Tech Stack

- **Graph Database:** [FalkorDB](https://www.falkordb.com/) — open-source graph DB, Cypher queries over Redis
- **AI:** [Vercel AI SDK v7](https://sdk.vercel.ai/) — ToolLoopAgent with streaming UI
- **LLM:** Google Gemini 3.5 Flash
- **Frontend:** Next.js 16, React 19, Tailwind CSS 4
- **MCP:** Model Context Protocol SDK — stdio server with Zod schemas
- **Visualization:** Custom force-directed graph on Canvas 2D

## Key Cypher Queries

The agent's tools wrap these Cypher queries against FalkorDB:

**Circular Flow Detection (3-hop, temporal ordering):**
```cypher
MATCH (a:Account {id: $id})-[:SENT]->(tx1:Transaction)-[:RECEIVED_BY]->(b:Account)
      -[:SENT]->(tx2:Transaction)-[:RECEIVED_BY]->(c:Account)
      -[:SENT]->(tx3:Transaction)-[:RECEIVED_BY]->(a)
WHERE tx2.timestamp > tx1.timestamp AND tx3.timestamp > tx2.timestamp
RETURN a.name, b.name, c.name, tx1.amount, tx2.amount, tx3.amount,
       tx1.timestamp, tx2.timestamp, tx3.timestamp
```

**Multi-hop Money Flow Tracing (2 hops with temporal ordering):**
```cypher
MATCH (start:Account {id: $id})-[:SENT]->(tx1:Transaction)-[:RECEIVED_BY]->(a2:Account)
      -[:SENT]->(tx2:Transaction)-[:RECEIVED_BY]->(a3:Account)
WHERE tx2.timestamp > tx1.timestamp
RETURN start.name, a2.name, a3.name, tx1.amount, tx2.amount,
       tx1.timestamp, tx2.timestamp, a2.risk_score, a3.risk_score
```

**Structuring Detection (below reporting thresholds):**
```cypher
MATCH (a:Account)-[:SENT]->(tx:Transaction)
WHERE (tx.amount >= 4500 AND tx.amount < 5000)
   OR (tx.amount >= 9000 AND tx.amount < 10000)
RETURN a.id, a.name, tx.amount, tx.timestamp, tx.type
ORDER BY tx.amount DESC
```

**Shared Device Detection:**
```cypher
MATCH (a1:Account)-[:SHARES_DEVICE]->(a2:Account)
MATCH (a1)-[:USES]->(d:Device)
RETURN a1.name, a2.name, d.fingerprint, d.type, d.is_vpn, d.country
```

**Geographic Mismatch:**
```cypher
MATCH (a:Account)-[:USES]->(d:Device)
WHERE a.country <> d.country
RETURN a.name, a.country, d.country, d.is_vpn, d.ip_address
```

## Example Queries

- "Investigate Priya Miller's account for fraud"
- "Show me all accounts sharing devices"
- "Are there any money laundering patterns?"
- "Trace money flow from Priya Miller with 3 hops"
- "Which accounts have transactions at shell companies?"
- "Detect structuring patterns across all accounts"

## License

MIT
