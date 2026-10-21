"""Flow relations for supply chains: queues, lead times and stock levels.

- Little's law: L = lambda * W. The average number in a stable system equals the arrival rate times the average time in
  the system. It needs no assumption about the distributions.
- Kingman's formula (G/G/1, heavy-traffic approximation): mean wait in queue Wq ~ (rho / (1 - rho)) * (ca^2 + cs^2) / 2 * tau,
  where rho = lambda * tau is utilization, tau the mean service time, and ca, cs the coefficients of variation of the
  inter-arrival and service times. With ca = cs = 1 it reduces to the exact M/M/1 result Wq = rho * tau / (1 - rho).
- Economic order quantity: Q* = sqrt(2 D S / H), with D annual demand, S the fixed cost per order and H the holding cost per
  unit per year. It minimises D S / Q + H Q / 2.
- Safety stock for normally distributed demand over the lead time: SS = z sigma_w sqrt(L), with z = Phi^-1(service level)
  and sigma_w the standard deviation of weekly demand. Reorder point = mean weekly demand * L + SS.

Assumptions: Kingman's result is an approximation that is accurate at high utilization and loose at low utilization; the
stock formulas assume independent weekly demand and a fixed lead time.
"""
from __future__ import annotations

import math
from statistics import NormalDist


class UnstableQueue(ValueError):
    """Utilization at or above 1: the queue grows without bound, so no steady-state wait exists."""


def utilization(arrival_rate: float, mean_service_time: float) -> float:
    rho = arrival_rate * mean_service_time
    if rho >= 1:
        raise UnstableQueue(f"utilization is {rho:.3f}; at or above 1 the queue grows without bound")
    return rho


def kingman_wait_in_queue(arrival_rate: float, mean_service_time: float, ca: float, cs: float) -> float:
    """Approximate mean time spent waiting before service, in the same time unit as the service time."""
    if ca < 0 or cs < 0:
        raise ValueError("coefficients of variation cannot be negative")
    rho = utilization(arrival_rate, mean_service_time)
    return rho / (1 - rho) * (ca * ca + cs * cs) / 2 * mean_service_time


def littles_law_number_in_system(arrival_rate: float, time_in_system: float) -> float:
    """L = lambda * W: the average number of items in the system."""
    return arrival_rate * time_in_system


def economic_order_quantity(annual_demand: float, order_cost: float, holding_cost_per_unit_year: float) -> float:
    return math.sqrt(2 * annual_demand * order_cost / holding_cost_per_unit_year)


def safety_stock(service_level: float, weekly_demand_sd: float, lead_time_weeks: float) -> float:
    if not 0 < service_level < 1:
        raise ValueError("service level must be between 0 and 1, exclusive")
    z = NormalDist().inv_cdf(service_level)
    return z * weekly_demand_sd * math.sqrt(lead_time_weeks)


def reorder_point(weekly_mean_demand: float, lead_time_weeks: float, stock_buffer: float) -> float:
    return weekly_mean_demand * lead_time_weeks + stock_buffer
