"""Which conflicting remedies to drop: a minimum-value cut of double-claim conflicts.

When two remedies both claim recovery for the same event, pursuing both recovers that event twice.
Each conflict becomes a chain whose steps are (remedy, event) pairs. Dropping a remedy removes all of its
steps, so the cheapest set of drops that cuts every conflict is a minimum-cost vertex cover. The solver is
the adapted Interdict search in adapters/interdict_cut.py.

Cost of dropping a remedy is the recovery value that only that remedy would still obtain: value covered by
it and by no other conflicting remedy. Probability of success is not weighed, and no legal entitlement is
assessed. These are policy inputs that the user can change.
"""

from __future__ import annotations

from typing import Any

from api.services.consumer.interdict_cut import Action, Chain, PlanStatus, solve

RULE = (
    "Drop the conflicting remedies that leave no double claim at the least recovery value forgone. "
    "A remedy's value is the recovery only it would still obtain. Success probability is not weighed."
)


def _net(evidence_id: str, facts: dict[str, Any]) -> float:
    gross = facts["evidence"][evidence_id]["amount"]
    refunded = sum(
        facts["evidence"][r]["amount"]
        for r in facts["refunds_of"].get(evidence_id, [])
        if facts["evidence"][r]["status"] == "PRESENT"
    )
    return gross - refunded


def unique_recovery_values(facts: dict[str, Any], event_evidence: dict[str, list[str]],
                           members: set[str]) -> dict[str, float]:
    """Value each remedy alone would still recover, relative to the other conflicting remedies.

    `facts` has the shape produced by verifier.load_facts. `event_evidence` maps an Event to the Evidence
    it is EVIDENCED_BY. A remedy covers the evidence its linked claims INCLUDE and the evidence of the
    events it CLAIMS_RECOVERY_FOR. Evidence covered by another member is not counted for this member.
    """
    covered: dict[str, set[str]] = {}
    for strategy in members:
        items: set[str] = set()
        for cond in facts["strategy_conditions"].get(strategy, []):
            claim = facts["cond_claim"].get(cond)
            if claim:
                items |= set(facts["claim_evidence"].get(claim, []))
        remedy = facts["strategies"][strategy]["remedy_id"]
        for recovery in facts["recovery_claims"]:
            if recovery["remedy"] == remedy:
                items |= set(event_evidence.get(recovery["event"], []))
        covered[strategy] = items
    values: dict[str, float] = {}
    for strategy in members:
        others: set[str] = set()
        for other in members:
            if other != strategy:
                others |= covered[other]
        values[strategy] = float(sum(_net(item, facts) for item in covered[strategy] - others))
    return values


def recommend_drops(conflicts: list[dict[str, Any]], costs: dict[str, float], *, k: int = 3) -> dict[str, Any]:
    """conflicts: [{"event": str, "strategies": [str, ...]}]. costs: {strategy: value forgone if dropped}."""
    chains: list[Chain] = []
    members: dict[str, set[tuple[str, str]]] = {}
    for conflict in conflicts:
        if not isinstance(conflict, dict) or not isinstance(conflict.get("event"), str):
            raise ValueError("each conflict needs an 'event' string")
        strategies_raw = conflict.get("strategies")
        if not isinstance(strategies_raw, list) or not all(isinstance(s, str) for s in strategies_raw):
            raise ValueError("each conflict needs a 'strategies' list of strings")
        event = conflict["event"]
        strategies = sorted(set(strategies_raw))
        if len(strategies) < 2:
            continue
        chains.append(Chain(id=f"{event}:{'|'.join(strategies)}", steps=tuple((s, event) for s in strategies)))
        for s in strategies:
            members.setdefault(s, set()).add((s, event))
    if not chains:
        return {"status": "NO_CONFLICT", "drop": [], "forgone_value": 0.0, "alternatives": [], "rule": RULE}
    missing = sorted(s for s in members if s not in costs)
    if missing:
        raise ValueError(f"no value supplied for {missing}")
    for s in members:
        value = costs[s]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"value for {s} must be a number")
    actions = [
        Action(id=f"DROP:{s}", selector=(s, "drop"), removed=frozenset(members[s]), cost=float(costs[s]))
        for s in sorted(members)
    ]
    solution = solve(actions, chains, k=k)
    if solution.status is not PlanStatus.PLAN_FOUND:
        reason = solution.no_plan_reason.value if solution.no_plan_reason else None
        return {"status": solution.status.value, "reason": reason, "drop": [], "forgone_value": None,
                "alternatives": [], "rule": RULE}

    def names(action_ids: tuple[str, ...]) -> list[str]:
        return [a.removeprefix("DROP:") for a in action_ids]

    return {
        "status": "RECOMMENDED",
        "drop": names(solution.plan.action_ids),
        "forgone_value": solution.plan.cost,
        "alternatives": [{"drop": names(p.action_ids), "forgone_value": p.cost} for p in solution.alternatives],
        "rule": RULE,
    }
