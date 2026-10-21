"""End-to-end over a real socket: a fake SGLang server on 127.0.0.1 with an ephemeral port.

This exercises the same code paths a live SGLang server would: real HTTP, real status codes, real
Authorization headers, and the doctor and CLI on top of them.
"""

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from orchestration.backends import SGLangBackend
from orchestration.cli import main
from orchestration.doctor import Health, probe
from orchestration.scheduler import RetryPolicy, TaskState, run_workflow
from orchestration.workflow import load_workflow

API_KEY = "sk-test-key-123456"
MODEL = "demo-model"


class _FakeSGLang(BaseHTTPRequestHandler):
    server_version = "FakeSGLang/0.1"

    def log_message(self, format, *args):  # keep test output quiet
        return

    def _authorized(self) -> bool:
        expected = self.server.api_key
        return expected is None or self.headers.get("Authorization") == f"Bearer {expected}"

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self._authorized():
            return self._send(401, {"error": "unauthorized"})
        if self.path == "/v1/models":
            return self._send(200, {"object": "list", "data": [{"id": MODEL, "object": "model"}]})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        # Read the body before answering, as a real server does. Replying early leaves unread bytes
        # on the socket, which the client sees as a dropped connection rather than the HTTP status.
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) or b"{}"
        if not self._authorized():
            return self._send(401, {"error": "unauthorized"})
        if self.path != "/v1/chat/completions":
            return self._send(404, {"error": "not found"})
        request = json.loads(raw)
        last = request["messages"][-1]["content"]
        if "boom" in last:
            return self._send(503, {"error": "overloaded"})
        return self._send(
            200,
            {
                "choices": [
                    {"index": 0, "message": {"role": "assistant", "content": f"echo: {last}"}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 4, "completion_tokens": 2},
            },
        )


@pytest.fixture
def fake_sglang():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeSGLang)
    server.api_key = API_KEY
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_doctor_reports_ok_and_proves_generation(fake_sglang):
    report = asyncio.run(probe(fake_sglang, api_key=API_KEY, model=MODEL, ping=True))
    assert report.status is Health.OK
    assert report.models == (MODEL,)
    assert report.generation == "OK"


def test_doctor_reports_a_rejected_key(fake_sglang):
    report = asyncio.run(probe(fake_sglang, api_key="wrong-key-000000", model=MODEL))
    assert report.status is Health.AUTH_REJECTED


def test_doctor_reports_a_missing_model_and_what_is_served(fake_sglang):
    report = asyncio.run(probe(fake_sglang, api_key=API_KEY, model="other-model"))
    assert report.status is Health.MODEL_NOT_LISTED
    assert MODEL in report.detail


def test_doctor_reports_an_unreachable_server():
    report = asyncio.run(probe("http://127.0.0.1:1", model=MODEL))
    assert report.status is Health.UNREACHABLE


def test_workflow_runs_end_to_end_over_http(fake_sglang):
    workflow = load_workflow(
        {
            "name": "http-e2e",
            "agents": {"a": {"system": "Echo politely.", "max_steps": 2}},
            "tasks": [
                {"id": "first", "agent": "a", "input": "hello"},
                {"id": "second", "agent": "a", "input": "{first}", "depends_on": ["first"]},
            ],
        }
    )

    async def scenario():
        async with SGLangBackend(base_url=fake_sglang, model=MODEL, api_key=API_KEY) as backend:
            return await run_workflow(workflow, backend=backend, retry=RetryPolicy(base_s=0.0))

    result = asyncio.run(scenario())
    assert result.status == "SUCCEEDED"
    assert result.outputs["first"] == "echo: hello"
    assert result.outputs["second"] == "echo: echo: hello"
    llm_events = [e for e in result.trace.events if e.type == "LLM_RESPONSE"]
    assert len(llm_events) == 2
    assert all(e.data["latency_ms"] >= 0 for e in llm_events)
    assert API_KEY not in result.trace.to_json()


def test_server_error_is_retried_then_reported(fake_sglang):
    workflow = load_workflow(
        {
            "name": "retry-e2e",
            "agents": {"a": {"system": "Answer.", "max_steps": 1}},
            "tasks": [{"id": "a", "agent": "a", "input": "boom please", "retries": 1}],
        }
    )

    async def scenario():
        async with SGLangBackend(base_url=fake_sglang, model=MODEL, api_key=API_KEY) as backend:
            return await run_workflow(workflow, backend=backend, retry=RetryPolicy(base_s=0.0))

    result = asyncio.run(scenario())
    assert result.states["a"] is TaskState.FAILED
    assert "HTTP 503" in result.errors["a"]
    attempts = [e for e in result.trace.events if e.type == "ATTEMPT_STARTED"]
    assert len(attempts) == 2


def test_wrong_key_fails_the_task_without_retrying(fake_sglang):
    workflow = load_workflow(
        {
            "name": "auth-e2e",
            "agents": {"a": {"system": "Answer.", "max_steps": 1}},
            "tasks": [{"id": "a", "agent": "a", "input": "hi", "retries": 3}],
        }
    )

    async def scenario():
        async with SGLangBackend(base_url=fake_sglang, model=MODEL, api_key="wrong-key-000000") as backend:
            return await run_workflow(workflow, backend=backend, retry=RetryPolicy(base_s=0.0))

    result = asyncio.run(scenario())
    assert result.states["a"] is TaskState.FAILED
    assert "rejected the API key" in result.errors["a"]
    assert len([e for e in result.trace.events if e.type == "ATTEMPT_STARTED"]) == 1


def test_cli_doctor_exit_codes_follow_the_report(fake_sglang, monkeypatch, capsys):
    monkeypatch.delenv("SGLANG_API_KEY", raising=False)
    assert main(["doctor", "--base-url", fake_sglang, "--model", MODEL]) == 3  # no key: server answers 401
    capsys.readouterr()  # discard the human-readable line so the next output parses as JSON

    monkeypatch.setenv("SGLANG_API_KEY", API_KEY)
    assert main(["doctor", "--base-url", fake_sglang, "--model", MODEL, "--ping", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "OK"
    assert payload["generation"] == "OK"

    monkeypatch.setenv("SGLANG_API_KEY", "wrong-key-000000")
    assert main(["doctor", "--base-url", fake_sglang, "--model", MODEL]) == 3


def test_cli_run_uses_the_sglang_server_and_writes_a_redacted_trace(fake_sglang, monkeypatch, tmp_path, capsys):
    example = Path(__file__).resolve().parents[1] / "orchestration" / "examples" / "demo_workflow.json"
    trace_path = tmp_path / "trace.json"
    monkeypatch.setenv("SGLANG_API_KEY", API_KEY)
    monkeypatch.delenv("SGLANG_MODEL", raising=False)

    code = main(
        [
            "run",
            str(example),
            "--tools",
            "orchestration.examples.demo_tools:REGISTRY",
            "--base-url",
            fake_sglang,
            "--model",
            MODEL,
            "--out",
            str(trace_path),
            "--json",
        ]
    )
    assert code == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["status"] == "SUCCEEDED"
    assert summary["tasks"]["brief"]["output"].startswith("echo: ")
    assert API_KEY not in trace_path.read_text(encoding="utf-8")
