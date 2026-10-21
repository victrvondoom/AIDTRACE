"""Coordination routes against an explicit test-only Falkor protocol adapter."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_current_user, get_falkor_drift_store
from api.routers import coordination
from api.services.coordination.graph_store import InMemoryGraphStore


class FalkorProtocolTestAdapter:
    """In-memory test double with the site's FalkorDriftStore method signatures."""

    def __init__(self) -> None:
        self.graph = InMemoryGraphStore()

    def inspect_site(self, site_id):
        return {"reachable": True, "site_graph_exists": True}

    def upsert_node(self, site_id, label, node_id, properties):
        self.graph.upsert_node(label, node_id, {**properties, "site_id": site_id})

    def create_node_once(self, site_id, label, node_id, properties):
        return self.graph.create_node_once(label, node_id, {**properties, "site_id": site_id})

    def read_node(self, site_id, node_id):
        node = self.graph.read_node(node_id)
        if node is None:
            return None
        return {"labels": [node["label"]], "properties": node["properties"]}

    def list_nodes(self, site_id, label, *, limit=200):
        return self.graph.list_nodes(label, limit=limit)

    def update_node_properties(self, site_id, label, node_id, properties):
        self.graph.update_node_properties(label, node_id, properties)

    def compare_and_set_node_properties(self, site_id, label, node_id, *, expected, properties):
        return self.graph.compare_and_set_node_properties(label, node_id, expected=expected, properties=properties)

    def link(self, site_id, source_label, source_id, relationship, target_label, target_id, properties=None):
        self.graph.link(source_id, relationship, target_id, properties)


@pytest.fixture
def test_client() -> tuple[TestClient, FalkorProtocolTestAdapter]:
    adapter = FalkorProtocolTestAdapter()
    app = FastAPI()
    app.include_router(coordination.router, prefix="/coordination")
    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "test_engineer", "email": "engineer@aidtrace.org",
        "role": "engineer", "site_id": "test_site",
    }
    app.dependency_overrides[get_falkor_drift_store] = lambda: adapter
    return TestClient(app), adapter


def test_get_capabilities(test_client: tuple[TestClient, FalkorProtocolTestAdapter]) -> None:
    client, _ = test_client
    response = client.get("/coordination/capabilities")
    assert response.status_code == 200
    data = response.json()
    capabilities = {item["capability_id"]: item for item in data["capabilities"]}
    assert data["total"] >= 13
    assert capabilities["cyber.reachability"]["availability"] == "PLANNED"
    assert capabilities["business.engineering_memory"]["availability"] == "PARTIAL"
    assert "required_services" in capabilities["cyber.reachability"]
    assert "test_evidence" in capabilities["cyber.reachability"]


def test_create_and_read_run_uses_shared_graph_and_reports_blocked_domain(
    test_client: tuple[TestClient, FalkorProtocolTestAdapter],
) -> None:
    client, _ = test_client
    response = client.post("/coordination/runs", json={
        "goal": "Investigate this reported issue",
        "domain": "cybersecurity",
        "context_ids": ["CVE-EXAMPLE-001"],
        "execute_now": True,
    })
    assert response.status_code == 200, response.text
    result = response.json()
    run_id = result["run"]["run_id"]
    assert result["execution"]["status"] == "BLOCKED"
    assert result["execution"]["domain_analysis_performed"] is False
    assert len(result["execution"]["tasks"]) == 3

    detail = client.get(f"/coordination/runs/{run_id}")
    assert detail.status_code == 200
    data = detail.json()
    assert data["run"]["status"] == "BLOCKED"
    assert len(data["tasks"]) == 3
    assert len(data["events"]) >= 8
    assert data["checkpoint"]["hash"]


def test_missing_falkordb_returns_service_unavailable_without_memory_fallback() -> None:
    app = FastAPI()
    app.include_router(coordination.router, prefix="/coordination")
    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "test_engineer", "email": "engineer@aidtrace.org",
        "role": "engineer", "site_id": "test_site",
    }
    app.dependency_overrides[get_falkor_drift_store] = lambda: None
    response = TestClient(app).post("/coordination/runs", json={"goal": "check the graph"})
    assert response.status_code == 503
    assert "no in-memory fallback" in response.json()["detail"]


def test_task_cancellation_is_persisted_within_its_run(
    test_client: tuple[TestClient, FalkorProtocolTestAdapter],
) -> None:
    client, _ = test_client
    created = client.post("/coordination/runs", json={
        "goal": "Check a graph evidence item", "domain": "general", "execute_now": False,
    })
    assert created.status_code == 200
    run_id = created.json()["run"]["run_id"]
    evidence_task = next(task for task in created.json()["tasks"]
                         if task["capability_id"] == "core.graph_evidence_lookup")
    response = client.post(f"/coordination/runs/{run_id}/tasks/{evidence_task['task_id']}/cancel", json={})
    assert response.status_code == 200
    details = client.get(f"/coordination/runs/{run_id}").json()
    cancelled = next(task for task in details["tasks"] if task["task_id"] == evidence_task["task_id"])
    assert cancelled["status"] == "CANCELLED"
    assert any(event["event_type"] == "TASK_CANCELLED" for event in details["events"])


def test_unlearning_route_fails_closed_and_changes_no_data(
    test_client: tuple[TestClient, FalkorProtocolTestAdapter],
) -> None:
    client, adapter = test_client
    adapter.graph.upsert_node("Runbook", "runbook_old", {"title": "Keep this record"})
    before = adapter.graph.read_node("runbook_old")
    response = client.post("/coordination/unlearning/delete", json={
        "entity_id": "runbook_old", "entity_type": "Runbook", "reason": "obsolete",
    })
    assert response.status_code == 501
    assert response.json()["detail"]["data_changed"] is False
    assert adapter.graph.read_node("runbook_old") == before
