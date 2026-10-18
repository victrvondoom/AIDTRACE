# graph-hacks

> **WeMakeDevs × FalkorDB Graph Hacks (Oct 15–18, 2026)**  
> **Team Zero Degree (HBQZVK)** | Solo Architect: Pratham Dey (@prothamd)  
> Target Tracks: **Track 01 (Connected Data)** + **Track 02 (Memory & State)** + **Track 03 (Company Brain)**

---

## Project: BlastRadius — Autonomous FalkorDB Graph Intelligence

BlastRadius is an **autonomous codebase impact analysis, PR triage & SecOps agent** built on top of FalkorDB.

### Key Highlights
- **Track 01 (Connected Data):** Multi-hop reasoning across 5 native graph algorithm categories (PageRank, Betweenness Centrality, Shortest Paths / CVE exploit chains, Weakly Connected Components, Label Propagation / CDLP).
- **Track 02 (Memory & State):** Episodic memory, session handoffs, and procedural playbooks (`TriageAgent` $\to$ `RemediationAgent`).
- **Track 03 (Company Brain):** Developer ownership traversal, ADR governance, and incident retrospectives.
- **Frontend:** Next.js 15 UI with D3 force-graph visualization and dark glassmorphic styling.
- **Backend:** FastAPI + FastMCP suite running on port `8090`.

### Quick Navigation
- [`blastradius/`](blastradius/): Full project source code (backend, frontend, seeds, schema, and MCP server).
- [`blastradius/README.md`](blastradius/README.md): Detailed installation, architecture, and tool documentation.
- [`BlastRadius Master Engineering & Hackathon Blueprint.pdf`](BlastRadius%20Master%20Engineering%20%26%20Hackathon%20Blueprint.pdf): Hackathon architectural specification.
