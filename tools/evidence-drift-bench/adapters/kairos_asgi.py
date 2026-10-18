"""Mount the unmodified Kairos drift router in an isolated in-process ASGI app."""

from __future__ import annotations

import importlib.util
import json
import secrets
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from adapters.kairos_api import KairosAPIError


def create_isolated_app(backend: Path, db_url: str, graph_prefix: str, site_id: str, token: str):
    """Use the real router/store/engine with only settings and identity overridden.

    Kairos's routers package imports the whole application at package import time. A
    package shell avoids those unrelated startup imports while executing drift.py
    directly from its unchanged source path. No network listener or app lifespan runs.
    """
    backend = backend.resolve()
    drift_file = backend / "api" / "routers" / "drift.py"
    if not drift_file.is_file() or not (backend / "api" / "services" / "drift" / "store.py").is_file():
        raise FileNotFoundError("Kairos backend drift router/store not found")
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(backend))
    from api import dependencies
    from fastapi import FastAPI, HTTPException

    routers = types.ModuleType("api.routers")
    routers.__path__ = [str(drift_file.parent)]
    sys.modules["api.routers"] = routers
    spec = importlib.util.spec_from_file_location("api.routers.drift", drift_file)
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load real Kairos drift router")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    settings = SimpleNamespace(
        FALKORDB_URL=db_url, FALKORDB_GRAPH_PREFIX=graph_prefix,
        FALKORDB_QUERY_TIMEOUT_MS=5000, DRIFT_MAX_DEPTH=12, DRIFT_MAX_EDGES=5000,
    )

    async def test_identity(request):
        if request.headers.get("authorization") != f"Bearer {token}":
            raise HTTPException(status_code=401, detail="Benchmark test token required")
        return {"user_id": "edb-asgi-" + site_id, "role": "engineer", "site_id": site_id}

    # FastAPI inspects this annotation to inject the request instead of treating
    # it as a query value. Resolve it from the imported runtime's Request class.
    from fastapi import Request

    test_identity.__annotations__["request"] = Request
    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[dependencies.get_settings] = lambda: settings
    app.dependency_overrides[dependencies.get_current_user] = test_identity
    return app


class ASGIKairosTransport:
    """Synchronous transport for the existing KairosAPIAdapter and real TestClient."""

    def __init__(self, app) -> None:
        from fastapi.testclient import TestClient

        self.client = TestClient(app, raise_server_exceptions=False)
        self.last_status_code: int | None = None

    def __enter__(self):
        self.client.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        return self.client.__exit__(exc_type, exc, tb)

    def __call__(self, method: str, path: str, payload: dict[str, Any] | None, token: str) -> dict[str, Any]:
        if not path.startswith("/drift/"):
            raise ValueError("Only genuine drift routes are mounted")
        response = self.client.request(method, path, json=payload, headers={"Authorization": f"Bearer {token}"})
        self.last_status_code = response.status_code
        if response.status_code >= 400:
            raise KairosAPIError(f"Kairos ASGI returned HTTP {response.status_code} for {method} {path}", response.status_code)
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise KairosAPIError("Kairos ASGI returned invalid JSON") from exc
        if not isinstance(data, dict):
            raise KairosAPIError("Kairos ASGI returned a non-object for an object route")
        return data


def new_isolated_names() -> tuple[str, str, str]:
    suffix = secrets.token_hex(5).upper()
    return f"EDB_BENCH_{suffix}", f"EDB_BENCH_{suffix}", secrets.token_urlsafe(32)
