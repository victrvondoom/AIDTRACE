"""Local-only API check using a disposable site graph, never an account graph."""
from __future__ import annotations

import os
import uuid

import pytest
from api.dependencies import get_current_user, get_falkor_drift_store
from api.routers.graphlab import router as graphlab_router
from api.routers.health import router as health_router
from api.services.drift.model import Label
from api.services.drift.store import FalkorDriftStore
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    url = os.getenv("FALKORDB_TEST_URL")
    if not url:
        pytest.skip("set FALKORDB_TEST_URL to a disposable local FalkorDB instance")
    store = FalkorDriftStore(url, graph_prefix=f"pytest_{uuid.uuid4().hex[:12]}")
    site = f"site_{uuid.uuid4().hex[:8]}"
    app = FastAPI()
    app.include_router(graphlab_router, prefix="/graphlab")
    app.include_router(health_router, prefix="/health")
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "synthetic", "role": "engineer", "site_id": site}
    app.dependency_overrides[get_falkor_drift_store] = lambda: store
    try:
        yield TestClient(app), store, site
    finally:
        if store.graph_name(site) in store._client.list_graphs():
            store._graph(site).delete()
        store.close()


def test_site_graph_health_and_read_only_cypher(client) -> None:
    api, store, site = client
    assert api.get("/health/falkordb").json() == {"reachable": True, "site_graph_exists": False}
    store.upsert_node(site, Label.SOURCE_VERSION, "source-1", {"status": "ACTIVE"})
    graph = api.get("/graphlab/site-graph")
    assert graph.status_code == 200, graph.text
    assert graph.json()["falkordb"]["graph_name"] == store.graph_name(site)
    assert api.get("/health/falkordb").json()["site_graph_exists"] is True
    read = api.post("/graphlab/site-cypher", json={"query": "MATCH (n) RETURN count(n) AS total"})
    assert read.status_code == 200, read.text
    assert read.json()["rows"][0][0] == 1
    assert api.post("/graphlab/site-cypher", json={"query": "CREATE (:Test {id: 'bad'})"}).status_code == 422
    assert store.read_node(site, "bad") is None
