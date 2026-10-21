# AIDTRACE: activating Claude reasoning

**Status: prepared and tested with mocks. Live Anthropic connectivity is not verified** until a key is set and the
opt-in smoke test in step 5 below passes. Until then every question is answered from the graph engines, as before.

## What is built

| Piece | File |
| --- | --- |
| Settings and defaults | `backend/api/config.py` (the `AIDTRACE agent` block) |
| Anthropic adapter, readiness, usage, error codes | `backend/api/services/aidtrace_agent/provider.py` |
| Read-only tool registry | `backend/api/services/aidtrace_agent/tools.py` |
| Bounded tool loop, citation check, failure handling | `backend/api/services/aidtrace_agent/orchestrator.py` |
| Endpoints `GET /aidtrace-agent/status`, `POST /aidtrace-agent/ask` | `backend/api/routers/aidtrace_agent.py` (mounted in `backend/api/main.py`) |
| Offline tests (no key, no network, no graph) | `backend/tests/test_aidtrace_agent.py` |
| Opt-in live smoke test (manual only) | `backend/scripts/aidtrace_agent_live_smoke.py` |

The model reaches the graph only through five read-only tools: `get_memory_snapshot`, `get_action_eligibility`,
`get_graph_impact`, `get_agent_handoffs` and `preview_supplier_what_if`. There is no tool that writes, approves, runs
Cypher or SQL, or calls out over HTTP. The tools wrap the site-scoped `AgentMemory` service, so a question can only see
the caller's own site.

## Configuration

Set these in the backend environment. `.env.example` lists them with the safe defaults.

| Variable | Default | Meaning |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | empty | The key. Never commit it, paste it into chat, or put it in a screenshot. |
| `ANTHROPIC_MODEL` | `claude-opus-5` | Active model ID in Anthropic's current API model list and present in the installed SDK (anthropic 1.14.0). |
| `AIDTRACE_LLM_ENABLED` | `false` | Master switch. While `false`, no Anthropic request is ever made. |
| `AIDTRACE_LLM_FALLBACK` | `graph-only` | The only supported fallback. A failure keeps the deterministic answers. |
| `AIDTRACE_LLM_MAX_OUTPUT_TOKENS` | `2048` | Output cap per model call. |
| `AIDTRACE_LLM_MAX_TOOL_STEPS` | `6` | Tool rounds per question. |
| `AIDTRACE_LLM_REQUEST_TIMEOUT_SECONDS` | `60` | Per model call. The whole question gets this times steps plus one. |
| `AIDTRACE_LLM_MAX_CONCURRENT_REQUESTS` | `2` | Questions in flight in this process. Extra requests get `busy`. |
| `AIDTRACE_LLM_MAX_REQUESTS_PER_USER_PER_HOUR` | `30` | Per signed-in staff user, counted in Redis. Demo accounts use the existing demo budget. |
| `AIDTRACE_LLM_PRICE_INPUT_PER_MTOK` | `0` | USD per million input tokens, from the current price sheet. At `0` no cost estimate is shown. |
| `AIDTRACE_LLM_PRICE_OUTPUT_PER_MTOK` | `0` | USD per million output tokens, from the current price sheet. |

Usage and cost estimates appear only in responses to `admin` users.

## Activation: Windows local development

The installed SDK's `Model` type also contains `claude-opus-5-5`, but Anthropic's current API model-status page lists `claude-opus-5` as active and does not list Opus 5.5. A key is present in this local environment, but no live request was made, so account-level model access has not been queried. Keep the supported Opus 5 default until an operator verifies any alternative with the opt-in smoke test. The key value is never printed or included in this report.

1. Create the key in the Anthropic console.
2. Put it in the backend environment file, which Git ignores. Copy `.env.example` to `kairos-main\.env` if you have not already,
   then set:
   ```dotenv
   ANTHROPIC_API_KEY=<your key>
   AIDTRACE_LLM_ENABLED=true
   ```
   For a single PowerShell session instead, use `$env:ANTHROPIC_API_KEY = "<your key>"` before starting the backend. That value
   lasts only for that session.
3. Restart the backend. Either the dev harness, `python scripts\dev_harness.py` (serves `127.0.0.1:8100`), or uvicorn from the
   `backend` folder: `..\.venv\Scripts\python.exe -m uvicorn api.main:app --port 8000`.
4. Sign in as a staff user and call `GET /aidtrace-agent/status`. It should report `"state": "ready"`. If not, its `reason`
   field says why. The key itself is never returned.
5. Run the opt-in connectivity check once. It makes one paid request:
   ```powershell
   cd backend
   $env:AIDTRACE_LIVE_SMOKE = "1"
   ..\.venv\Scripts\python.exe scripts\aidtrace_agent_live_smoke.py
   ```
   Success prints `Live connectivity verified`. Any failure prints a fixed code and message, never the provider's text.
6. Ask a question once the workspace is wired (see *Not done yet*).

## Activation: hosted

1. Store `ANTHROPIC_API_KEY` in the deployment secret manager. Do not place it in a repository file or a build argument.
2. Set `AIDTRACE_LLM_ENABLED=true` in the backend's environment and redeploy the backend. No frontend rebuild is needed.
3. Run the smoke test as a one-off job in that environment, with `AIDTRACE_LIVE_SMOKE=1` set for that job only.
4. Set a monthly spend limit in the Anthropic console. The local limits above are not a billing cap.

## Things to decide before enabling

- **The fraud investigator shares `ANTHROPIC_MODEL`.** `backend/domains/fraud/config.py` uses the same environment
  variable, defaulting to the currently active Sonnet 5 model when no shared value is set. An environment override for
  the AIDTRACE agent also changes the fraud planner. Give each adapter a separate variable before selecting different models.
- **Prices are not set.** Cost estimates stay hidden until `AIDTRACE_LLM_PRICE_*` are entered from the current price sheet.

## What the answers guarantee

- Deterministic graph routes are the first answer path, and nothing changes for them. The model is consulted only for a
  question no deterministic route answers.
- A question makes at most `AIDTRACE_LLM_MAX_TOOL_STEPS` tool rounds and one timed investigation.
- An answer is shown only if every id it cites was returned by a tool during that question. Otherwise it is withheld and the
  gathered graph results stay visible, labelled as graph results.
- The model cannot approve, write or change anything, because no such tool exists.
- Provider failures return a fixed code: `invalid_key`, `forbidden`, `rate_limited`, `timeout`, `unavailable`,
  `insufficient_credits`, `bad_request` or `unexpected`. Provider text is never echoed.

## Not done yet

- **Workspace wiring.** The Ask input in `frontend/src/components/aidtrace/data.ts` (`askAgent`) and
  `workspace.tsx` are not connected to the endpoints. Both files had uncommitted edits from another session, so the backend
  was built first. The natural hook is `askAgent`'s final "not supported" branch: when `GET /aidtrace-agent/status` is ready,
  post to `/aidtrace-agent/ask` and show `answer` if present, otherwise the `message`.
- **Tools not wired.** Supplier search and profile, supplier dependencies, supply-chain risk scoring, cyber findings and
  investigation timeline are not registered. No read-only service path for them was found that could be reused safely.
  `check_evidence_validity` is covered by the eligibility fields in `get_memory_snapshot`.
- **No streaming and no memory across questions.** Each question is one self-contained investigation.
