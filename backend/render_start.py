"""Render entrypoint: the real Kairos API without a Supabase project (same approach as scripts/dev_harness.py).

Every real router, middleware and graph store stays; only the Supabase client dependency is stubbed, and the
documented development bypass (APP_ENV=development, no token => "dev-user") stands in for sign-in. This is a
demo deployment: it has no real authentication. Once SUPABASE_URL is set, the normal uvicorn API is used instead.
"""
from __future__ import annotations

import os

import uvicorn

port = int(os.environ.get("PORT", "8000"))

# Render's private network hands us host:port for the FalkorDB service.
if os.environ.get("FALKORDB_HOSTPORT") and not os.environ.get("FALKORDB_URL"):
    os.environ["FALKORDB_URL"] = f"redis://{os.environ['FALKORDB_HOSTPORT']}"

if os.environ.get("SUPABASE_URL"):
    uvicorn.run("api.main:app", host="0.0.0.0", port=port, forwarded_allow_ips="*")
else:
    os.environ.setdefault("APP_ENV", "development")
    os.environ.setdefault("OTEL_SDK_DISABLED", "true")

    from api import dependencies as deps
    from api.main import app

    class _NoSupabase:
        """Any use of the data service fails loudly instead of pretending to succeed."""

        def __getattr__(self, name: str):
            raise RuntimeError(f"Supabase is not configured on this deployment (used .{name}).")

    app.dependency_overrides[deps.get_supabase] = lambda: _NoSupabase()
    uvicorn.run(app, host="0.0.0.0", port=port, forwarded_allow_ips="*")
