"""The hub overview labels every capability from a live probe. These tests pin the honesty rules:
a dead dependency is UNAVAILABLE, a connected-but-incomplete one is LIMITED with its limits listed, and nothing is
OPERATIONAL on the strength of a static claim."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_current_user, get_falkor_drift_store
from api.routers import hub, resolveai_platform


class _Store:
    def __init__(self, reachable: bool) -> None:
        self.reachable = reachable

    def inspect_site(self, site_id):
        if not self.reachable:
            raise ConnectionError("down")
        return {"reachable": True, "site_graph_exists": bool(site_id)}


def client(*, falkor: bool, runtime, role="engineer") -> TestClient:
    app = FastAPI()
    app.include_router(hub.router, prefix="/hub")
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "u1", "role": role, "site_id": "site_hub_a"}
    app.dependency_overrides[get_falkor_drift_store] = lambda: _Store(falkor)

    async def fake_runtime():
        return runtime

    resolveai_platform._runtime = fake_runtime  # restored by the fixture below
    return TestClient(app)


@pytest.fixture(autouse=True)
def restore_runtime():
    original = resolveai_platform._runtime
    yield
    resolveai_platform._runtime = original


WORKER_NO_MODEL = {"model_provider": "disabled", "model_provider_name": "gemini", "vector_backend": "jsonl", "indexed_points": 12113,
                   "collections": 8, "graph_backend": "jsonl", "case_store": "local"}


def by_id(body: dict) -> dict:
    return {c["id"]: c for c in body["capabilities"]}


def test_a_connected_worker_with_no_model_is_limited_not_operational() -> None:
    caps = by_id(client(falkor=True, runtime=WORKER_NO_MODEL).get("/hub/capabilities").json())
    assert caps["resolveai"]["state"] == "LIMITED"
    assert any("No model provider" in limit for limit in caps["resolveai"]["limits"])
    assert caps["resolveai"]["metrics"]["indexed_points"] == 12113


def test_a_worker_that_does_not_answer_is_unavailable() -> None:
    caps = by_id(client(falkor=True, runtime=None).get("/hub/capabilities").json())
    assert caps["resolveai"]["state"] == "UNAVAILABLE"
    assert caps["reports"]["state"] == "LIMITED"


def test_graph_dependent_capabilities_go_unavailable_when_falkordb_is_down() -> None:
    caps = by_id(client(falkor=False, runtime=WORKER_NO_MODEL).get("/hub/capabilities").json())
    for cid in ("memory", "evidence-drift", "consumer", "fraud"):
        assert caps[cid]["state"] == "UNAVAILABLE", cid
    assert caps["graph"]["state"] == "OPERATIONAL"  # the in-process engines need no database
    assert caps["simulations"]["state"] == "LIMITED"


def test_model_only_cybersecurity_and_synthetic_fraud_are_never_labelled_operational() -> None:
    caps = by_id(client(falkor=True, runtime=WORKER_NO_MODEL).get("/hub/capabilities").json())
    assert caps["cybersecurity"]["state"] == "LIMITED" and "Model-only" in caps["cybersecurity"]["limits"][0]
    assert caps["fraud"]["state"] == "LIMITED" and "synthetic" in caps["fraud"]["limits"][0]


def test_edges_only_reference_known_capabilities_and_roles_are_enforced() -> None:
    body = client(falkor=True, runtime=WORKER_NO_MODEL).get("/hub/capabilities").json()
    ids = set(by_id(body))
    assert {"overview", "resolveai", "greenchain", "consumer", "fraud", "cybersecurity", "agents", "memory", "evidence-drift", "graph", "simulations", "reports"} <= ids
    assert all(e["source"] in ids and e["target"] in ids for e in body["edges"])
    assert client(falkor=True, runtime=WORKER_NO_MODEL, role="field_worker").get("/hub/capabilities").status_code == 403
