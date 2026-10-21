"""GreenChain inside Kairos: real ML scoring through the Kairos API, graph persistence and evidence impact."""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from domains.greenchain import kairos_adapter as adapter
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_current_user, get_settings
from api.routers.graphlab import router as graphlab_router
from api.routers.greenchain import router

requires_falkordb = pytest.mark.skipif(not os.getenv("FALKORDB_TEST_URL"), reason="set FALKORDB_TEST_URL")


def client(role="engineer", site="site_gc_test") -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/greenchain")
    app.include_router(graphlab_router, prefix="/graphlab")
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "u-gc", "role": role, "site_id": site}
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace(FALKORDB_URL=os.environ.get("FALKORDB_TEST_URL", "redis://127.0.0.1:1"))
    return TestClient(app)


def test_health_reports_real_models_and_unconnected_live_discovery() -> None:
    body = client().get("/greenchain/health").json()
    assert body["ml_models"] is True and body["reference_data"] is True
    assert body["live_discovery"] in ("NOT_CONNECTED", "CONFIGURED")


def test_demo_is_labelled_illustrative_and_ranked_by_the_real_scorer() -> None:
    demo = client().get("/greenchain/demo").json()
    assert demo["mode"] == "ILLUSTRATIVE_DEMO" and "not real suppliers" in demo["notice"]
    ranks = [r["rank"] for r in demo["results"]]
    assert ranks == sorted(ranks) and len(ranks) == 5
    totals = [r["scores"]["total_tco2e"] for r in demo["results"]]
    assert all(r["emission_factor"]["q10_tco2e"] <= r["emission_factor"]["q50_tco2e"] <= r["emission_factor"]["q90_tco2e"] for r in demo["results"])
    assert min(totals) > 0
    assert demo["graph"]["nodes"] and demo["graph"]["edges"]


def test_transport_rescore_changes_totals_and_ranking_inputs() -> None:
    c = client()
    sea = c.get("/greenchain/demo", params={"transport_mode": "sea"}).json()["results"]
    air = c.post("/greenchain/rescore-transport", json={"manufacturers": sea, "mode": "air"}).json()["results"]
    by_name = {r["name"]: r["scores"]["total_tco2e"] for r in sea}
    assert all(r["scores"]["total_tco2e"] > by_name[r["name"]] for r in air)  # air is far more carbon-intensive than sea
    assert [r["rank"] for r in air] == list(range(1, len(air) + 1))


def test_weights_change_the_ranking_deterministically() -> None:
    a = adapter.score_candidates(adapter.demo_candidates())
    b = adapter.score_candidates(adapter.demo_candidates())
    assert [r["name"] for r in a] == [r["name"] for r in b]
    shifted = adapter.score_candidates(adapter.demo_candidates(), weights={"manufacturing": 0.05, "transport": 0.05, "grid_carbon": 0.05, "certifications": 0.05, "climate_risk": 0.8})
    assert {r["name"] for r in shifted} == {r["name"] for r in a}


def test_whatif_removal_reranks_and_rejects_unknown_suppliers() -> None:
    c = client()
    top = c.get("/greenchain/demo").json()["results"][0]["name"]
    out = c.post("/greenchain/whatif/remove-supplier", json={"remove": top}).json()
    assert out["top_before"] == top and out["top_after"] != top and out["recommendation_changes"] is True
    assert c.post("/greenchain/whatif/remove-supplier", json={"remove": "Nobody Ltd"}).status_code == 422


def test_unverified_certification_makes_impact_only_possible() -> None:
    c = client()
    demo = c.get("/greenchain/demo").json()
    cert = next(n["id"] for n in demo["graph"]["nodes"] if n["type"] == "Certification")
    res = c.post("/graphlab/analyze", json={"algorithm": "blast_radius", "graph": demo["graph"], "params": {"changed": [cert]}}).json()
    decision = next(n["id"] for n in demo["graph"]["nodes"] if n["type"] == "Decision")
    marks = res["result"]["node_marks"]
    assert marks[decision] in ("impacted", "possible")  # a claimed certification only ever advises review, never proves invalidation


def test_dataset_change_reaches_every_estimate_and_the_decision() -> None:
    c = client()
    demo = c.get("/greenchain/demo").json()
    res = c.post("/graphlab/analyze", json={"algorithm": "blast_radius", "graph": demo["graph"],
                                            "params": {"changed": ["dataset:USEEIO"]}}).json()
    impacted = {r["node"] for r in res["result"]["findings"] if r["certainty"] == "definite"}
    assert {f"estimate:Illustrative_Packaging_{x}" for x in "ABCDE"} <= impacted
    assert next(n["id"] for n in demo["graph"]["nodes"] if n["type"] == "Decision") in impacted


def test_live_search_and_provider_routes_are_closed_to_the_demo_role() -> None:
    d = client(role="demo")
    assert d.post("/greenchain/search", json={"product": "cardboard", "quantity": 100, "destination": "US", "countries": ["VN"]}).status_code == 403
    assert client(role="field_worker").get("/greenchain/demo").status_code == 403


@requires_falkordb
def test_graph_persists_per_tenant_in_falkordb() -> None:
    from api.services.consumer.store import GraphStore
    url = os.environ["FALKORDB_TEST_URL"]
    a, b = client(site="site_gc_a"), client(site="site_gc_b")
    try:
        results = a.get("/greenchain/demo").json()["results"]
        counts = a.post("/greenchain/graph/persist", json={"results": results}).json()
        assert counts["nodes"] > 10
        stored = a.get("/greenchain/graph/stored").json()["graph"]
        assert any(n["type"] == "Decision" for n in stored["nodes"]) and stored["edges"]
        assert b.get("/greenchain/graph/stored").json()["graph"]["nodes"] == []  # another site sees nothing
    finally:
        for s in ("site_gc_a", "site_gc_b"):
            GraphStore(url, f"greenchain_{s}").reset_synthetic_graph()
