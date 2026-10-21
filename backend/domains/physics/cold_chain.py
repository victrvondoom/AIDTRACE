"""Cold-chain kinetics: how a temperature history turns into lost shelf life.

Physics. A degradation reaction (loss of potency, growth of a spoilage organism, a protein unfolding) runs at a rate
k(T) = A * exp(-Ea / (R * T)), with T absolute temperature in kelvin, Ea the activation energy in J/mol and
R = 8.314462618 J/(mol K). Degradation adds up over time, so a history that holds each temperature T_i for h_i hours
consumes the same shelf life as this many hours at the reference temperature:

    equivalent hours at reference = sum_i h_i * exp(-Ea/R * (1/T_i - 1/T_ref))

The shelf life left is the labelled shelf life at the reference minus that sum. This is the time-temperature integration
used in stability and cold-chain assessment.

Mean kinetic temperature (MKT, the USP <1079> definition) is the one steady temperature that would cause the same total
degradation over the same period:

    T_MKT = (Ea/R) / -ln( sum_i h_i * exp(-Ea/(R*T_i)) / sum_i h_i )

Because the Arrhenius weighting favours warm excursions, T_MKT is never below the time-weighted arithmetic mean.

Assumptions: one activation energy holds across the whole range (no phase change, no change of mechanism); each segment is
at a uniform temperature; the reference shelf life is supplied by the caller and is only as good as that value.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

R_J_PER_MOL_K = 8.314462618
ZERO_C_IN_K = 273.15
# About 83 kJ/mol, the activation energy conventionally used for MKT (Ea / R = 10 000 K).
DEFAULT_ACTIVATION_ENERGY_J_MOL = 83_144.0


@dataclass(frozen=True)
class Segment:
    """One stretch of a temperature history: held at `temp_c` for `hours`."""

    temp_c: float
    hours: float


@dataclass(frozen=True)
class ShelfLife:
    total_hours: float
    equivalent_hours_at_reference: float
    consumed_fraction: float
    remaining_hours: float
    expired: bool
    mean_kinetic_temp_c: float


def to_kelvin(temp_c: float) -> float:
    return temp_c + ZERO_C_IN_K


def _check_segments(segments: Sequence[Segment]) -> float:
    if not segments:
        raise ValueError("at least one temperature segment is needed")
    if any(segment.hours < 0 for segment in segments):
        raise ValueError("segment durations cannot be negative")
    total = sum(segment.hours for segment in segments)
    if total <= 0:
        raise ValueError("the segments must add up to a positive duration")
    return total


def arrhenius_factor(temp_c: float, reference_c: float, activation_energy_j_mol: float = DEFAULT_ACTIVATION_ENERGY_J_MOL) -> float:
    """How many times faster the reaction runs at `temp_c` than at `reference_c` (exactly 1.0 at the reference)."""
    ea_over_r = activation_energy_j_mol / R_J_PER_MOL_K
    return math.exp(-ea_over_r * (1 / to_kelvin(temp_c) - 1 / to_kelvin(reference_c)))


def mean_kinetic_temperature_c(segments: Sequence[Segment], activation_energy_j_mol: float = DEFAULT_ACTIVATION_ENERGY_J_MOL) -> float:
    """The single constant temperature (Celsius) with the same total degradation as the whole history."""
    total = _check_segments(segments)
    ea_over_r = activation_energy_j_mol / R_J_PER_MOL_K
    weighted = sum(s.hours * math.exp(-ea_over_r / to_kelvin(s.temp_c)) for s in segments) / total
    return ea_over_r / -math.log(weighted) - ZERO_C_IN_K


def shelf_life_consumed(
    segments: Sequence[Segment],
    reference_c: float,
    shelf_life_at_reference_hours: float,
    activation_energy_j_mol: float = DEFAULT_ACTIVATION_ENERGY_J_MOL,
) -> ShelfLife:
    """How much of the labelled shelf life a temperature history has used up, and what is left."""
    total = _check_segments(segments)
    if shelf_life_at_reference_hours <= 0:
        raise ValueError("the shelf life at the reference temperature must be positive")
    equivalent = sum(s.hours * arrhenius_factor(s.temp_c, reference_c, activation_energy_j_mol) for s in segments)
    remaining = shelf_life_at_reference_hours - equivalent
    return ShelfLife(
        total_hours=total,
        equivalent_hours_at_reference=equivalent,
        consumed_fraction=equivalent / shelf_life_at_reference_hours,
        remaining_hours=max(remaining, 0.0),
        expired=remaining <= 0,
        mean_kinetic_temp_c=mean_kinetic_temperature_c(segments, activation_energy_j_mol),
    )
