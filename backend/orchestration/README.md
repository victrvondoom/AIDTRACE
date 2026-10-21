# orchestration: LLM agent workflows on SGLang

Run a workflow of LLM agents against an SGLang server, or against a deterministic dry-run backend.
Agents can call only the tools they are granted, failures are retried only when they are retryable,
and every decision is written to a redacted trace.

Written for: engineers who will run workflows, and engineers who will extend the package.

Run every command from the `backend/` directory, with the repository virtualenv.

## 1. Quick start (users)

**a. Start an SGLang server**, following SGLang's current documentation for your model. The default
OpenAI-compatible API is what this package uses. The default port is 30000. An example launch looks like
`python -m sglang.launch_server --model-path <model> --port 30000`; check the flags against the version you install.

**b. Configure** (environment variables, all optional except the model when you use a real server):

| Variable | Default | Meaning |
|---|---|---|
| `SGLANG_BASE_URL` | `http://127.0.0.1:30000` | Server URL. Plain `http(s)`, no credentials in the URL. |
| `SGLANG_MODEL` | none | Model name the server serves. Required for `run --backend sglang`. |
| `SGLANG_API_KEY` | none | Sent as a bearer token if your server enforces one. Never printed or traced. |
| `ORCH_REQUEST_TIMEOUT_S` | `60` | Per-request HTTP timeout. |
| `ORCH_MAX_CONCURRENCY` | `8` | Maximum concurrent requests from this process. |

**c. Check the server**

```
python -m orchestration doctor --model <model>          # does it answer, and does it serve the model?
python -m orchestration doctor --model <model> --ping   # also proves a completion works
```

`doctor` reports one of `OK`, `MODEL_NOT_LISTED`, `AUTH_REJECTED`, `UNREACHABLE`, `TIMEOUT`, or
`PROTOCOL_ERROR`, and exits 3 unless the server is healthy. `OK` means the server answered and listed the
model. Only `--ping` shows that generation works.

**d. Validate a workflow** (no model is called):

```
python -m orchestration validate orchestration/examples/demo_workflow.json --tools orchestration.examples.demo_tools:REGISTRY
```

**e. Dry run** (no server needed; the scripted backend echoes its input and is not a model):

```
python -m orchestration run orchestration/examples/demo_workflow.json --backend scripted --tools orchestration.examples.demo_tools:REGISTRY
```

**f. Real run:**

```
python -m orchestration run orchestration/examples/demo_workflow.json --model <model> --tools orchestration.examples.demo_tools:REGISTRY --out trace.json
```

Add `--json` for a machine-readable summary. `--out` writes the complete trace.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Success: `doctor` healthy, `validate` passed, or the run `SUCCEEDED`. |
| 1 | The run finished as `PARTIAL` or `FAILED`. |
| 2 | Usage, configuration, or workflow error. The message goes to stderr. |
| 3 | `doctor` found the server unhealthy. |
| 130 | Interrupted. Running tasks are cancelled before exit. |

## 2. Workflow format

A workflow is one JSON document:

```json
{
  "name": "brief-from-notes",
  "agents": {
    "analyst": {"system": "Extract three facts.", "max_steps": 3, "tools": ["word_count"]},
    "writer": {"system": "Write two sentences.", "max_steps": 2}
  },
  "tasks": [
    {"id": "extract", "agent": "analyst", "input": "Notes: ..."},
    {"id": "brief", "agent": "writer", "input": "Bullet points:\n{extract}", "depends_on": ["extract"], "retries": 1, "timeout_s": 60}
  ],
  "failure_policy": "fail_fast",
  "max_parallel": 4
}
```

| Field | Rules |
|---|---|
| `agents.<name>.system` | Required. 1 to 8000 characters. |
| `agents.<name>.max_steps` | 1 to 20 model calls per task attempt. Default 4. |
| `agents.<name>.tools` | Names of registered tools this agent may call. Default none. |
| `agents.<name>.temperature`, `max_tokens`, `tool_timeout_s` | Optional, with bounds enforced. |
| `tasks[].id` | Letter or underscore first; then letters, digits, `-`, `_`. Unique. |
| `tasks[].agent` | Must name an agent. |
| `tasks[].input` | 1 to 20000 characters. `{task_id}` inserts that task's output. Only tasks it depends on may be referenced. |
| `tasks[].depends_on` | Task ids that must succeed first. The graph must be acyclic. |
| `tasks[].retries` | 0 to 5 extra attempts, used only for retryable failures. |
| `tasks[].timeout_s` | Wall-clock limit per attempt. Default 120. |
| `failure_policy` | `fail_fast` (default) or `continue`. |
| `max_parallel` | 1 to 64 tasks in flight. Default 4. |

Unknown fields are rejected, so a typo fails validation instead of being ignored.

### Failure and retry semantics

| Situation | Result |
|---|---|
| Timeout, unreachable server, rate limit (429), or 5xx | Retryable. Retried with exponential backoff (0.5 s base, 8 s cap) until the task's `retries` budget is spent. |
| 401/403, other 4xx, malformed response, or a model that never answers | Not retried. The task is `FAILED`. |
| Tool error or refused tool call | Not a task failure. The error is returned to the model so it can recover. Each attempt is bounded by `max_steps`. |
| `fail_fast` and a task fails | Running tasks are cancelled (`CANCELLED`), and unstarted tasks are cancelled. |
| `continue` and a task fails | Only its dependents are `SKIPPED`. Independent tasks keep running. |
| Run status | `SUCCEEDED` if every task succeeded, `PARTIAL` if some did, `FAILED` if none did. |

## 3. Tools (developers)

A tool is a Python function plus a JSON schema. Agents see only the tools they are granted, and a call
to any other tool is refused and recorded as `TOOL_DENIED`.

```python
# myproject/tools.py
from orchestration import ToolRegistry

REGISTRY = ToolRegistry()

def lookup_price(sku: str) -> dict:
    return {"sku": sku, "price_eur": 12.5}

REGISTRY.register(
    "lookup_price",
    lookup_price,
    description="Return the catalogue price for a SKU.",
    parameters={"type": "object", "properties": {"sku": {"type": "string"}}, "required": ["sku"]},
)
```

Load it with `--tools myproject.tools:REGISTRY`. Async functions are supported. Sync functions run in a
worker thread: a timeout stops waiting for them but cannot kill them, so keep tools side-effect-aware.
Results are capped at 8000 characters.

## 4. Python API

```python
import asyncio
from orchestration import SGLangBackend, RetryPolicy, load_workflow, run_workflow
from myproject.tools import REGISTRY

workflow = load_workflow("orchestration/examples/demo_workflow.json", tools=REGISTRY)

async def main():
    async with SGLangBackend(base_url="http://127.0.0.1:30000", model="my-model", api_key=None) as backend:
        return await run_workflow(workflow, backend=backend, tools=REGISTRY, retry=RetryPolicy(base_s=0.5))

result = asyncio.run(main())
print(result.status, result.outputs)
print(result.trace.to_json())
```

## 5. Adding a provider

Implement the `ChatBackend` protocol: a `name` attribute and one coroutine,
`chat(messages, *, tools, temperature, max_tokens) -> ChatResponse`. Raise `BackendError(message, kind=..., retryable=...)`
for failures, and set `retryable` honestly. The scheduler and the agent loop need nothing else.
`ScriptedBackend` is the smallest example.

## 6. Traces and sensitivity

A trace is a list of events: `RUN_STARTED`, `TASK_STARTED`, `ATTEMPT_STARTED`, `LLM_REQUEST`,
`LLM_RESPONSE` (with token counts and latency), `TOOL_CALLED`, `TOOL_COMPLETED`, `TOOL_ERROR`,
`TOOL_DENIED`, `AGENT_ANSWERED`, `TASK_RETRY`, `TASK_SUCCEEDED`, `TASK_FAILED`, `TASK_SKIPPED`,
`TASK_CANCELLED`, and `RUN_COMPLETED`.

Traces record tool arguments (up to 500 characters) and failure messages, which can contain user
content. Treat trace files as sensitive. The API key is redacted from the trace by value, and it never
enters the trace by construction: the key lives only in the HTTP client's headers. `Settings.__repr__`
shows only whether a key is set.

## 7. Limits (read before relying on this)

- **No benchmarks.** Nothing here measures latency, throughput, or cost for SGLang. Make those claims only
  after measuring your model on your hardware.
- **`scripted` is not a model.** Its outputs echo the input.
- **`doctor OK` is not a quality guarantee.** It proves the server answers, lists the model, and, with `--ping`,
  completes one request.
- **Retries are in-process.** The scheduler does not persist runs. If the process dies, the run is lost.
  The AIDTRACE coordination layer in `api/services/coordination/` is the FalkorDB-backed, durable path;
  this package is standalone and does not use it.
- **Tool timeouts cannot kill sync tools.** See section 3.
- **Tool calling depends on the model.** The request includes `tools`, and SGLang's tool-call parsing depends
  on the model and server flags. Validate tool use with your model before depending on it.
- **Single process.** Concurrency limits apply within one process only.

## 8. Tests

From `backend/`:

```
../.venv/Scripts/python.exe -m pytest -p no:cacheprovider -q tests/test_orchestration_*.py
```

The suite covers the protocol and status-code mapping (mocked transport), the agent loop and tool grants,
scheduling (concurrency bound, dependency ordering, retries, timeouts, both failure policies, redaction),
and a fake SGLang server on a real localhost socket that exercises the doctor, the API, and the CLI.

## 9. Layout

| File | Role |
|---|---|
| `backends.py` | `ChatBackend` protocol, `SGLangBackend`, `ScriptedBackend` |
| `agents.py` | `AgentSpec` and the agent loop with tool grants |
| `tools.py` | `ToolRegistry` and `load_registry` |
| `workflow.py` | Workflow schema, validation, and placeholder rendering |
| `scheduler.py` | Parallel DAG execution, retries, and failure policy |
| `trace.py` | Append-only, redacted event log |
| `doctor.py` | Server preflight |
| `config.py` | Environment settings and URL validation |
| `cli.py`, `__main__.py` | `python -m orchestration` |
| `examples/` | Demo workflow and tool registry |
