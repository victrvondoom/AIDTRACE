"""DEVELOPMENT ONLY: run the real Kairos API on a machine that has no Supabase project.

Kairos normally needs Supabase for sign-in and for several data routes. This launcher keeps every real router,
middleware and graph store, stubs only the Supabase *client* dependency, and relies on the documented
development bypass (no token + APP_ENV=development => the engineer "dev-user"). It therefore exercises the
integrated routes against real FalkorDB, but it proves NOTHING about authentication. Real-login verification is
reported separately as BLOCKED_EXTERNAL_CONFIGURATION until Supabase credentials exist.

    python scripts/dev_harness.py            # serves http://127.0.0.1:8100

Refuses to start unless APP_ENV is "development" (the default here) and binds to loopback only.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
os.environ.setdefault("FALKORDB_URL", "redis://localhost:6380")
os.environ.setdefault("GREENCHAIN_DATA_DIR", str(ROOT / "backend" / "domains" / "greenchain" / "data"))
os.environ.setdefault("CORS_ORIGINS", '["http://localhost:3000"]')

# Private ResolveAI worker (scripts/start_resolveai_worker.py): share its generated gateway secret with this API.
_secret_file = ROOT / "var" / "resolveai" / "gateway.secret"
if _secret_file.exists():
    os.environ.setdefault("RESOLVEAI_GATEWAY_SECRET", _secret_file.read_text(encoding="utf-8").strip())
    os.environ.setdefault("RESOLVEAI_WORKER_URL", "http://127.0.0.1:8200")

if os.environ["APP_ENV"] != "development":
    sys.exit("dev_harness.py only runs with APP_ENV=development.")
if os.environ.get("SUPABASE_URL"):
    sys.exit("Supabase is configured; run the real API (uvicorn api.main:app) instead of the harness.")

sys.path.insert(0, str(ROOT / "backend"))

import uvicorn  # noqa: E402

from api import dependencies as deps  # noqa: E402
from api.main import app  # noqa: E402


class _NoSupabase:
    """Any use of the data service fails loudly instead of pretending to succeed."""

    def __getattr__(self, name: str):  # pragma: no cover - only reached on misuse
        raise RuntimeError(f"Supabase is not available in the development harness (used .{name}).")


app.dependency_overrides[deps.get_supabase] = lambda: _NoSupabase()

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("KAIROS_API_PORT", "8100")), log_level="info")
