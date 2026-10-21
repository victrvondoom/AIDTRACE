"""Start the Catalyst QC worker as Kairos's private worker (loopback only, shared-secret gateway auth).

    python scripts/start_catalyst_worker.py            # serves 127.0.0.1:8300

* Runs the unmodified Catalyst API (qc.api:app) inside its own virtualenv (integrations/catalyst/.venv), because its pins
  (pydantic 2.13, numpy 2.x, pandas 3, torch) conflict with Kairos's. Create it once with `uv sync` in integrations/catalyst.
* Its working directory is integrations/catalyst, because Catalyst reads data/ and writes out/ relative to that folder.
* Auth: CATALYST_GATEWAY_SECRET makes the worker refuse every request that does not carry the secret. The secret is generated
  once into var/catalyst/gateway.secret, and the Kairos API reads it from there (scripts/dev_harness.py).
* The DINOv2 weights load from the local Hugging Face cache. HF_HUB_OFFLINE defaults to 1, as in the Catalyst README.
"""
from __future__ import annotations

import os
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER_DIR = ROOT / "integrations" / "catalyst"
RUNTIME = Path(os.environ.get("CATALYST_RUNTIME_DIR") or ROOT / "var" / "catalyst")
VENV_PY = WORKER_DIR / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def gateway_secret() -> str:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    path = RUNTIME / "gateway.secret"
    if not path.exists():
        path.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    return path.read_text(encoding="utf-8").strip()


def main() -> int:
    if not VENV_PY.exists():
        print(f"Missing {VENV_PY}. Create it with: cd integrations/catalyst && uv sync")
        return 1
    env = dict(os.environ)
    env["CATALYST_GATEWAY_SECRET"] = gateway_secret()
    env.setdefault("HF_HUB_OFFLINE", "1")
    env["PYTHONUTF8"] = "1"
    port = os.environ.get("CATALYST_WORKER_PORT", "8300")
    print(f"Catalyst worker on http://127.0.0.1:{port} (gateway-only). Batches live in {WORKER_DIR / 'data'}")
    return subprocess.call(
        [str(VENV_PY), "-m", "uvicorn", "qc.api:app", "--host", "127.0.0.1", "--port", port],
        cwd=WORKER_DIR, env=env,
    )


if __name__ == "__main__":
    sys.exit(main())
