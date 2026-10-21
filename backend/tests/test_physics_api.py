"""Physics endpoints: the formulas reachable over HTTP, units explicit, and refusals as 422 rather than a made-up number."""
from __future__ import annotations

import math

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_current_user
from api.routers import physics


def client() -> TestClient:
    app = FastAPI()
    app.include_router(physics.router, prefix="/physics")
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "u1", "role": "engineer", "site_id": "site_p"}
    return TestClient(app)


def test_a_constant_temperature_history_has_that_mkt_and_its_clock_time_as_exposure() -> None:
    body = {"segments": [{"temp_c": 5.0, "hours": 100.0}], "reference_temp_c": 5.0, "shelf_life_at_reference_h": 1000.0}
    out = client().post("/physics/cold-chain/exposure", json=body).json()
    assert out["mean_kinetic_temp_c"] == pytest.approx(5.0, abs=1e-9)
    assert out["equivalent_hours_at_reference"] == pytest.approx(100.0)
    assert out["remaining_shelf_life_hours"] == pytest.approx(900.0)
    assert out["expired"] is False
    assert out["formula"] and out["assumptions"]


def test_an_excursion_costs_more_than_its_clock_time_and_can_expire_the_product() -> None:
    body = {"segments": [{"temp_c": 30.0, "hours": 50.0}], "reference_temp_c": 5.0, "shelf_life_at_reference_h": 100.0}
    out = client().post("/physics/cold-chain/exposure", json=body).json()
    assert out["equivalent_hours_at_reference"] > 50.0
    assert out["expired"] is True


def test_a_warming_payload_reports_when_it_crosses_the_limit() -> None:
    body = {"mass_kg": 10.0, "specific_heat_j_kg_k": 4000.0, "conductance_w_k": 20.0,
            "start_c": 20.0, "ambient_c": 30.0, "limit_c": 25.0}
    out = client().post("/physics/thermal/time-to-limit", json=body).json()
    assert out["time_constant_min"] == pytest.approx(2000.0 / 60.0)
    assert out["reaches_limit"] is True
    assert out["time_to_limit_min"] == pytest.approx(2000.0 * math.log(2.0) / 60.0)


def test_a_limit_beyond_ambient_is_reported_as_never_reached() -> None:
    body = {"mass_kg": 10.0, "specific_heat_j_kg_k": 4000.0, "conductance_w_k": 20.0,
            "start_c": 20.0, "ambient_c": 30.0, "limit_c": 35.0}
    out = client().post("/physics/thermal/time-to-limit", json=body).json()
    assert out["reaches_limit"] is False
    assert out["time_to_limit_min"] is None


def test_queue_wait_matches_mm1_at_half_utilization_and_obeys_littles_law() -> None:
    out = client().post("/physics/flow/queue", json={"arrival_rate_per_h": 0.5, "mean_service_h": 1.0}).json()
    assert out["utilization"] == pytest.approx(0.5)
    assert out["wait_in_queue_h"] == pytest.approx(1.0)
    assert out["time_in_system_h"] == pytest.approx(2.0)
    assert out["items_in_system"] == pytest.approx(0.5 * 2.0)


def test_a_saturated_queue_is_refused_with_422_not_given_a_finite_wait() -> None:
    response = client().post("/physics/flow/queue", json={"arrival_rate_per_h": 1.0, "mean_service_h": 1.0})
    assert response.status_code == 422
    assert "grows without bound" in response.text


def test_inventory_policy_returns_eoq_safety_stock_and_reorder_point() -> None:
    body = {"annual_demand": 52000.0, "order_cost": 50.0, "holding_cost_per_unit_year": 2.0,
            "weekly_demand_sd": 10.0, "lead_time_weeks": 4.0, "service_level": 0.95}
    out = client().post("/physics/inventory/policy", json=body).json()
    assert out["order_quantity_units"] == pytest.approx(math.sqrt(2 * 52000 * 50 / 2))
    assert out["weekly_mean_demand_units"] == pytest.approx(1000.0)
    assert out["reorder_point_units"] == pytest.approx(4000.0 + 1.6448536269514722 * 10.0 * 2.0)
    assert out["cycle_days"] == pytest.approx(365.0 * out["order_quantity_units"] / 52000.0)


def test_out_of_range_inputs_are_rejected_by_validation() -> None:
    too_hot = {"segments": [{"temp_c": 500.0, "hours": 1.0}], "shelf_life_at_reference_h": 10.0}
    assert client().post("/physics/cold-chain/exposure", json=too_hot).status_code == 422
    certainty = {"annual_demand": 1000.0, "order_cost": 50.0, "holding_cost_per_unit_year": 2.0,
                 "weekly_demand_sd": 1.0, "lead_time_weeks": 2.0, "service_level": 0.9999}
    assert client().post("/physics/inventory/policy", json=certainty).status_code == 422
