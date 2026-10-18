# Pathflip

**Pathflip** is a small web app that shows an idea's influence paths on one side of a scale and the strongest counter-path on the other. Stamp a counter as accepted, or nudge any edge weight, and the ranking is re-run and the scale tips in front of you.

All of it runs on **FalkorDB**. The influence graph, every weight, every stamp, the edit log and the revision counter live in one FalkorDB graph. Finding paths, ranking them and finding counter-paths are Cypher queries. The Python server only wraps them in JSON, and if FalkorDB goes away the API returns `503` and the product stops (there is a test for that).

## Track 1: Agents That Act on Connected Data

Pathflip is now a small **agent that reasons over a FalkorDB graph and acts on what the graph shows**. One flow:

1. Pick a claim (the 4 clash presets: Keynesian Economics, Empiricism, Marxism, Behaviorism) or type a Person/Idea.
2. The agent runs and you watch it call graph tools in the **Trace panel**.
3. It returns a **verdict** (CLAIM STANDS / COUNTER WINS), the **evidence path**, and a short **cited memo** (every clause cites the `source` stored on a graph edge).
4. The agent names the one counter-argument whose acceptance would hurt the claim most (found by what-if queries in FalkorDB). **Stamp it**: the agent re-runs, the verdict flips live (existing flip animation), and the memo is regenerated.

![agent trace, flipped verdict and updated memo](docs/agent-flip.png)

### Agent tools (one registry, used by the web UI and by `/mcp`)

| Tool | What FalkorDB does |
|---|---|
| `strongest_support_path` | variable-length Cypher path search, per-hop discounted score, best path per origin, top 3 |
| `strongest_counter_edge` | counter-paths (a `COUNTERED` edge landing on the claim or on something that feeds it), then a **what-if per candidate edge**: the same query is re-run with that edge stamped, and the edge with the biggest counter total is recommended (`would_flip` says whether it flips the verdict) |
| `shortest_path` | FalkorDB `shortestPath()` over `INFLUENCED\|COUNTERED`, fewest hops from the counter's origin to the claim |
| `influence_rank` | **`CALL algo.pageRank(null, 'INFLUENCED')` computed inside FalkorDB**. If an instance lacks the algo library the tool falls back to a Cypher weighted in-degree and the trace says `FALLBACK` (covered by a test). The hosted FalkorDB Cloud instance supports `algo.pageRank`, so the live site runs real PageRank |
| `resolve_claim` | name to node (internal step 1) |

Tool selection is a deterministic policy (no LLM, no API key): resolve, support path, counter edge, then `shortest_path` if a counter exists, then `influence_rank` on the winning evidence. The verdict is simply which side's FalkorDB total is larger; the memo is a template filled from tool outputs, so it cannot say anything the graph did not return.

### Trace

Every tool call is logged with: step, tool and args, **why it was chosen**, the **Cypher FalkorDB ran** (click to expand in the UI), the engine used, the **nodes touched**, and **timing in ms**. The same trace is returned by `GET /api/agent?q=<claim>` (`agent.trace`) and by the MCP tools.

### MCP

`POST /mcp` (JSON-RPC) lists and calls: `strongest_support_path`, `strongest_counter_edge`, `shortest_path`, `influence_rank`, `analyze_claim` (the whole agent: verdict, evidence path, memo, trace, `recommended_stamp`), `stamp_counter` (the action: accept a counter edge by `eid`), plus the original `find_paths`, `find_counter_paths`, `balance`. Tool arguments accept names as well as keys. An external agent can therefore do `analyze_claim` -> `stamp_counter` -> `analyze_claim` and see the verdict flip.

```bash
curl -s localhost:8000/api/agent?q=Keynesian%20Economics | jq '.agent | {verdict, tools: [.trace[].tool], rec: .recommended_stamp.eid}'
curl -s -X POST localhost:8000/api/stamp -H 'content-type: application/json' -d '{"eid":"c12"}'   # then re-run the agent: COUNTER WINS
```

Built for the WeMakeDevs **Graph Hacks: Context for AI Agents** hackathon (FalkorDB). Solo project.

![flip](docs/flip.png)

## Design

The balance is the hero: two huge rolling-odometer scores either side of a brushed-aluminium scale with glass bowls of iridescent liquid. The winning side gets a chromatic-aberration edge glow, and the whole page hue follows the balance (aqua when the claim stands, magenta when the counter wins). Accepting a counter flips the verdict as a physical event: inversion bloom, hue spin, ripples, a thump, and the digits roll. Weights are edited with machined knobs and a 10-notch meter. Everything is vanilla HTML/CSS/SVG/JS, no build step, and `prefers-reduced-motion` turns the motion off.

## Graph model

44 nodes, 66 edges (every edge carries a one-sentence `source` citation).

```
(:Person {key, name, blurb})        34 people   e.g. Locke, Hume, Kant, Marx, Hayek, Friedman, Chomsky, Skinner
(:Idea   {key, name, blurb})        10 ideas    e.g. Empiricism, Marxism, Keynesian Economics, Behaviorism

(a)-[:INFLUENCED  {eid, weight 1-10, base, source, stamp?}]->(b)    49 edges, directed
(a)-[:COUNTERED   {eid, weight 1-10, base, source, stamp?}]->(b)    15 edges, directed
(a)-[:COLLABORATED{eid, weight, base, source}]->(b)                  2 edges (kept for context, not scored)
(i)-[:CLASH {id, title}]->(j)                                         4 preset idea clashes
(:Meta {id:'rev', rev})   (:Event {ts, kind, text})                   revision counter + edit log
```

`base` is the curated weight; `weight` is the live, editable one; `stamp = true` marks an accepted counter.
Weights are an editorial judgement of how strong a link is. The facts behind each edge are real and cited
(for example Marx's 1873 afterword to *Capital* on Hegel, Hayek's tribute to Mises's *Socialism*, Keynes's 1933 essay on Malthus).

Presets: Keynesian Economics vs Monetarism · Empiricism vs Rationalism · Marxism vs Austrian School · Behaviorism vs Cognitive Psychology.
You can also type any Person or Idea (try `Hume`).

## The queries that matter

Effective weight of an edge is its `weight`, or **10 if stamped**. A path scores `10 × Π(effective_weight / 10)` over its edges, so every extra hop discounts it.

**Supporting paths** (best path per origin, top 3, total = their sum). `backend/queries.py`:

```cypher
MATCH p = (s)-[:INFLUENCED*1..3]->(a {key: $key})
WITH s, p, reduce(sc = 10.0, r IN relationships(p) |
     sc * (CASE WHEN r.stamp = true THEN 10 ELSE r.weight END) / 10.0) AS score
ORDER BY score DESC
WITH s, collect({p: p, score: score})[0] AS best     // one path per origin
...                                                  // ORDER BY score, take 3, sum
```

**Counter-paths.** A `COUNTERED` edge that lands on the subject, or on a node that feeds the subject within two `INFLUENCED` hops, so the counter travels down the influence chain and is discounted by it (Leibniz counters Locke, who feeds Empiricism):

```cypher
MATCH p = (m)-[:COUNTERED]->(x)-[:INFLUENCED*0..2]->(a {key: $key})
WITH m, p, reduce(...same score...) AS score
ORDER BY score DESC
WITH m, collect({p: p, score: score})[0] AS best
...                                                  // top 3, sum
```

**Live re-ranking** is just running those two queries again after an edit. The edits are Cypher too:

```cypher
MATCH (u)-[r]->(v) WHERE r.eid = $eid AND type(r) IN ['INFLUENCED','COUNTERED']
SET r.weight = clamp($w, 1, 10)                       // weight edit, bumps (:Meta {id:'rev'}).rev, logs an :Event
MATCH (u)-[r:COUNTERED]->(v) WHERE r.eid = $eid SET r.stamp = true      // Accept counter
MATCH ()-[r:COUNTERED]->() WHERE r.stamp = true SET r.stamp = null      // Clear stamps
```

The scale compares the two totals. Larger counter total: **COUNTER WINS**, otherwise **CLAIM STANDS**. The frontend polls the revision counter, so a second tab or a refresh shows the same state.

## Live demo

**https://pathflip-srini5.vercel.app** (Vercel front/API, graph and every edit live in a hosted **FalkorDB Cloud** instance).
Try the *Keynes vs Friedman* preset, then accept the counter `c11`: the scale flips from 22.0 vs 20.4 (claim stands) to 22.0 vs 23.4 (counter wins).
Note: the instance is shared, so anyone's stamps are visible to everyone; use "Reset" in the UI (or `POST /api/reset`) to go back to the curated weights.

### Hosted FalkorDB setup (what the live site uses)

1. Create a free instance at https://app.falkordb.cloud and note host, port, username and password.
2. Set these env vars on the host (Vercel: Project Settings > Environment Variables):
   `FALKORDB_HOST`, `FALKORDB_PORT`, `FALKORDB_USERNAME`, `FALKORDB_PASSWORD`, and `FALKORDB_SSL=1` if the instance requires TLS.
   Optional: `PATHFLIP_GRAPH` (graph name, default `pathflip`).
3. Deploy. `index.py` is the Vercel entrypoint (`vercel.json` bundles `frontend/`). On cold start it seeds the graph **only if it is empty**
   (a `Meta` node marks a complete seed; a short lock graph stops concurrent cold starts from double-seeding). Seeding is a handful of batched `UNWIND` queries.
4. Without env vars the app talks to `localhost:6379` as before (`scripts/run_local.sh`, `docker compose up --build`).
   `Dockerfile.space` is a single container (official FalkorDB image + app) for hosts that run Docker.

Serverless caveat: embedded FalkorDB (`falkordblite`) can't run on Vercel (its binary needs glibc 2.35+), so a hosted FalkorDB is required there.

## Run it (under 5 minutes)

**With Docker**

```bash
docker pull falkordb/falkordb:latest
docker compose up --build        # FalkorDB + seeded app
# open http://localhost:8000
```

**Without Docker** (uses the same FalkorDB engine from the [`falkordblite`](https://pypi.org/project/falkordblite/) wheel, run as a real server on :6379):

```bash
./scripts/run_local.sh           # venv, FalkorDB, seed, app on http://localhost:8000
```

Or by hand against any FalkorDB on `localhost:6379` (`FALKORDB_HOST`, `FALKORDB_PORT`, `FALKORDB_PASSWORD` are honoured):

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python backend/seed.py
.venv/bin/uvicorn app:app --app-dir backend --port 8000
```

Tests (start their own throwaway FalkorDB, or set `PATHFLIP_TEST_FALKORDB=host:port`):

```bash
.venv/bin/pip install falkordblite && .venv/bin/pytest -q
```

Agent tools: see *Track 1* above (`POST /mcp`, `GET /api/agent`, `GET /api/tools`).

## 60-second demo script

1. **0-8s** Click the preset **Keynesian Economics vs Monetarism**. The scale leans toward support (22.0 vs 20.4) and the banner says CLAIM STANDS.
2. **8-18s** Point at the two lists: teal supporting paths, red counter-paths. The strongest path of the winning side is marked WINNING PATH and drawn thick and animated in the graph.
3. **18-30s** Click counter-path #3 (Hayek countered Keynes). It expands to show each edge's weight and its source sentence. Press **+** on the Hayek edge: the counter total rises to 21.3 and the gap nearly closes.
4. **30-48s** Press **ACCEPT COUNTER**. The path jumps to #1, the scale swings, **FLIP!** flashes, and the banner turns to COUNTER WINS (24.0 vs 22.0).
5. **48-60s** Refresh, or open a second tab: the stamp is still there because it lives in FalkorDB. Press **Clear stamps** and it flips back. The edit log shows every change.

`docs/pathflip-demo.mp4` is a recorded 88-second version with voiceover and captions (recorded from the running app by `scripts/record_demo.py`).

**No server? Static replay.** `docs/replay.html` is the same UI running on recorded responses from the live API (stamps work, one at a time; weight edits and free-text names need the live app). Open it from any static host, for example `cd docs && python3 -m http.server`. Rebuild it with `python scripts/make_replay.py` against a running app.

## Layout

```
backend/   app.py (FastAPI), queries.py (all Cypher), seed.py, data.py (curated graph + sources)
frontend/  index.html (single page, SVG scale + path map, no build step)
backend/agent.py  tool registry + rule-based agent loop + memo template
tests/     pytest suite against real FalkorDB (test_agent.py covers the tools, trace, memo, MCP and the stamp flip)
docs/      screenshots, demo video, static replay page
```

## Honest gaps

- The agent is rule-based, not an LLM: tool choice is a fixed policy, so it demonstrates tool use and explainability, not open-ended planning.
- PageRank runs over the `INFLUENCED` graph and ignores weights and stamps (it measures structural influence); the support/counter scores use the weights. It is context in the memo, it does not decide the verdict.
- The what-if recommendation considers the unstamped `COUNTERED` edges on the current top-3 counter paths only.
- Each agent run makes about 10 round trips to the hosted FalkorDB (~2 s on the live site).

- 44 nodes is deliberately small. Path scores multiply normalised weights, which is a simple model of influence, not a theory of it.
- Weights are my judgement. The facts and sources are checked, the numbers 1-10 are opinion. You can edit them in the UI.
- "Accept counter" sets that counter's edges to full strength (10). It does not change any supporting edge.
- Each side's score is the sum of its top 3 paths, one per origin. A clash with fewer than 3 counters scores lower on that side by design.
- A challenger idea in a preset is shown as context. The ranking is run for the claim under test.
- No auth, no multi-user conflict handling: last write wins.
- It was built and tested on a box with no Docker, so it ran on FalkorDB 4.18.3 from the `falkordblite` wheel (a real FalkorDB server process, same Cypher and client). `docker-compose.yml` follows the official image but I did not run it there.
- No hosted live demo: a persistent FalkorDB server needs a host with an account, which I did not set up. The video and the static replay stand in for it.
