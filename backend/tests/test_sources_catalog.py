"""Source library, Graph Lab and Sources API tests (HTTP layer, role gates, real-FalkorDB parity)."""
from __future__ import annotations

import hashlib
import os
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_current_user, get_falkor_drift_store
from api.routers.graphlab import router as graphlab_router
from api.routers.sources import router as sources_router
from api.services.drift.demo_workflow import run_evidence_supersession
from api.services.drift.store import FalkorDriftStore
from api.services.graphlab.registry import ALGORITHMS
from api.services.sources import catalog


def test_catalog_accounts_for_all_98_repositories_without_inventing_readmes() -> None:
    rows = catalog.ledger()
    assert len(rows) == 98 and len({r["repo"] for r in rows}) == 98
    present = [r for r in rows if r["readme"]["present"]]
    assert len(present) + sum(1 for r in rows if r["blocked_reason"]) == 98
    files = list((catalog.DIR / "readmes").glob("*.md"))
    assert len(files) == len(present)
    for item in catalog._catalog():
        if item["readme"]:
            raw = (catalog.DIR / "readmes" / item["readme"]["file"]).read_bytes()
            assert hashlib.sha256(raw).hexdigest() == item["readme"]["sha256"]  # faithful, unmodified copy
        else:
            assert not (catalog.DIR / "readmes" / f"{item['slug']}.md").exists()


def test_every_engine_source_is_a_catalogued_repository() -> None:
    urls = catalog.repo_urls()
    for engine in ALGORITHMS.values():
        assert not [r for r in engine.sources if r not in urls], f"{engine.id} cites an unknown repository"


def test_ledger_claims_only_evidenced_stages() -> None:
    for row in catalog.ledger():
        if "INTEGRATED" in row["stages"]:
            assert row["engines"] or row["repo"] in catalog.PRIOR_INTEGRATIONS
        if "BROWSER_VERIFIED" in row["stages"]:  # only for engines named in verification.json
            assert set(row["engines"]) & catalog._verified_engines()
        if row["blocked_reason"]:  # a missing README never claims README_READ; no evidence at all is BLOCKED
            assert not row["readme"]["present"] and "README_READ" not in row["stages"]
            assert row["stage"] == (row["stages"][-1] if row["stages"] else "BLOCKED")


def test_readme_lookup_rejects_traversal_and_unknown_slugs() -> None:
    assert catalog.readme("../../etc__passwd") is None
    assert catalog.readme("nobody__nothing") is None
    first = next(r for r in catalog.ledger() if r["readme"]["present"])
    found = catalog.readme(first["slug"])
    assert found and found["untrusted"] is True and len(found["text"].encode()) >= min(found["bytes"], 1)


def make_client(role: str = "engineer", store=None) -> TestClient:
    app = FastAPI()
    app.include_router(graphlab_router, prefix="/graphlab")
    app.include_router(sources_router, prefix="/sources")
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "synthetic", "role": role, "site_id": "site_test"}
    if store is not None:
        app.dependency_overrides[get_falkor_drift_store] = lambda: store
    return TestClient(app)


def test_graphlab_api_runs_scenario_payload_and_rejects_bad_requests() -> None:
    client = make_client()
    assert len(client.get("/graphlab/algorithms").json()["algorithms"]) == len(ALGORITHMS)
    ran = client.post("/graphlab/analyze", json={"algorithm": "min_cut", "scenario": "cloud_attack",
                                                 "params": {"sources": ["internet"], "targets": ["customer-db"]}})
    assert ran.status_code == 200, ran.text
    body = ran.json()
    assert body["result"]["summary"]["verified"] is True and body["provenance"]["status"] == "INTEGRATED_TESTED"
    assert body["provenance"]["readme_derived_hypothesis_from"][0]["url"].startswith("https://github.com/")
    graph = {"nodes": [{"id": "a"}, {"id": "b"}], "edges": [{"source": "b", "target": "a"}]}
    custom = client.post("/graphlab/analyze", json={"algorithm": "blast_radius", "graph": graph, "params": {"changed": ["a"]}})
    assert custom.json()["result"]["node_marks"]["b"] == "impacted"
    for bad in (
        {"algorithm": "nope", "scenario": "transit"},
        {"algorithm": "route", "scenario": "transit", "graph": graph},
        {"algorithm": "route"},
        {"algorithm": "route", "scenario": "transit", "params": {"source": "ghost", "target": "stn-airport"}},
        {"algorithm": "route", "graph": {"nodes": [{"id": "../x"}], "edges": []}},
    ):
        assert client.post("/graphlab/analyze", json=bad).status_code in (404, 422), bad


def test_graphlab_and_sources_are_staff_only() -> None:
    client = make_client("field_worker")
    assert client.get("/graphlab/scenarios").status_code == 403
    assert client.post("/graphlab/analyze", json={"algorithm": "route", "scenario": "transit"}).status_code == 403
    assert client.get("/sources/summary").status_code == 403


def test_sources_api_filters_and_serves_readmes_as_untrusted_text() -> None:
    client = make_client()
    assert client.get("/sources/summary").json()["repositories"] == 98
    engine_rows = client.get("/sources/repos", params={"engine": "min_cut"}).json()
    assert engine_rows["total"] == len(ALGORITHMS["min_cut"].sources)
    search = client.get("/sources/repos", params={"q": "interdict"}).json()["items"]
    assert search and search[0]["repo"] == "YashSoni998265/interdict"
    readme = client.get("/sources/readme", params={"slug": search[0]["slug"]}).json()
    assert readme["untrusted"] is True and readme["text"]
    assert client.get("/sources/readme", params={"slug": "nobody__nothing"}).status_code == 404
    assert client.get("/sources/readme", params={"slug": "../../secrets__x"}).status_code == 422
    assert client.get("/sources/ledger").json()["items"][0]["stages"]


@pytest.fixture
def live_store():
    url = os.getenv("FALKORDB_TEST_URL")
    if not url:
        pytest.skip("set FALKORDB_TEST_URL to run local FalkorDB integration coverage")
    store = FalkorDriftStore(url, graph_prefix=f"pytest_{uuid.uuid4().hex[:12]}", query_timeout_ms=5000, max_depth=8)
    site = f"site_{uuid.uuid4().hex[:8]}"
    try:
        yield store, site
    finally:
        if store.graph_name(site) in store._client.list_graphs():
            store._graph(site).delete()
        store.close()


def test_site_graph_blast_radius_matches_the_drift_store_on_real_falkordb(live_store) -> None:
    store, site = live_store
    run_evidence_supersession(store, site)
    app = FastAPI()
    app.include_router(graphlab_router, prefix="/graphlab")
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "synthetic", "role": "engineer", "site_id": site}
    app.dependency_overrides[get_falkor_drift_store] = lambda: store
    client = TestClient(app)

    exported = client.get("/graphlab/site-graph").json()
    assert not exported["empty"] and {n["id"] for n in exported["graph"]["nodes"]} >= {"DEMO-DRIFT-ACTION-001", "DEMO-DRIFT-CLAIM-V1"}
    result = client.post("/graphlab/analyze", json={"algorithm": "blast_radius", "site_graph": True,
                                                    "params": {"changed": ["DEMO-DRIFT-SOP-V1"], "direction": "reverse"}})
    assert result.status_code == 200, result.text
    lab = {r["node"] for r in result.json()["result"]["findings"] if r["certainty"] == "definite"}
    assert lab == {p.node_id for p in store.find_impacts(site, ["DEMO-DRIFT-SOP-V1"])}  # same closure as the production store
    assert result.json()["graph_source"] == "site:falkordb"
