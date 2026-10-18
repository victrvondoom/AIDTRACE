"""Minimum-cost cut of constraint chains, adapted from Interdict's exact remediation planner.

Adapted from: YashSoni998265/interdict, backend/src/interdict/engine/planner.py, function `solve`
with helpers `_minimal` and `objective`, at commit 829f1dd63fab80f56c019c4a0a40d761c822ea2a.
Copyright (c) 2026 Yash Soni. MIT License; see THIRD_PARTY_NOTICES.md.

Local changes (also listed in THIRD_PARTY_NOTICES.md):
  * Interdict's objective fields (known_broken, unknown, blocked) are replaced by a caller-supplied cost.
    The objective is (total cost, number of actions, sorted action ids).
  * Strict-mode filtering of unknown impact and the deny-all "hard isolation" plan are removed.
  * Chain and Action are local dataclasses. Interdict's own types are not imported.
  * Input guards: 0 <= k <= MAX_K, at most MAX_ACTIONS candidates, unique ids, non-negative costs.
    Violations raise ValueError instead of running an unbounded search.
The exact search, the bitmask coverage test, the one-action-per-selector rule, the best-partial fallback
and the minimal-alternatives filter are kept from the source.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from itertools import combinations

MAX_K = 3
MAX_ACTIONS = 30
ALTERNATIVES = 3


class PlanStatus(StrEnum):
    PLAN_FOUND = "PLAN_FOUND"
    NO_FEASIBLE_PLAN_WITHIN_K = "NO_FEASIBLE_PLAN_WITHIN_K"


class NoPlanReason(StrEnum):
    NO_ELIGIBLE_ACTION = "NO_ELIGIBLE_ACTION"
    K_EXCEEDED = "K_EXCEEDED"


@dataclass(frozen=True)
class Chain:
    """A constraint that must be cut. A chain is cut when a chosen action removes any of its steps."""

    id: str
    steps: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class Action:
    """A candidate intervention. Choosing it removes every step listed in `removed`."""

    id: str
    selector: tuple[str, str]
    removed: frozenset[tuple[str, str]]
    cost: float


@dataclass(frozen=True)
class Plan:
    action_ids: tuple[str, ...]
    cost: float
    cut: frozenset[str]


@dataclass(frozen=True)
class Solution:
    status: PlanStatus
    plan: Plan | None
    alternatives: tuple[Plan, ...]
    best_partial: Plan | None
    uncovered: tuple[str, ...]
    no_plan_reason: NoPlanReason | None
    feasible: int
    evaluated: int


def objective(chosen: Iterable[Action]) -> tuple[float, int, tuple[str, ...]]:
    items = list(chosen)
    return (sum(a.cost for a in items), len(items), tuple(sorted(a.id for a in items)))


def _check_inputs(actions: Sequence[Action], k: int) -> None:
    if not 0 <= k <= MAX_K:
        raise ValueError(f"k must be between 0 and {MAX_K}")
    if len(actions) > MAX_ACTIONS:
        raise ValueError(f"at most {MAX_ACTIONS} candidate actions are accepted")
    ids = [a.id for a in actions]
    if len(set(ids)) != len(ids):
        raise ValueError("action ids must be unique")
    if any(a.cost < 0 for a in actions):
        raise ValueError("costs must be non-negative")


def _plan(actions: Sequence[Action], combo: tuple[int, ...], hits: list[int], constraint: list[Chain]) -> Plan:
    mask = 0
    for i in combo:
        mask |= hits[i]
    chosen = [actions[i] for i in combo]
    cut = frozenset(c.id for bit, c in enumerate(constraint) if mask >> bit & 1)
    return Plan(tuple(sorted(a.id for a in chosen)), objective(chosen)[0], cut)


def solve(actions: Sequence[Action], chains: Iterable[Chain], *, k: int = MAX_K) -> Solution:
    """Exact search over every plan of at most k actions, with at most one action per selector.

    A plan is feasible when it cuts every chain. When none is feasible, the best partial plan is
    reported together with the chains it leaves open.
    """
    _check_inputs(actions, k)
    constraint = sorted({c.id: c for c in chains}.values(), key=lambda c: c.id)
    step_bits: dict[tuple[str, str], int] = defaultdict(int)
    for bit, chain in enumerate(constraint):
        for pair in chain.steps:
            step_bits[pair] |= 1 << bit
    hits = []
    for action in actions:
        mask = 0
        for pair in action.removed:
            mask |= step_bits.get(pair, 0)
        hits.append(mask)
    every = (1 << len(constraint)) - 1

    feasible: list[tuple[tuple, tuple[int, ...]]] = []
    partial = None
    evaluated = 0
    for size in range(k + 1):
        for combo in combinations(range(len(actions)), size):
            chosen = [actions[i] for i in combo]
            if len({a.selector for a in chosen}) < size:
                continue
            evaluated += 1
            mask = 0
            for i in combo:
                mask |= hits[i]
            cost = objective(chosen)
            if mask == every:
                feasible.append((cost, combo))
            key = (-mask.bit_count(), cost)
            if partial is None or key < partial[0]:
                partial = (key, combo, mask)

    if feasible:
        feasible.sort()
        best = _plan(actions, feasible[0][1], hits, constraint)
        alternatives = tuple(
            _plan(actions, combo, hits, constraint)
            for _, combo in feasible[1:]
            if _minimal(combo, hits, every)
        )[:ALTERNATIVES]
        return Solution(PlanStatus.PLAN_FOUND, best, alternatives, None, (), None, len(feasible), evaluated)

    best_partial = None
    uncovered = tuple(c.id for c in constraint)
    if partial is not None:
        _, combo, mask = partial
        best_partial = _plan(actions, combo, hits, constraint)
        uncovered = tuple(c.id for bit, c in enumerate(constraint) if not mask >> bit & 1)
    removable = frozenset().union(*(a.removed for a in actions))
    if any(not frozenset(c.steps) & removable for c in constraint):
        reason = NoPlanReason.NO_ELIGIBLE_ACTION
    else:
        reason = NoPlanReason.K_EXCEEDED
    return Solution(PlanStatus.NO_FEASIBLE_PLAN_WITHIN_K, None, (), best_partial, uncovered, reason, 0, evaluated)


def _minimal(combo: tuple[int, ...], hits: list[int], every: int) -> bool:
    """True when dropping any one action would leave some chain uncut."""
    for left_out in combo:
        rest = 0
        for i in combo:
            if i != left_out:
                rest |= hits[i]
        if rest == every:
            return False
    return True
