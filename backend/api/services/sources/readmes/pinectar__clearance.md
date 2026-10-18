# Clearance

**Name search finds "Kane Logistics". Clearance finds the subsidiary suing your client two hops away, and won't open the matter until a lawyer signs the path it drew.**

**Live:** https://clearance-chi.vercel.app (opens signed out, seeded) · **Product story:** [clearance-chi.vercel.app/about](https://clearance-chi.vercel.app/about) · **Stack:** FalkorDB + Next.js

![The matter report: drawn conflict paths with provenance beside the name-search baseline](docs/matter-report.png)

Conflicts of interest are a leading cause of legal-malpractice claims, and most small firms still check them with a shared spreadsheet and memory. Clearance is a conflicts-of-interest gate: the firm's history lives in a FalkorDB graph, a new inquiry is checked by deterministic multi-hop traversal, and the matter stays blocked until an attorney signs the drawn risk. The signature, the wall and every resolved identity are written back: the graph is the firm's record.

Built for **Graph Hacks: Context for AI Agents** (WeMakeDevs × FalkorDB, Oct 15-18 2026). Tracks: **Agents That Act on Connected Data**, **Agent Memory and Coordination**, and **Company Brain**. This repository was created on 15 Oct 2026, inside the event window; no project code predates the start. The first commit (c4138e4) is timestamped Thu 15 Oct 16:59 +05:30 (2026-10-15T11:29:35Z), after the build opened at Thu 15 Oct 00:01 +05:30. Idea notes and graph-model sketches (allowed before the start by Rule 8) live outside this repository.

## The graph data model (Rule 10)

One FalkorDB graph per firm (`firm_demo` in the demo; multi-graph tenancy is the isolation story).

```
(:Person|:Org {key, name})          people and organisations, incl. attorney-confirmed alias nodes
(:Attorney {key, name})             the firm's lawyers
(:Matter {key, name, year})         the firm's historical matters
(:Intake {key, title, status, report})   new inquiries and their full reports (the gate's record)
(:Clearance {key, by, at, action, pathsSeen})   a signed decision, write-once
(:Wall {key, by, at})               an approved ethical wall

(a)-[:ALIAS_OF {source, since}]->(b)        renames + attorney resolutions (ask-once memory)
(a)-[:SUBSIDIARY_OF {source, since}]->(b)   corporate family
(a)-[:RELATED_TO {relType: family|officer, source, since}]->(b)
(e)-[:CLIENT_IN|ADVERSE_IN|WITNESS_IN|DECLINED_CONSULT {source, since}]->(:Matter)
(:Attorney)-[:WORKED_ON {source, since}]->(:Matter)
(:Wall)-[:GUARDS]->(:Intake)  (:Wall)-[:SCREENED_BY]->(:Attorney)  (:Wall)-[:AROUND]->(:Matter)
(:Clearance)-[:CLEARS]->(:Intake)
```

**Every edge carries provenance** (`source`: the record that established it; `since`). A conflict verdict is a path, and every hop of it can say where it came from.

## The Cypher the product depends on (Rule 10)

1. **Direct conflicts**: a party's own matter history.
```cypher
MATCH p = (a {key: $key})-[t:CLIENT_IN|ADVERSE_IN|WITNESS_IN|DECLINED_CONSULT]->(m:Matter)
RETURN p, type(t) LIMIT 50
```
2. **Indirect conflicts (the wedge)**: variable-length traversal through aliases, corporate families and personal relationships to the firm's history; this is the path a name search cannot see:
```cypher
MATCH p = (a {key: $key})-[:ALIAS_OF|SUBSIDIARY_OF|RELATED_TO*1..2]-(b)-[t:CLIENT_IN|ADVERSE_IN|DECLINED_CONSULT]->(m:Matter)
WHERE id(a) <> id(b)
RETURN p, type(t) LIMIT 50
```
3. **Wall enforcement**: a standing ethical wall downgrades later findings on the same matter:
```cypher
MATCH (w:Wall)-[:AROUND]->(m:Matter {name: $m})
OPTIONAL MATCH (w)-[:SCREENED_BY]->(a:Attorney)
RETURN w.by, w.at, collect(a.name) LIMIT 5
```
4. **The baseline shown beside it**: the incumbent, a literal name search (deliberately weak; this is the product with FalkorDB taken out, Rule 3):
```cypher
MATCH (e)-[:CLIENT_IN|ADVERSE_IN|WITNESS_IN|DECLINED_CONSULT]->(m:Matter)
WHERE toLower(e.name) CONTAINS toLower($q) RETURN DISTINCT e.name LIMIT 25
```
5. **Ask the firm** (institutional memory as parameterised templates, e.g. "who has ever touched a Meridian entity?"):
```cypher
MATCH (o) WHERE toLower(o.name) CONTAINS toLower($param)
MATCH (o)-[:ALIAS_OF|SUBSIDIARY_OF*0..2]-(fam)
MATCH (fam)-[t:CLIENT_IN|ADVERSE_IN|DECLINED_CONSULT|WITNESS_IN]->(m:Matter)
OPTIONAL MATCH (att:Attorney)-[:WORKED_ON]->(m)
RETURN fam.name, type(t), t.source, m.name, att.name LIMIT 30
```
All reads run through `GRAPH.RO_QUERY` with a 3-second timeout and a bounded-result guard (`npm run lint:graph` enforces that no query bypasses the graph layer).

## The agent loop (and the human gate)

Clearance is an agent with one irreversible action, opening a matter, and a human gate in front of it. The loop: an intake note is ingested, parties are extracted, identities are resolved against the firm graph (an ambiguity asks a human once and is remembered forever as an `ALIAS_OF` edge), the graph is traversed for conflict paths, the matter is **blocked**, an attorney signs clear / decline / wall, and the decision is written back, so every future check knows what this one learned. Memory here changes future *verdicts*, not future chats: an approved ethical wall visibly annotates later checks, and a resolved alias never asks again, for any attorney at the firm.

## Where the model is, and where it is not

The LLM does exactly one job: reading the parties out of a messy intake note (`src/lib/extract.ts`). The deployed demo runs live extraction (Qwen2.5-72B via Featherless, capped per day); a deterministic mock ships for key-free local runs and is the fallback beyond the cap. `/api/health` reports which is live. Everything that decides is model-free and replayable: entity resolution is three auditable rules (an exact normalized name auto-matches; a shared surname with matching initials, or an org name whose every word appears in a record's name, asks the attorney once and is remembered as an `ALIAS_OF` edge; everything else is new), and the verdict is the traversal above. The model cannot talk the gate open: uncertain identity blocks, a graph outage blocks, and only a signature clears.

## Run it

```bash
npm install
export FALKORDB_URL=falkor://:<password>@<host>:<port>   # FalkorDB Cloud free tier, or local Docker
npm run seed        # deterministic synthetic firm: ~120 entities, ~40 matters, planted conflicts
npm run dev         # http://localhost:3000
npm run eval        # planted-conflict recall: graph vs name search, one command
npm test            # unit suite;  npm run test:int needs FALKORDB_URL
```
Optional: `FEATHERLESS_API_KEY` or `ANTHROPIC_API_KEY` for live extraction (`LLM_MODEL` picks the model, default `Qwen/Qwen2.5-72B-Instruct`; `EXTRACTOR=mock` forces the deterministic mock; live calls are capped per day), `RESET_TOKEN` to enable `POST /api/admin/reset`.

## Honest limits

- The demo firm is **synthetic** (Rule 6 bars real client data; law-firm records are confidential by nature). `npm run eval` runs a **seeded demonstration corpus**, not an independent benchmark: the generator is deterministic and the planted-conflict manifest is public in `src/lib/corpus-spec.ts`, so the result is reproducible by one command, and honestly framed: the 4 conflicts name search misses are *structural* (they exist only as graph edges a literal search cannot see), not statistical.
- Relationship-aware conflicts exist at enterprise price: Intapp buys corporate-tree data and sells to big law. Agentic checkers exist too: Gamut's intake template searches Clio/PACER in parallel and lets a model sort findings into tiers. Clearance's claim is the method at the small-firm scale: the firm's **own** provenance graph, deterministic replayable verdicts, a fails-closed gate, and ask-once memory. Gamut searches more places; Clearance proves the verdict.
- Rate limits are in-memory per instance (fine for a demo; a real deployment would move them to the graph).
- No auth by design: judges must not sign in. A real firm deployment would add it.

## Build notes

How this was built, including the two failures that shaped the design (an embedding matcher that collapsed at production directory size, and a process that printed PASS and never exited): [docs/blog.md](docs/blog.md). Decision records and the failure log live in [docs/memory/](docs/memory/).

## AI-tool disclosure (Rule 11)

Built with Claude Code (planning, code, tests, review); all graph modelling, queries and architecture decisions are documented in `ARCHITECTURE.md` and explained in the demo. The demo video is narrated by a synthetic voice (neural TTS) reading the author's script, with burned-in captions. The authors can walk through every Cypher query above (Rule 12).
