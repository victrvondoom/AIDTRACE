"""Start the REAL RESOLVE-AI-main backend as Kairos's private worker (loopback only, trusted-gateway auth).

    python scripts/start_resolveai_worker.py            # serves 127.0.0.1:8200

* Runs the unmodified ResolveAI FastAPI app from integrations/resolveai/backend inside its own virtualenv
  (integrations/resolveai/.venv), because its pins (pydantic 2.10, FastAPI 0.115, langgraph) conflict with Kairos's.
* Its working directory is var/resolveai, so every file it writes (cases, agent runs, vectors, graph) lives there and
  never in the preserved source tree. Nothing is read from or written to Supabase, Qdrant, Neo4j or Redis unless you
  configure them; the worker's own JSONL stores are its supported local mode.
* Auth: KAIROS_GATEWAY_SECRET makes the worker accept only the Kairos gateway (no login of its own). The secret is
  generated once into var/resolveai/gateway.secret; the Kairos API reads RESOLVEAI_GATEWAY_SECRET from the same file
  via scripts/dev_harness.py.
* Models: with GEMINI_API_KEY or NVIDIA_API_KEY set, the worker calls that provider. With neither, it runs with
  DISABLE_EXTERNAL_LLM=true, so agents use their deterministic code paths and nothing claims live LLM reasoning.
"""
from __future__ import annotations

import os
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER_SRC = ROOT / "integrations" / "resolveai" / "backend"
RUNTIME = Path(os.environ.get("RESOLVEAI_RUNTIME_DIR") or ROOT / "var" / "resolveai")
VENV_PY = ROOT / "integrations" / "resolveai" / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def gateway_secret() -> str:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    path = RUNTIME / "gateway.secret"
    if not path.exists():
        path.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    return path.read_text(encoding="utf-8").strip()


def main() -> int:
    if not VENV_PY.exists():
        print(f"Missing {VENV_PY}. Create it with: python -m venv \"integrations/resolveai/.venv\" && "
              "\"integrations/resolveai/.venv/Scripts/pip\" install -r \"integrations/resolveai/backend/requirements.txt\"")
        return 1
    env = dict(os.environ)
    env["KAIROS_GATEWAY_SECRET"] = gateway_secret()
    env.setdefault("ENVIRONMENT", "development")
    env.setdefault("VECTOR_STORE_BACKEND", "jsonl")
    env.setdefault("GRAPH_STORE_BACKEND", "jsonl")
    # The worker's response/embedding cache is TTL-bound Redis keys. Point it at Kairos's own FalkorDB server (a Redis
    # server) rather than the default localhost:6379, which may belong to another project.
    env.setdefault("REDIS_URL", os.environ.get("FALKORDB_URL", "redis://127.0.0.1:6380"))
    env["PYTHONPATH"] = str(WORKER_SRC)
    env["PYTHONUTF8"] = "1"
    live_model = bool(env.get("GEMINI_API_KEY") or env.get("NVIDIA_API_KEY"))
    env["DISABLE_EXTERNAL_LLM"] = "false" if live_model else "true"
    print(f"ResolveAI worker: {'live model provider' if live_model else 'deterministic mode (no model key, no external LLM calls)'}")
    port = os.environ.get("RESOLVEAI_WORKER_PORT", "8200")
    return subprocess.call(
        [str(VENV_PY), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", port],
        cwd=RUNTIME, env=env,
    )


if __name__ == "__main__":
    sys.exit(main())
