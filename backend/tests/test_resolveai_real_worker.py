"""The REAL RESOLVE-AI-main worker, driven through the Kairos gateway.

Unlike test_resolveai_platform.py (which stands in the worker with an httpx MockTransport), this module boots the
actual ResolveAI FastAPI app from integrations/resolveai in its own virtualenv, indexes a slice of its real
health-insurance corpus into a temporary runtime directory, and exercises case creation, routing, retrieval, evidence
scoring, tenant isolation, credential refusal and restart persistence over real HTTP.

It needs integrations/resolveai/.venv (see docs/integration/RESOLVEAI_MIGRATION.md) and the preserved
RESOLVE-AI-main/knowledge folder. When either is missing the whole module is SKIPPED with a BLOCKED reason; it is
never reported as passing. No external service or model key is used: the worker runs in its deterministic mode."""
from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_current_user
from api.routers import resolveai_platform as platform

ROOT = Path(__file__).resolve().parents[2]
WORKER_PY = ROOT / "integrations" / "resolveai" / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
WORKER_SRC = ROOT / "integrations" / "resolveai" / "backend"
KNOWLEDGE = ROOT.parent / "RESOLVE-AI-main" / "knowledge" / "health_insurance"
SECRET = "test-gateway-secret-not-a-real-credential"

pytestmark = pytest.mark.skipif(
    not (WORKER_PY.exists() and KNOWLEDGE.exists()),
    reason="BLOCKED_EXTERNAL_CONFIGURATION: needs integrations/resolveai/.venv and RESOLVE-AI-main/knowledge",
)

CASE = {
    "domain": "health_insurance",
    "title": "Cashless claim rejected for knee surgery",
    "institution_name": "Acme Health Insurance",
    "summary": "Insurer rejected a cashless hospitalisation claim for knee replacement citing a pre-existing condition, "
               "although the policy is four years old and the condition was disclosed at purchase.",
}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Worker:
    def __init__(self, runtime: Path) -> None:
        self.runtime, self.port, self.proc = runtime, _free_port(), None
        self.env = {**os.environ, "RESOLVEAI_RUNTIME_DIR": str(runtime), "PYTHONUTF8": "1", "PYTHONPATH": str(WORKER_SRC),
                    "KAIROS_GATEWAY_SECRET": SECRET, "ENVIRONMENT": "development", "VECTOR_STORE_BACKEND": "jsonl",
                    "GRAPH_STORE_BACKEND": "jsonl", "DISABLE_EXTERNAL_LLM": "true", "CACHE_ENABLED": "false"}
        for key in ("GEMINI_API_KEY", "NVIDIA_API_KEY"):
            self.env.pop(key, None)  # the test must never reach a paid provider

    def start(self) -> None:
        self.proc = subprocess.Popen([str(WORKER_PY), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(self.port)],
                                     cwd=self.runtime, env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + 90
        while time.time() < deadline:
            try:
                if httpx.get(f"{self.url}/health/live", timeout=2).status_code == 200:
                    return
            except httpx.HTTPError:
                time.sleep(0.5)
        raise RuntimeError("the real ResolveAI worker did not start")

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self.proc.wait(timeout=20)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


@pytest.fixture(scope="module")
def worker(tmp_path_factory):
    runtime = tmp_path_factory.mktemp("resolveai-runtime")
    ingest = subprocess.run(
        [str(WORKER_PY), str(ROOT / "scripts" / "ingest_resolveai_knowledge.py"), "--domains", "health_insurance", "--max-files", "8"],
        env={**os.environ, "RESOLVEAI_RUNTIME_DIR": str(runtime), "PYTHONUTF8": "1"}, capture_output=True, text=True, timeout=240)
    assert ingest.returncode == 0, ingest.stderr[-800:]
    w = Worker(runtime)
    w.start()
    yield w
    w.stop()


def gateway(worker: Worker, *, role="engineer", site="site_real_a", user_id="u1") -> TestClient:
    app = FastAPI()
    app.include_router(platform.router, prefix="/resolveai/platform")
    app.dependency_overrides[get_current_user] = lambda: {"user_id": user_id, "role": role, "site_id": site}
    os.environ["RESOLVEAI_GATEWAY_SECRET"] = SECRET
    os.environ["RESOLVEAI_WORKER_URL"] = worker.url
    return TestClient(app)


def test_the_worker_has_no_login_of_its_own(worker) -> None:
    assert httpx.get(f"{worker.url}/api/v1/cases").status_code == 401
    bad = httpx.get(f"{worker.url}/api/v1/cases", headers={"X-Kairos-Gateway-Secret": "wrong", "X-Kairos-User": "u", "X-Kairos-Tenant": "t"})
    assert bad.status_code == 401
    assert httpx.get(f"{worker.url}/api/v1/cases", headers={"Authorization": "Bearer anything"}).status_code == 401  # bearer tokens are refused


def test_status_reports_the_real_domain_packs(worker) -> None:
    body = gateway(worker).get("/resolveai/platform/status").json()
    assert body["connected"] is True
    ids = {d["id"] for d in body["domains"]}
    assert {"health_insurance", "banking", "telecom", "airlines", "housing", "ecommerce", "government", "healthcare"} <= ids


def test_case_to_cited_evidence_through_the_kairos_gateway(worker) -> None:
    c = gateway(worker)
    case = c.post("/resolveai/platform/cases", json=CASE).json()
    assert case["user_id"] == "site_real_a:u1" and case["status"] == "intake"

    result = c.post("/resolveai/platform/agents/investigate", json={"case_id": case["id"]}).json()
    assert result["mode"] == "retrieval_only" and result["llm_used"] is False
    assert result["synthesis"]["status"] == "NOT_RUN"
    assert result["domains_searched"][0] == "health_insurance"
    assert result["retrieval"][0]["indexed_points"] > 100  # the real corpus was indexed into the worker's own store
    assert result["evidence"], "retrieval returned no evidence from the indexed corpus"
    first = result["evidence"][0]
    assert first["title"] and first["retrieved_chunk"] and first["chunk_id"]
    assert 0.0 <= first["confidence"] <= 1.0 and "authority_score" in first["evidence_scores"]
    assert any(step.startswith("retrieve:health_insurance") for step in result["agent_trace"])

    runs = c.get("/resolveai/platform/agents/runs", params={"case_id": case["id"]}).json()["runs"]
    assert any(r["workflow_name"] == "kairos_evidence_investigation" for r in runs)


def test_the_full_agent_run_is_honest_without_a_model(worker) -> None:
    c = gateway(worker)
    case = c.post("/resolveai/platform/cases", json=CASE).json()
    run = c.post("/resolveai/platform/agents/run-case", json={"case_id": case["id"]}).json()
    assert run["workflow_engine"] == "langgraph"  # the real LangGraph pipeline executed
    assert "Offline fallback" in run["research_summary"] and run["review_output"]["approval_ready"] is False


def test_search_report_graph_trail_and_timeline_over_the_real_worker(worker) -> None:
    c = gateway(worker, site="site_real_views")
    hits = c.post("/resolveai/platform/search", json={"query": "waiting period pre-existing disease claim", "domain": "health_insurance"}).json()["hits"]
    assert hits and hits[0]["text"] and hits[0]["metadata"]

    case = c.post("/resolveai/platform/cases", json=CASE).json()
    c.post("/resolveai/platform/agents/investigate", json={"case_id": case["id"]})
    report = c.get("/resolveai/platform/report", params={"case_id": case["id"]}).json()
    assert report["case"]["id"] == case["id"] and len(report["agent_runs"]) >= 1
    graph = c.get("/resolveai/platform/case-graph", params={"case_id": case["id"]}).json()
    assert graph["nodes"] and graph["edges"]
    events = c.get("/resolveai/platform/timeline", params={"case_id": case["id"]}).json()["events"]
    assert any(e["event_type"] == "agent_run" for e in events)
    totals = c.get("/resolveai/platform/summary").json()["totals"]
    assert totals["cases"] >= 1
    # another tenant sees none of it
    other = gateway(worker, site="site_real_other")
    assert other.get("/resolveai/platform/report", params={"case_id": case["id"]}).json()["case"] is None
    assert other.get("/resolveai/platform/summary").json()["totals"]["cases"] == 0


def test_a_different_site_cannot_see_another_sites_case(worker) -> None:
    case = gateway(worker, site="site_real_a").post("/resolveai/platform/cases", json=CASE).json()
    other = gateway(worker, site="site_real_b")
    assert other.get("/resolveai/platform/case", params={"case_id": case["id"]}).status_code == 404
    assert other.post("/resolveai/platform/agents/investigate", json={"case_id": case["id"]}).status_code == 404


def test_cases_survive_a_worker_restart(worker) -> None:
    case = gateway(worker).post("/resolveai/platform/cases", json=CASE).json()
    worker.stop()
    worker.start()
    again = gateway(worker).get("/resolveai/platform/case", params={"case_id": case["id"]})
    assert again.status_code == 200 and again.json()["id"] == case["id"]
