"""Heat transfer for a payload in a container or pallet: how fast it warms or cools, and when it crosses a limit.

Physics. Lumped-capacitance model: a body of mass m and specific heat c exchanges heat with its surroundings at ambient
temperature T_env through an effective conductance UA (W/K). The energy balance gives

    m c dT/dt = -UA (T - T_env)   =>   T(t) = T_env + (T0 - T_env) exp(-t / tau),   tau = m c / UA

The gap to ambient falls by a factor e every tau. The model assumes the body is close to uniform in temperature, which holds
when conduction inside the body is small against the surface resistance (Biot number h L / k well below 0.1). The caller
checks that. For an insulated box, UA = U * A, and the heat flowing in is Q = U A (T_out - T_in).

Assumptions: constant UA and ambient temperature over the interval; no internal heat source (a compressor or a product
giving off heat is not modelled); the same mass and specific heat throughout.
"""
from __future__ import annotations

import math


def _positive(name: str, value: float) -> float:
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def conductance_w_k(u_w_m2_k: float, area_m2: float) -> float:
    """UA for a wall or box: overall heat-transfer coefficient times surface area."""
    return _positive("U", u_w_m2_k) * _positive("area", area_m2)


def time_constant_s(mass_kg: float, specific_heat_j_kg_k: float, ua_w_k: float) -> float:
    """tau = m c / UA, in seconds: the time for the gap to ambient to shrink to 1/e of its start."""
    return _positive("mass", mass_kg) * _positive("specific heat", specific_heat_j_kg_k) / _positive("UA", ua_w_k)


def temperature_at_c(elapsed_s: float, start_c: float, ambient_c: float, tau_s: float) -> float:
    """Body temperature (Celsius) after `elapsed_s` seconds of exposure to a constant ambient."""
    if elapsed_s < 0:
        raise ValueError("elapsed time cannot be negative")
    return ambient_c + (start_c - ambient_c) * math.exp(-elapsed_s / _positive("tau", tau_s))


def time_to_reach_s(start_c: float, ambient_c: float, limit_c: float, tau_s: float) -> float | None:
    """Seconds until the body reaches `limit_c`, or None if it never does.

    The body only approaches ambient, so a limit beyond ambient (or on the far side of the start) is never reached.
    Solving T(t) = limit gives t = -tau * ln( (limit - ambient) / (start - ambient) ).
    """
    _positive("tau", tau_s)
    if start_c == ambient_c:
        return 0.0 if limit_c == start_c else None
    ratio = (limit_c - ambient_c) / (start_c - ambient_c)
    if ratio <= 0 or ratio > 1:
        return None
    return -tau_s * math.log(ratio)


def heat_ingress_w(ua_w_k: float, outside_c: float, inside_c: float) -> float:
    """Steady heat flow into the box in watts: positive when the outside is warmer than the inside."""
    return _positive("UA", ua_w_k) * (outside_c - inside_c)
