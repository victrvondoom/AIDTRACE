"""Physics and mathematics checks for backend/domains/physics. Each formula is checked against a value that can be derived by
hand, a limiting case, or a known property, not against the code's own output."""
from __future__ import annotations

import math

import pytest

from domains.physics import cold_chain as cc
from domains.physics import flow, thermal
from domains.physics.cold_chain import Segment


# --- cold chain: Arrhenius kinetics, time-temperature integration, mean kinetic temperature ---

def test_arrhenius_factor_is_exactly_one_at_the_reference_and_orders_temperatures() -> None:
    assert cc.arrhenius_factor(5.0, 5.0) == pytest.approx(1.0, abs=1e-12)
    assert cc.arrhenius_factor(25.0, 5.0) > 1.0
    assert cc.arrhenius_factor(-18.0, 5.0) < 1.0


def test_arrhenius_factor_for_a_ten_degree_step_is_in_the_chemical_q10_band() -> None:
    # Q10 is the rate ratio for a 10 K rise. For Ea near 83 kJ/mol it sits around 3, in the 2-4 band typical of
    # chemical degradation. Ea = 0 would give exactly 1, so this also checks the energy term is doing work.
    q10 = cc.arrhenius_factor(15.0, 5.0)
    assert 2.0 < q10 < 4.0
    assert cc.arrhenius_factor(15.0, 5.0, activation_energy_j_mol=0.0) == pytest.approx(1.0)


def test_mkt_of_a_constant_temperature_is_that_temperature() -> None:
    history = [Segment(7.0, 10.0), Segment(7.0, 3.0)]
    assert cc.mean_kinetic_temperature_c(history) == pytest.approx(7.0, abs=1e-9)


def test_mkt_is_above_the_time_weighted_mean_because_warm_excursions_dominate() -> None:
    # 10 h at 2 C and 2 h at 25 C: the arithmetic mean is (20 + 50) / 12 = 5.83 C. The Arrhenius weighting pulls MKT up.
    history = [Segment(2.0, 10.0), Segment(25.0, 2.0)]
    arithmetic_mean = (2.0 * 10.0 + 25.0 * 2.0) / 12.0
    mkt = cc.mean_kinetic_temperature_c(history)
    assert arithmetic_mean < mkt < 25.0


def test_holding_at_the_reference_consumes_exactly_its_own_duration_of_shelf_life() -> None:
    result = cc.shelf_life_consumed([Segment(5.0, 100.0)], reference_c=5.0, shelf_life_at_reference_hours=1000.0)
    assert result.equivalent_hours_at_reference == pytest.approx(100.0)
    assert result.consumed_fraction == pytest.approx(0.1)
    assert result.remaining_hours == pytest.approx(900.0)
    assert result.expired is False


def test_a_warm_excursion_consumes_more_shelf_life_than_its_clock_time() -> None:
    result = cc.shelf_life_consumed([Segment(25.0, 10.0)], reference_c=5.0, shelf_life_at_reference_hours=1000.0)
    assert result.equivalent_hours_at_reference == pytest.approx(10.0 * cc.arrhenius_factor(25.0, 5.0))
    assert result.equivalent_hours_at_reference > 10.0


def test_shelf_life_reports_expiry_when_consumption_reaches_the_limit() -> None:
    result = cc.shelf_life_consumed([Segment(5.0, 10.0)], reference_c=5.0, shelf_life_at_reference_hours=10.0)
    assert result.consumed_fraction == pytest.approx(1.0)
    assert result.expired is True
    assert result.remaining_hours == 0.0


@pytest.mark.parametrize("bad", [[], [Segment(5.0, -1.0)], [Segment(5.0, 0.0)]])
def test_invalid_temperature_histories_are_refused(bad) -> None:
    with pytest.raises(ValueError):
        cc.mean_kinetic_temperature_c(bad)


# --- heat transfer: lumped capacitance ---

def test_time_constant_is_mass_times_specific_heat_over_conductance() -> None:
    assert thermal.time_constant_s(mass_kg=10.0, specific_heat_j_kg_k=4000.0, ua_w_k=20.0) == pytest.approx(2000.0)


def test_after_one_time_constant_the_gap_to_ambient_has_fallen_by_e() -> None:
    tau = 2000.0
    temp = thermal.temperature_at_c(tau, start_c=20.0, ambient_c=30.0, tau_s=tau)
    gap_fraction = (30.0 - temp) / (30.0 - 20.0)
    assert gap_fraction == pytest.approx(math.exp(-1.0))


def test_time_to_a_limit_inverts_the_temperature_curve() -> None:
    tau = 2000.0
    t_limit = thermal.time_to_reach_s(start_c=20.0, ambient_c=30.0, limit_c=25.0, tau_s=tau)
    assert t_limit == pytest.approx(tau * math.log(2.0))
    assert thermal.temperature_at_c(t_limit, 20.0, 30.0, tau) == pytest.approx(25.0, abs=1e-9)


@pytest.mark.parametrize("limit", [35.0, 10.0])
def test_a_limit_the_body_never_reaches_returns_none(limit: float) -> None:
    # Warming towards 30 C, so 35 C is beyond ambient and 10 C is behind the start: neither is ever reached.
    assert thermal.time_to_reach_s(start_c=20.0, ambient_c=30.0, limit_c=limit, tau_s=2000.0) is None


def test_a_body_already_at_ambient_stays_there() -> None:
    assert thermal.time_to_reach_s(30.0, 30.0, 30.0, 2000.0) == 0.0
    assert thermal.time_to_reach_s(30.0, 30.0, 31.0, 2000.0) is None


def test_heat_ingress_is_positive_when_the_outside_is_warmer() -> None:
    ua = thermal.conductance_w_k(u_w_m2_k=0.5, area_m2=12.0)
    assert ua == pytest.approx(6.0)
    assert thermal.heat_ingress_w(ua, outside_c=30.0, inside_c=5.0) == pytest.approx(150.0)
    assert thermal.heat_ingress_w(ua, outside_c=5.0, inside_c=30.0) == pytest.approx(-150.0)


def test_non_physical_transfer_inputs_are_refused() -> None:
    with pytest.raises(ValueError):
        thermal.time_constant_s(mass_kg=0.0, specific_heat_j_kg_k=4000.0, ua_w_k=20.0)
    with pytest.raises(ValueError):
        thermal.temperature_at_c(-1.0, 20.0, 30.0, 2000.0)


# --- flow: queueing and inventory ---

def test_kingman_reduces_to_the_exact_mm1_wait_when_both_cvs_are_one() -> None:
    # M/M/1: Wq = rho * tau / (1 - rho). With lambda = 0.5/h and tau = 1 h, rho = 0.5 and Wq = 1 h.
    assert flow.kingman_wait_in_queue(arrival_rate=0.5, mean_service_time=1.0, ca=1.0, cs=1.0) == pytest.approx(1.0)


def test_more_variability_means_a_longer_queue_at_the_same_utilization() -> None:
    steady = flow.kingman_wait_in_queue(0.8, 1.0, ca=0.5, cs=0.5)
    bursty = flow.kingman_wait_in_queue(0.8, 1.0, ca=1.5, cs=1.5)
    assert bursty > steady > 0.0


def test_a_saturated_queue_is_refused_not_given_a_finite_wait() -> None:
    with pytest.raises(flow.UnstableQueue):
        flow.kingman_wait_in_queue(arrival_rate=1.0, mean_service_time=1.0, ca=1.0, cs=1.0)


def test_littles_law_multiplies_rate_by_time_in_system() -> None:
    assert flow.littles_law_number_in_system(arrival_rate=3.0, time_in_system=4.0) == pytest.approx(12.0)


def test_economic_order_quantity_matches_the_closed_form() -> None:
    # Q = sqrt(2 * 1000 * 50 / 2) = sqrt(50000)
    assert flow.economic_order_quantity(1000.0, 50.0, 2.0) == pytest.approx(math.sqrt(50000.0))


def test_safety_stock_uses_the_normal_quantile_for_the_service_level() -> None:
    z_95 = 1.6448536269514722  # Phi^-1(0.95)
    assert flow.safety_stock(0.95, weekly_demand_sd=10.0, lead_time_weeks=4.0) == pytest.approx(z_95 * 10.0 * 2.0)
    assert flow.reorder_point(20.0, 4.0, 32.0) == pytest.approx(112.0)


@pytest.mark.parametrize("level", [0.0, 1.0, 1.2])
def test_a_service_level_outside_zero_to_one_is_refused(level: float) -> None:
    with pytest.raises(ValueError):
        flow.safety_stock(level, weekly_demand_sd=10.0, lead_time_weeks=4.0)
