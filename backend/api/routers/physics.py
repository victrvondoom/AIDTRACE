"""Supply-chain physics and mathematics as API endpoints (AIDtrace).

Each route is a deterministic formula from `domains/physics`. Nothing is stored and no model is called. Every response names
the formula it used and the assumptions the number depends on, so a planner can see what it rests on.

Routes (all under /physics, any signed-in user):
  POST /cold-chain/exposure     Arrhenius shelf-life use and mean kinetic temperature for a temperature history
  POST /thermal/time-to-limit   lumped-capacitance warm-up or cool-down of a payload, and when it crosses a limit
  POST /flow/queue              Kingman queue wait and Little's law for a handling or transport stage
  POST /inventory/policy        economic order quantity, safety stock and reorder point
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from api.dependencies import CurrentUserDep
from domains.physics import cold_chain, flow, thermal

router = APIRouter()
KJ_TO_J = 1000.0
HOURS_IN_YEAR = 8784.0


def _refuse(error: ValueError) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error))


class SegmentIn(BaseModel):
    temp_c: float = Field(ge=-90, le=150, description="Temperature held for this stretch, Celsius")
    hours: float = Field(gt=0, le=HOURS_IN_YEAR, description="How long it was held, hours")


class ExposureBody(BaseModel):
    segments: list[SegmentIn] = Field(min_length=1, max_length=10_000)
    reference_temp_c: float = Field(default=5.0, ge=-90, le=40, description="Storage temperature the shelf life is labelled at")
    shelf_life_at_reference_h: float = Field(gt=0, le=HOURS_IN_YEAR * 10, description="Labelled shelf life at the reference, hours")
    activation_energy_kj_mol: float = Field(default=83.144, gt=0, le=300, description="Ea of the degradation, kJ/mol")


@router.post("/cold-chain/exposure", summary="Shelf life used up by a temperature history, and its mean kinetic temperature")
def cold_chain_exposure(body: ExposureBody, _user: CurrentUserDep) -> dict:
    segments = [cold_chain.Segment(s.temp_c, s.hours) for s in body.segments]
    try:
        result = cold_chain.shelf_life_consumed(
            segments, body.reference_temp_c, body.shelf_life_at_reference_h, body.activation_energy_kj_mol * KJ_TO_J)
    except ValueError as error:
        raise _refuse(error)
    return {
        "total_hours": result.total_hours,
        "equivalent_hours_at_reference": result.equivalent_hours_at_reference,
        "consumed_fraction": result.consumed_fraction,
        "remaining_shelf_life_hours": result.remaining_hours,
        "expired": result.expired,
        "mean_kinetic_temp_c": result.mean_kinetic_temp_c,
        "formula": "equivalent hours = sum(h_i * exp(-Ea/R * (1/T_i - 1/T_ref))); "
                   "MKT = (Ea/R) / -ln(sum(h_i * exp(-Ea/(R*T_i))) / sum(h_i))",
        "assumptions": [
            "One activation energy across the whole range (no phase change or change of mechanism).",
            "Each segment is at a uniform temperature.",
            "The reference shelf life is the labelled value supplied with the request.",
        ],
    }


class ThermalBody(BaseModel):
    mass_kg: float = Field(gt=0, le=1_000_000)
    specific_heat_j_kg_k: float = Field(gt=0, le=10_000, description="Specific heat of the payload, J/(kg K)")
    conductance_w_k: float = Field(gt=0, le=1_000_000, description="UA: effective heat conductance to ambient, W/K")
    start_c: float = Field(ge=-90, le=150)
    ambient_c: float = Field(ge=-90, le=150)
    limit_c: float = Field(ge=-90, le=150, description="The temperature to check the payload against")


@router.post("/thermal/time-to-limit", summary="How long a payload takes to reach a limit temperature in a given ambient")
def thermal_time_to_limit(body: ThermalBody, _user: CurrentUserDep) -> dict:
    try:
        tau = thermal.time_constant_s(body.mass_kg, body.specific_heat_j_kg_k, body.conductance_w_k)
        t_limit = thermal.time_to_reach_s(body.start_c, body.ambient_c, body.limit_c, tau)
    except ValueError as error:
        raise _refuse(error)
    return {
        "time_constant_min": tau / 60.0,
        "reaches_limit": t_limit is not None,
        "time_to_limit_min": None if t_limit is None else t_limit / 60.0,
        "formula": "T(t) = T_env + (T0 - T_env) * exp(-t/tau), tau = m*c/UA; t_limit = -tau * ln((T_lim - T_env)/(T0 - T_env))",
        "assumptions": [
            "The payload is at a uniform temperature (small Biot number).",
            "Constant ambient temperature and conductance; no internal heat source.",
        ],
    }


class QueueBody(BaseModel):
    arrival_rate_per_h: float = Field(gt=0, le=1_000_000, description="Items arriving per hour")
    mean_service_h: float = Field(gt=0, le=10_000, description="Mean time to handle one item, hours")
    ca: float = Field(default=1.0, ge=0, le=10, description="Coefficient of variation of inter-arrival times (1 = Poisson)")
    cs: float = Field(default=1.0, ge=0, le=10, description="Coefficient of variation of service times")


@router.post("/flow/queue", summary="Expected queueing delay and queue size at a stage with variable arrivals and service")
def flow_queue(body: QueueBody, _user: CurrentUserDep) -> dict:
    try:
        rho = flow.utilization(body.arrival_rate_per_h, body.mean_service_h)
        wait = flow.kingman_wait_in_queue(body.arrival_rate_per_h, body.mean_service_h, body.ca, body.cs)
    except ValueError as error:
        raise _refuse(error)
    time_in_system = wait + body.mean_service_h
    return {
        "utilization": rho,
        "wait_in_queue_h": wait,
        "time_in_system_h": time_in_system,
        "items_waiting": flow.littles_law_number_in_system(body.arrival_rate_per_h, wait),
        "items_in_system": flow.littles_law_number_in_system(body.arrival_rate_per_h, time_in_system),
        "formula": "Wq ~ rho/(1-rho) * (ca^2 + cs^2)/2 * tau (Kingman); L = lambda * W (Little)",
        "assumptions": [
            "Approximation: accurate at high utilization, loose at low utilization.",
            "Single server stage; steady state.",
        ],
    }


class InventoryBody(BaseModel):
    annual_demand: float = Field(gt=0, le=1e9, description="Units per year")
    order_cost: float = Field(gt=0, le=1e9, description="Fixed cost of placing one order")
    holding_cost_per_unit_year: float = Field(gt=0, le=1e9)
    weekly_demand_sd: float = Field(ge=0, le=1e9, description="Standard deviation of weekly demand, units")
    lead_time_weeks: float = Field(gt=0, le=520)
    service_level: float = Field(gt=0.5, lt=0.999, description="Probability of not running out in one replenishment cycle")


@router.post("/inventory/policy", summary="Order quantity, safety stock and reorder point for one item")
def inventory_policy(body: InventoryBody, _user: CurrentUserDep) -> dict:
    try:
        eoq = flow.economic_order_quantity(body.annual_demand, body.order_cost, body.holding_cost_per_unit_year)
        buffer = flow.safety_stock(body.service_level, body.weekly_demand_sd, body.lead_time_weeks)
    except ValueError as error:
        raise _refuse(error)
    weekly_mean = body.annual_demand / 52.0
    return {
        "order_quantity_units": eoq,
        "cycle_days": 365.0 * eoq / body.annual_demand,
        "weekly_mean_demand_units": weekly_mean,
        "safety_stock_units": buffer,
        "reorder_point_units": flow.reorder_point(weekly_mean, body.lead_time_weeks, buffer),
        "formula": "Q = sqrt(2*D*S/H); SS = z * sigma_w * sqrt(L), z = Phi^-1(service level); ROP = d_w * L + SS",
        "assumptions": [
            "Independent, normally distributed weekly demand.",
            "Fixed lead time; deterministic order cost and holding cost.",
        ],
    }
