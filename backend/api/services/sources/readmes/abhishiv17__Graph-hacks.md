# KindRed

A coordination and decision-support platform for living-donor exchanges across transplant programs: **kidney paired donation** and **living donor liver paired donation**, on one FalkorDB graph. Built for Graph Hacks 2026 (Tracks 1 and 2).

**Synthetic demo data only. No real patients. A software prototype, not a clinical tool.**

The graph finds the swap loops inside each program, a CP-SAT optimiser ranks them, agents send offers and each program's test (a lab crossmatch for kidney, a donor work-up for liver), and when a test fails the graph repairs the loop locally (2 hops around the released families). A person approves every repair. The LLM never allocates anything and never creates a fact.

### One platform, two programs

| | Shared core | Kidney program | Liver program |
|---|---|---|---|
| Code | `swapnet/agents`, `optimiser`, `programs.py`, `access.py` | `swapnet/organs/kidney.py` | `swapnet/organs/liver.py`, `gen/liver.py` |
| Matching rule | loop search, optimiser, repair (Q04, Q05, Q11) | ABO + virtual crossmatch (Q02) | ABO + graft size + evaluation statuses (Q21) |
| Test before surgery | offers, tasks, failure memory | lab crossmatch | donor work-up (CT volumetry) |
| Program config | committee, timeline, scenario framework | `data/params/india_kidney.yaml` `program:` | `data/params/india_liver.yaml` `program:` |

### What the graph does that a table can't

- **Loop finding is graph traversal.** 2-way and 3-way swaps are cycles over `CAN_GIVE_TO` edges (Q04, Q05). `algo.WCC` splits the pool into independent parts before matching (Q07), and `algo.betweenness` finds bridge families whose withdrawal would break the most loops (Q19).
- **Repair is a local, multi-hop search.** When a test fails, Q11 searches only 2 hops around the released families. Every other loop stays untouched, and the screen says how many.
- **Memory lives in the graph.** A failed test becomes a `FAILED` edge that is never proposed again, plus a `Failure` node. Every agent step and human approval is a `Decision` with `BASED_ON` edges to the facts it used. Agents hand off through `Offer`, `Crossmatch` and `Task` nodes, so a restart loses nothing. Every agent step also stores what it read from memory first and which agent wrote it ("Read before acting" on each patient's page): the coordinator agent reads the health watch's beliefs and findings and the crossmatch coordinator's failed links; the matching agent reads the failure memory before every search (Q54) and skips those links; the scheduler, clerk and liaison pick up the health watch's tasks.
- **Demo patients the agents follow over months.** Open **Demo patients** (`/patients`), no sign-up: Sunita (kidney, eGFR falling) and Rajesh (liver, MELD rising) each have six months of synthetic history. Press **Next week** and a new lab result arrives. The **health watch** compares the trend with sourced thresholds and with the stage it *remembers*. Only a more urgent stage triggers its playbook, which it reads from the graph. It then hands one `Task` per step to the scheduler (appointments), the committee clerk and the patient liaison. The case itself is run by a **coordinator agent**: each week a language model (Groq `openai/gpt-oss-120b`) reads the patient's state and memory from the graph and picks the next step from six vetted tools (search 2-way then 3-way, form the swap, run the tests, ask for papers, book surgery, or wait). It never writes Cypher, every tool checks the graph before it acts, every id in its reason is checked against the result, and the rules take over if it fails. No approve button. "Why this swap" shows each donation's stored reasons, the shallow vs deep search shows what a 2-way search missed, and each patient has a chat whose history lives in their memory graph. **See the swap on the live map** jumps to the map with it in focus. Readings stay in the hospital's private graph; each patient's memory (sessions, findings, beliefs that supersede older ones, playbooks) lives in a graph of its own (`mem_sunita`, `mem_rajesh`). See docs/personas.md.
- **A reasoning layer you can listen to.** Every family graph and swap has **Explain this graph, step by step**: a walkthrough built from graph data (why the family's own donor can't give, who the graph tried and why each failed, the 2-way and 3-way swaps found), highlighting each part as it goes, read aloud by Sarvam in English or 10 Indian languages. Hover over any circle or line for the same plain explanation; pinch or scroll to zoom. See docs/how-it-works.md.
- **A private copy per visitor, and the coordinator over real MCP.** "Make my own copy" in the top bar gives a visitor the whole demo in their own FalkorDB graphs, so two judges never move the same patient; on the shared demo a journey can't be advanced twice at once. The coordinator agent lists and calls its tools over MCP on KindRed's own MCP server. See docs/how-it-works.md.
- **One graph per tenant.** Each hospital has its own private graph (`hosp_hyd`, …) holding names, full HLA typing and documents. The shared `exchange` graph holds only what matching needs.
- **An agent that reasons over the graph, and never writes Cypher.** In **Ask KindRed** (`/ask`), a language model answers coordinators' questions ("What breaks if Bengaluru's P-0211 withdraws?", "Find a new loop for Kolkata: 2-way first, then 3-way") by choosing from 15 read-only graph tools. It runs on **Groq** (hosted `openai/gpt-oss-120b`, fast; set `GROQ_API_KEY`), **Claude** (`ANTHROPIC_API_KEY`), or **Llama 3.1 8B locally through Ollama** (free, no key, no data leaves the machine). Each tool is a named, parameterised query in `backend/queries/`, run through `GRAPH.RO_QUERY` so FalkorDB itself refuses a write. Every id is resolved against the graph before any traversal, so an unknown family gets "not in the graph" instead of a guess. Every answer shows the tool trace (tool, arguments, queries, latency, rows) and the graph paths it rests on, and a validator replaces any draft that names an id no query returned. Verified answers are remembered as `Question` nodes and recalled in later sessions, scoped to the viewer's hospitals and program. The same tools, plus the matching and workflow tools, are served to any MCP client: 37 in all, including the coordinator agent's case tools.

Programs never mix: each edge query matches only its own organ, every loop query requires one organ per loop, and an organ's rule refuses another organ's pair (`OrganMismatch`). Thresholds the project has a published source for (GRWR ≥ 0.8%, donor keeps ≥ 30%, MFI 2000) are program configuration; checks without an authoritative number are statuses (ELIGIBLE, REVIEW_REQUIRED, UNKNOWN, INELIGIBLE).

## Tracks entered: 1 and 2

| Track | Where to look |
|---|---|
| **1 · Agents that act on connected data** | The coordinator agent (`swapnet/agents/coordinator.py`) lists and calls its tools over MCP (`swapnet/mcp/server.py`) to search, form swaps, run tests, ask for papers and book surgery, while graph-side checks constrain each action. Graph work: 2- and 3-way loop traversal (Q04, Q05), 2-hop local repair (Q11), `algo.WCC` (Q07), `algo.betweenness` (Q19), `algo.pageRank` (Q59), `shortestPath` (Q34). Ask KindRed picks from 15 read-only tools and says "not in the graph" for unknown ids. |
| **2 · Agent memory and coordination** | Per-patient memory graphs (`mem_sunita`, `mem_rajesh`) hold findings, beliefs that `SUPERSEDES` older ones, playbooks and sessions (`swapnet/agents/recall.py`). Failures are `FAILED` edges, answers are `Question` nodes, and agents hand work over through `Task` nodes with "read before acting" provenance. Optimistic locking with measured concurrency and load tests (`tests/test_concurrency.py`, `loadtest/`, docs/how-it-works.md). A private graph per hospital and per visitor copy. |

## Run it on your laptop

Everything runs locally. There are no accounts to create and no API keys to set, and all data is generated.

### What you need

| | Version | Notes |
|---|---|---|
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | any recent | On Windows it needs WSL 2 (the installer offers it). Give Docker at least 4 GB of RAM. |
| Git | any | Or download the repo as a ZIP. |
| Free ports | 3000, 3001, 6379, 8000 | FalkorDB browser, web app, FalkorDB, API |

You only need Python and Node if you want to change the code (option B below).

### Option A: everything in Docker (recommended)

```bash
git clone <this repo> kindred
cd kindred
docker compose up --build -d
```

The first build takes about 3–5 minutes (it downloads FalkorDB, Python and Node images). After that:

1. Open **http://localhost:3001**. That's the homepage.
2. Click **Meet a demo patient** (or go to **http://localhost:3001/patients**). If it says the patients aren't loaded, press **Load the demo**.
3. For the exchange story, open the workspace (**http://localhost:3001/pool**) and press **Restart demo**. It generates 154 kidney and 44 liver synthetic pairs across 11 hospitals (including the two demo patients) and runs the first match. Then follow the demo story below.

Useful extras:

- **http://localhost:3000**: the FalkorDB browser. Pick the `exchange` graph to see the shared pool, or `hosp_hyd`, `hosp_blr`, … for a hospital's private graph.
- **http://localhost:8000/docs**: the API, if you want to call it directly.
- Reset the demo at any time with **Restart demo**, or run `curl -X POST http://localhost:8000/api/demo/reset`.
- See logs with `docker compose logs -f backend`, and stop everything with `docker compose down`.

If the API isn't reachable, the web app falls back to a recorded synthetic snapshot and shows an **Offline** badge in the top bar. It switches back to live data on its own once the API answers. If the badge stays, check `docker compose ps`.

### Option B: develop locally (hot reload)

You need **Python 3.11+** and **Node 22+**. FalkorDB always runs in Docker.

```bash
docker compose up -d falkordb
```

Backend, macOS / Linux:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn swapnet.api.main:app --reload --port 8000
```

Backend, Windows PowerShell:

```powershell
cd backend
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
uvicorn swapnet.api.main:app --reload --port 8000
```

Web, in a second terminal:

```bash
cd web
npm install
npm run dev          # http://localhost:3001
```

On Windows, `.\scripts\dev.ps1` starts all three in separate windows.

> **Windows "An Application Control policy has blocked this file"**: Smart App Control can block the pandas DLL that OR-Tools pulls in. Run the backend in Docker and only the web app locally: `docker compose up -d falkordb backend`, then `cd web && npm run dev`.

### Optional settings

**Ask KindRed needs a model.** Three options; every other screen works without any of them.

- **Groq (fast, hosted):** get a free key at console.groq.com, then in `.env` set `GROQ_API_KEY` and `KINDRED_ASK_PROVIDER=groq` (model `openai/gpt-oss-120b`, override with `KINDRED_GROQ_MODEL`).

- **Free, local (default):** install [Ollama](https://ollama.com), then run `ollama pull llama3.1:8b`. Leave Ollama running; the backend in Docker reaches it at `host.docker.internal:11434`. On a laptop CPU an answer takes about a minute (two model turns over a ~3,000-token prompt). Set `KINDRED_OLLAMA_MODEL` to try another model with tool support.
- **Claude:** copy `.env.example` to `.env`, set `ANTHROPIC_API_KEY` and `KINDRED_ASK_PROVIDER=anthropic` (model `claude-opus-5-5`, override with `KINDRED_ASK_MODEL`). Answers take seconds.

`/api/ask/status` says which model is active and whether it's reachable. The key, if set, is also used to translate family messages into languages other than English and Hindi. After editing `.env`, run `docker compose up -d backend`. If the API runs somewhere other than `localhost:8000`, set `NEXT_PUBLIC_API_URL` before building the web app.

### Tests, simulation and MCP

| What | Docker | Local (venv active, in `backend/`) |
|---|---|---|
| Tests (needs FalkorDB; resets the demo graph) | `docker compose exec backend sh -c "pip install -q pytest && pytest -q"` | `pytest -q` |
| Simulation lab, 20 runs, about 4–5 min | `docker compose run --rm backend python -m swapnet.sim.lab --runs 20` | `python -m swapnet.sim.lab --runs 20` |
| MCP server (37 tools, stdio) | `docker compose exec backend python -m swapnet.mcp.server` | `python -m swapnet.mcp.server` |
| Concurrency test, about 4 min (scratch graph, never the demo) | `docker compose exec backend python -m swapnet.sim.concurrency` | `python -m swapnet.sim.concurrency` |
| Load test through the API with Artillery, about 2.5 min (in a private copy, never the shared demo) | `cd loadtest && npm install && npm test` (against the running stack) | the same; `node run.mjs --target <url>` for a deployed API |

The simulation writes `data/generated/sim_results.json`, the concurrency test `data/generated/concurrency.json` and the load test `data/generated/loadtest.json`. The Simulation and How it works screens read them from the API, so refresh the page after a run.

### Check it works

With the stack up, these walk the kidney story through the API (on Windows PowerShell, type `curl.exe` instead of `curl`):

```bash
curl http://localhost:8000/api/health                       # {"ok":true}
curl -X POST http://localhost:8000/api/demo/reset           # 198 pairs, plan #42
curl -X POST http://localhost:8000/api/demo/add-chennai     # the Chennai family joins
curl -X POST http://localhost:8000/api/loops/S-0076/lab     # Bengaluru -> Kolkata is positive (DQ7)
curl http://localhost:8000/api/loops/S-0076                 # proposal.task_id and the recommended repair
curl -X POST http://localhost:8000/api/tasks/<task_id>/approve -H "Content-Type: application/json" -d '{"choice":"recommended"}'
curl -X POST http://localhost:8000/api/loops/L-0034/lab     # liver: GRWR 0.74% fails, repair proposed
curl -X POST http://localhost:8000/api/personas/sunita/advance   # demo patient: eGFR 19, stage Prepare, 6 hand-offs
curl http://localhost:8000/api/personas/sunita                   # readings, memory, hand-offs, appointments
```

Replace `<task_id>` with the id from the previous response (PowerShell rejects the `<` `>` characters). The guards answer plainly:

| Request | Answer |
|---|---|
| `POST /api/loops/S-0076/lab` again, after it broke | 409: a broken loop gets no more tests |
| `GET /api/hospital/XYZ`, `GET /api/family/P-9999`, `POST /api/tasks/T-nope/approve` | 404: not in the graph |
| Approving a task twice | 409: already done |
| `-H "X-KindRed-User: observer"` on a lab run | 403: read-only role |
| `POST /api/personas/sunita/advance` after week 6 | 409: the scripted readings ran out; `POST /api/personas/sunita/reset` replays |

To look at the graph directly, open http://localhost:3000, pick `exchange` and run `MATCH (a:Pair)-[f:FAILED]->(b:Pair) RETURN a, f, b`.

### Deploy it (FalkorDB Cloud, Render, Vercel)

1. **FalkorDB:** create an instance on [FalkorDB Cloud](https://app.falkordb.cloud) and note its host, port, user and password.
2. **API on Render:** New → Blueprint, pick this repo. `render.yaml` builds `backend/Dockerfile` from the repo root and asks for `FALKORDB_HOST`, `FALKORDB_PORT`, `FALKORDB_USERNAME`, `FALKORDB_PASSWORD`, `GROQ_API_KEY` and (optional) `SARVAM_API_KEY`. Set `FALKORDB_TLS=1` if the instance uses TLS. The free plan sleeps after 15 idle minutes, which also stops the agents' background watch; the blueprint uses Starter.
3. **Load the demo once:** `curl -X POST https://<your-api>.onrender.com/api/demo/reset` (or press **Restart demo** on `/pool`).
4. **Web on Vercel:** import the repo, set **Root Directory** to `web`, and add `NEXT_PUBLIC_API_URL=https://<your-api>.onrender.com`. It is read at build time, so redeploy after changing it.

### Troubleshooting

- **Port already in use**: something else is on 3000, 3001, 6379 or 8000. Stop it, or change the left-hand port in `docker-compose.yml`.
- **The workspace shows "offline snapshot"**: the API isn't up yet. Wait 10 seconds after `docker compose up`, then check `docker compose logs backend`.
- **The demo state looks odd after testing**: press **Restart demo** (or run `scripts/reset-demo`). Running the tests also resets the graph.
- **Code changes don't show up in Docker**: rebuild with `docker compose up --build -d`.

## Simulation results (synthetic, measured by us)

We simulate one year of a national pool, day by day: about 540 families arrive, lab results take 9 days (offer plus crossmatch, as in multi-centre programmes, Ashlagi 2018), and match runs are weekly. Each policy ran 20 times. Ranges are 95% intervals.

| Policy | Transplants / year | Lab tests wasted on loops that broke | Median wait to a match that held |
|---|---|---|---|
| Each hospital alone, 2-way only (today) | 142 (135–148) | 43 | 3.1 weeks |
| Shared pool, 2-way only | 223 (216–230) | 76 | 3.5 weeks |
| Shared, 3-way, ignores failures | 249 (241–257) | 152 | 3.8 weeks |
| **KindRed**: shared, 3-way, plans for failure, repairs live | **250 (242–258)** | **130** | **3.1 weeks** |

What this does and doesn't show:

- A shared pool is the big win: **76% more transplants** than each hospital working alone.
- Compared with a 3-way matcher that ignores failures, KindRed gets the same number of transplants (the intervals overlap), with **14% fewer wasted lab tests**, matches that hold **about 0.7 weeks sooner**, and about 25 broken loops repaired a year.
- KindRed matches fewer highly sensitised patients than the failure-blind matcher (39% vs 43%), because their links fail more often. It's a known trade-off of failure-aware matching, and we haven't solved it yet.
- The generator reproduces Saidman et al. 2006: 46.6% matched with 2-way loops (published 49.8%) and 57.7% with 2+3-way (published 59.8%), at n = 100.

## Concurrency test (measured by us)

Every hospital's intake agent writes to the shared exchange graph while the matching agent searches it. `python -m swapnet.sim.concurrency` does this on purpose with the real named queries, in a scratch graph of 150 synthetic kidney families: FalkorDB 6.0.1 in Docker with default settings, on one laptop (22 CPUs), agents as threads with their own connections. The numbers below are from `data/generated/concurrency.json`.

**1. Agents publishing 96 new families at once** (publish with the version check, then build the family's links), while two matchers search every 2- and 3-way loop:

| Agents writing | Families / s | Each family, p50 / p95 | Lost |
|---|---|---|---|
| 1 | 7.5 | 106 / 308 ms | 0 |
| 4 | 18.8 | 168 / 435 ms | 0 |
| 8 | 20.3 | 275 / 673 ms | 0 |
| 16 | 20.5 | 611 / 1,287 ms | 0 |

**2. Agents updating the same family at the same moment**, 10 updates each:

| Agents | Updates | Stale writes refused (then retried) | Lost with the version check | Lost without it |
|---|---|---|---|---|
| 2 | 20 | 11 | 0 | 10 |
| 8 | 80 | 330 | 0 | 65 |
| 16 | 160 | 1,498 | 0 | 138 |

What this shows and doesn't:

- **No write was lost** in any run, and no query timed out or was refused. Afterwards every published family is in the graph once, at version 1.
- **The version check is what makes concurrent agents safe.** Without it, the same read-then-write work by 16 agents keeps 22 of 160 updates; with it, all 160.
- **Throughput levels off at about 20 families a second from 8 agents.** FalkorDB runs one write query at a time per graph (reads run in parallel), so more agents queue rather than write faster, and each family's wait grows.
- **Writes don't measurably slow the matcher.** On a pool of fixed size, two matchers searching every loop take about 0.4–0.9 s with or without 1–16 agents updating families; the difference is within run-to-run noise. What slows the search is the pool's size: a bigger pool has many more 3-way loops, so the search grows steeply with it.
- One laptop, synthetic data, a few seconds per run. It is a measurement of this prototype, not a capacity claim for a national system.

## Load test through the API (measured by us)

The concurrency test above measures the graph. `loadtest/` (Artillery 2.0.34) measures the whole app the way visitors use it: HTTP, FastAPI, the agents' code and FalkorDB, in a private copy of the demo. Visitors arrive at 2 a second, ramp to 20 a second and stay there for a minute; each browses (the pool, the swaps, a family's graph two hops out, a patient's journey, the agents' shared state), chats about a family, or opens a patient's page. Then the runner counts every chat message and page visit in the copy's graphs and compares it with what was written. Finally 20 people press Next week on the same patient in the same second. One laptop (12 CPUs), the whole stack in Docker Compose. Numbers from `data/generated/loadtest.json`:

| | Result |
|---|---|
| Visitors / requests | 1,590 visitors, 5,881 requests in 114 s (51.6 a second at the peak rate), no errors, no timeouts |
| Latency, all requests | p50 1.1 s, p95 3.7 s, p99 5.0 s (at 20 new visitors a second; the backend is one Python process, so this is near its limit) |
| Writes | 499 chat turns and 143 page visits; all 1,046 chat messages in the graph exactly once (none lost, none doubled) |
| 20 × Next week at once | 1 moved the journey (the coordinator agent's week ran), 19 refused in 8 ms (p50), the patient moved exactly one week |

The first run found the limit: the API managed 28 requests a second, p95 was 25.6 s and 575 of 1,590 visitors timed out. Profiling showed most of the time going to parsing FalkorDB's replies in pure Python, and to every visitor re-running the same whole-pool traversals. Two changes fixed it: `hiredis` (the C parser for the Redis protocol), and a cache for the pool, swaps and family-graph reads that any write to the exchange graph clears (and that expires after 2 s, for writes from the MCP server's process). Even then, no write was lost: 135 chat turns whose client had given up were still written exactly once.

What it doesn't show: one machine, one backend process, chat questions answered by the guard rather than a language model (so it measures the graph, not a model's rate limit). It is a measurement of this prototype, not a capacity claim.

## Ask KindRed

| Ask | What the agent does in the graph |
|---|---|
| "Why was S-0076 put together?" | `explain_loop`: each link's success estimate and the reasons stored on the edge (Q13) |
| "What breaks if Bengaluru's P-0211 withdraws?" | `withdrawal_impact`: the live loops it's in, who else is affected, whether the stored fallback survives (Q32) |
| "Find a new loop for Kolkata's P-0388: 2-way first, then 3-way." | `find_loops_for` at depth 2, then 3: the same question at two depths (Q04, Q05) |
| "How many families can P-0154's donor reach within 1 hop, and within 3?" | `reachable_within`: variable-length paths over live links (Q33) |
| "How is P-0154 connected to P-1088?" | `connection_path`: `shortestPath` (Q34) |
| "Which families hold the most loops together?" | `bridge_families`: `algo.betweenness` (Q19) |
| "Which waiting families are hardest to match?" | `match_ease`: `algo.pageRank` over the compatibility links (Q59); a low score means few donors can reach that patient |
| "What has the graph learned from failed tests around P-0211?" | `failure_memory`: FAILED edges and their tests (Q35) |
| "What happens if P-9999 withdraws?" | The id resolver (Q36) answers "not in the graph"; nothing else runs |
| "What do the agents remember about Sunita, P-0901?" | `patient_memory`: her current beliefs with what each replaced, dated findings, open hand-offs (Q42, Q43, Q48) |

Earlier verified answers are stored in the graph (Q37) and recalled with their dates (Q38, Q39).

The Ask page opens with five **example conversations**, answered the moment it loads (`swapnet/agents/examples.py`): the same tools a model picks, run live on the graph, with full tool traces and graph paths. Only the sentence is written by code instead of a model, and each answer says so. They show the depth contrast (reach within 1 donation, then 3; or 2-way then 3-way swaps when the pool has them), PageRank as a tool, what breaks if a family withdraws, an answer from memory with the date each belief was learned, and an id that isn't in the graph.

## The screens

| Screen | What it's for |
|---|---|
| **Demo patients** (`/patients`, `/patients/sunita`, `/patients/rajesh`) | Start here. Where the case stands in five steps, **Next week**, **See the swap on the live map**, the trend with sourced thresholds, what the agents did week by week, and "Under the hood" (memory, playbook, appointments, queries) |
| **Program switcher** (sidebar) | Kidney, Liver, or All programs (an operational overview that lists both side by side, never one mixed graph). Every screen follows it; `?program=liver` links work too. |
| **Live pool** (`/pool`) | A zoomable map of India with every planned donation as a line, coloured by program. Each program has its own family columns (kidney: cPRA, HLA typing, crossmatch; liver: MELD and weight, graft suitability, anatomical, donor and recipient evaluation). Family details mark shared exchange data versus what stays private to the hospital. |
| **Swaps** (`/swaps`, `/swaps/S-0076`, `/swaps/L-0034`) | Each swap's graph, evidence per recommendation (facts, constraints satisfied, flags, test, human-approval status), the program's committee checklist, a proposed (synthetic) timeline, offers, tests, failure and repair proposal. |
| **Committee review** (`/committee`) | Each swap's readiness against its own program checklist, and which family's paperwork is holding it up, against the 42-day court target. |
| **Integrity** (`/integrity`) | Shared checks (references, broken links, cross-program links, missing evidence or approvals) and program checks (kidney crossmatches; liver graft-size confirmation and open reviews). Workflow checks, never diagnoses. |
| **Family view** (`/case/P-0154`, `/case/P-0451`) | What one family sees on their phone, in English or Hindi, in their program's terms. Only their own case. |
| **Simulation lab** (`/lab`) | Each program's scenario (initial state, failure event, repair strategy, review step), replayed from recorded backend output. Changes nothing. |
| **Impact** (`/impact`) | The yearly simulation (kidney program only): four policies, 20 runs, with the validation against Saidman 2006. |
| **How it works** (`/graph`) | What's in FalkorDB right now, every named query with live timings, the MCP tools, and the measured concurrency and load tests. |
| **Agents** (`/agents`) | The agents working in the background, drawn live from FalkorDB: each agent (language model, rules or person), the graphs it reads and writes, the open hand-off tasks between agents, and what each just did. Agents never call each other, so every line goes through a graph. Each action plays on the graph as the background watch writes it (the agent lights up, a caption says what it did); click any agent for what it read first and who wrote it. |
| **Audit trail** (`/audit`) | Every agent action and human decision, in order. |

A **demo guide** at the top of every screen shows the five story steps and offers the next one as a button, and every screen opens with a short "what is this" note. Dotted words have a plain-language definition on hover.

## Demo story (about 3 minutes)

0. **Demo patients** → Sunita. Press **Next week**: eGFR 19 crosses the pre-emptive window, the health watch hands out its *Prepare* playbook, and the coordinator agent searches 2-way swaps and forms one (open "How it decided" for its tool calls). Press **See Sunita's swap on the live map**. Keep pressing **Next week**: the lab tests pass, the clerk collects the papers, the surgery is booked, and in week 5 the transplant is done; no button approved anything. Rajesh (liver): nobody fits him at first; in week 2 a new family joins in Mumbai, the 2-way search still finds nothing, and the 3-way search finds Kochi → Bengaluru → Mumbai (press **Replay the search on the map**). Ask "Why was this swap chosen?" in his chat, then open the page in another browser: the conversation is still there. Reload a journey and the greeting says what changed since your last look.
1. **Live pool**: 153 synthetic pairs across 11 hospitals; this week's plan includes swap S-0076, Hyderabad → Bengaluru → Kolkata (46% chance every link holds, 2.0 of 3 expected thanks to its 2-way fallback). Zoom in and click its lines.
2. **Add a new family (Chennai)**: the intake agent checks the rules and adds the family's links to the graph.
3. Open S-0076 and press **Run lab tests**. Hyderabad → Bengaluru is negative; Bengaluru → Kolkata is positive (DQ7, never typed). The link is stored as a FAILED edge and never proposed again.
4. The repair panel shows Hyderabad → Bengaluru → Chennai, found in milliseconds without touching any other loop, with the 2-way fallback and alternatives. Kolkata → Hyderabad's test is marked *Not needed*: the loop broke first, so it was never sent. **Approve recommended repair**; the negative test carries over.
5. **Family view** (P-0154, English or Hindi), **Committee review** (the repaired swap waits on Bengaluru's relationship proof and Chennai's three missing papers), **Impact**, **How it works**.
6. Switch the sidebar to **Liver**. Open L-0034, Delhi → Chennai → Kochi, and press **Run donor work-ups**. Chennai's CT volumetry measures a 780 ml lobe (GRWR 0.74%, below the program's 0.8% rule), so that link fails; the repair proposes Delhi ⇄ Chennai. The liver committee checklist shows Chennai's surgical suitability review still open.

## Layout

- `backend/queries/` – every Cypher query, named Q00–Q59. Each screen shows which ones ran and how long they took.
- `backend/swapnet` is the Python package (the project's working name was SwapNet).
- `backend/swapnet/graph` – FalkorDB access, publishing from private hospital graphs to the shared exchange graph, and a log of every query for the How it works screen.
- `backend/swapnet/agents` – intake, crossmatch coordinator, matching, committee clerk, family messages, and (`health.py`) the health watch and scheduler for the demo patients; `swapnet/personas.py` seeds them and reads their journey; `data/params/personas.yaml` holds who they are, their readings, thresholds with sources, and playbooks.
- `backend/swapnet/organs` – the organ programs (kidney, liver) behind one interface; `swapnet/programs.py` – shared services (pair facts, evidence, checklists, timelines, integrity, scenarios); `swapnet/access.py` – program- and hospital-scoped access for demo identities (`data/policies/access.yaml`; there is no authentication).
- `backend/swapnet/optimiser` – CP-SAT on expected transplants (accounts for test failures and fallbacks).
- `backend/swapnet/sim` – day-by-day yearly simulation of 4 policies, validated against Saidman et al. 2006.
- `data/` – published parameters (ABO, cPRA bands, failure rates), hospitals, intake policies, the demo scenario. `data/geo/` – India map data (Natural Earth, India's point of view).
- `web/` – Next.js app. `docs/` – schema, queries, agents, build plan, demo script.
- `scripts/capture-snapshot.py` re-records the offline demo after API changes; `scripts/build-india-map.py` regenerates the map paths.

## Data model (short)

One private graph per hospital (`hosp_HYD`, …) holds names, full HLA typing, relationships and documents. The shared `exchange` graph holds only what matching needs: `Pair`, `Donor`, `Patient`, `HLAAntigen`, `Antibody`, `CAN_GIVE_TO {p_success, reasons}`, `Loop`, `IN_LOOP`, `FAILED`, `Failure`, `Decision`, `Task`, `Event`. Liver donors add a `LiverProfile` (volumes and evaluation statuses). Until a donor's CT volumetry is shared, the exchange sees a volume estimated from height and weight; the CT measurements and clinical notes stay in the hospital graph, and a failed work-up writes the measured volumes to the exchange so that donor is never matched on the estimate again. See docs/schema.md.

### Program APIs

`GET /api/programs`, `/api/programs/{organ}`, `/api/pairs?organ=`, `/api/exchanges?organ=`, `/api/exchanges/{id}/evidence`, `/api/matches?organ=&pair_id=`, `/api/simulations?organ=`, `/api/integrity?organ=`, `/api/audit?organ=`, `/api/me`. Callers may name a demo identity with the `X-KindRed-User` header (`meera`, `hyd_coord`, `che_liver`, `committee`, `observer`); scoped reads filter rows and out-of-scope actions return 403.

## Rules we follow

Indian law: swaps only between near-relative pairs, each needing Authorisation Committee approval, no altruistic chains. These are checked before a pair is published.

## AI assistance

We used an AI coding assistant, Claude Code (Anthropic), while building KindRed: for writing and refactoring code, tests and documentation, and for reviewing and manually testing the app. The product idea, the graph model, the matching and repair approach and the final decisions are the team's, and we can explain every part of the code. Ask KindRed itself calls a language model at runtime (a local Llama 3.1 8B through Ollama by default, or Claude), as described above.

<!-- TEAM: check this paragraph is accurate for how you worked before submitting. -->

## Credits

Built alongside, not instead of, KidneyGrid, the NOTTO portal, ASTRA, IKDRC and ISOT SWAP. KindRed is the coordination and failure-handling layer.
