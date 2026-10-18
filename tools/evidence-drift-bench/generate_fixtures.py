"""Generate deterministic evidence drift benchmark fixtures."""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

SCENARIO_TYPES = (
    "supplier_evidence_supersession",
    "outdated_emissions_estimate",
    "changed_supplier_relationship",
    "cybersecurity_risk_evidence",
    "agent_memory_recall",
    "stale_agent_memory",
    "direct_decision_invalidation",
    "multi_hop_dependency_invalidation",
    "independently_supported_conclusion",
    "irrelevant_evidence_update",
    "cyclic_dependencies",
    "duplicate_events",
    "conflicting_sources",
    "cross_tenant_isolation",
    "approval_invalidation",
)


def _node(node_id: str, kind: str, tenant_id: str, **properties: Any) -> dict[str, Any]:
    """Create one graph node with stable identifiers and JSON values."""
    return {
        "id": node_id,
        "kind": kind,
        "tenant_id": tenant_id,
        **properties,
    }


def _relationship(source: str, target: str, kind: str) -> dict[str, str]:
    """Create a directed graph relationship."""
    return {"source": source, "target": target, "kind": kind}


def make_scenario(index: int, seed: int) -> dict[str, Any]:
    """Build one fully specified graph scenario from its deterministic seed."""
    rng = random.Random(seed)
    scenario_type = SCENARIO_TYPES[index % len(SCENARIO_TYPES)]
    scenario_id = f"scenario-{index + 1:03d}-{scenario_type}"
    tenant_id = f"tenant-{index + 1:03d}"
    source_id = f"{scenario_id}:evidence:original"
    updated_id = f"{scenario_id}:evidence:updated"
    event_id = f"{scenario_id}:event:update"
    tenant_node_id = f"{scenario_id}:tenant"

    nodes: list[dict[str, Any]] = [_node(tenant_node_id, "tenant", tenant_id)]
    tenant_node_by_id = {tenant_id: tenant_node_id}
    relationships: list[dict[str, str]] = []
    decisions: list[str] = []
    impacted: set[str] = set()

    invalidates_source = scenario_type not in {
        "agent_memory_recall",
        "irrelevant_evidence_update",
        "conflicting_sources",
    }
    original = _node(
        source_id,
        "evidence",
        tenant_id,
        current=not invalidates_source,
        invalidated=invalidates_source,
        evidence_type=scenario_type,
        source="supplier-audit" if "supplier" in scenario_type else "security-review",
    )
    updated = _node(
        updated_id,
        "evidence",
        tenant_id,
        current=True,
        invalidated=False,
        evidence_type=scenario_type,
        source="updated-audit",
        revision=2,
    )
    nodes.extend((original, updated))
    relationships.append(_relationship(updated_id, source_id, "SUPERSEDES" if invalidates_source else "UPDATES"))

    update_event = {
        "event_id": event_id,
        "event_type": "evidence_updated",
        "evidence_id": updated_id,
        "sequence": 2,
    }
    events = [update_event, dict(update_event)] if scenario_type == "duplicate_events" else [update_event]
    for event in events:
        nodes.append(_node(event["event_id"], "event", tenant_id, **{key: value for key, value in event.items() if key != "event_id"}))
        relationships.append(_relationship(event["event_id"], updated_id, "APPLIES_TO"))

    def add_decision(key: str, **properties: Any) -> str:
        decision_id = f"{scenario_id}:decision:{key}"
        nodes.append(_node(decision_id, "decision", tenant_id, **properties))
        decisions.append(decision_id)
        return decision_id

    memory_id = f"{scenario_id}:memory:agent"
    memory_related = scenario_type in {"agent_memory_recall", "stale_agent_memory"} or rng.random() < 0.12
    nodes.append(_node(memory_id, "memory", tenant_id, initially_valid=True, memory_kind="agent_recall"))
    relationships.append(_relationship(tenant_node_id, memory_id, "OWNS"))
    if memory_related:
        relationships.append(_relationship(source_id, memory_id, "MEMORY_SOURCE"))

    if scenario_type == "multi_hop_dependency_invalidation":
        first = add_decision("root")
        second = add_decision("dependent-1")
        third = add_decision("dependent-2")
        relationships.extend(
            (
                _relationship(source_id, first, "SUPPORTS"),
                _relationship(first, second, "DEPENDS_ON"),
                _relationship(second, third, "DEPENDS_ON"),
            )
        )
        impacted.update((first, second, third))
    elif scenario_type == "independently_supported_conclusion":
        supported = add_decision("independently-supported")
        unsupported = add_decision("source-only")
        relationships.extend(
            (
                _relationship(source_id, supported, "SUPPORTS"),
                _relationship(source_id, unsupported, "SUPPORTS"),
                _relationship(updated_id, supported, "SUPPORTS"),
            )
        )
        impacted.add(unsupported)
    elif scenario_type == "cyclic_dependencies":
        first = add_decision("cycle-a")
        second = add_decision("cycle-b")
        relationships.extend(
            (
                _relationship(source_id, first, "SUPPORTS"),
                _relationship(first, second, "DEPENDS_ON"),
                _relationship(second, first, "DEPENDS_ON"),
            )
        )
        impacted.update((first, second))
    elif scenario_type == "changed_supplier_relationship":
        supplier_link = f"{scenario_id}:supplier-relationship:primary"
        nodes.append(_node(supplier_link, "supplier_relationship", tenant_id, relationship_state="changed"))
        relationships.append(_relationship(source_id, supplier_link, "DESCRIBES"))
        decision = add_decision("supplier-exposure")
        relationships.append(_relationship(supplier_link, decision, "SUPPORTS"))
        impacted.add(decision)
    elif scenario_type == "cross_tenant_isolation":
        local = add_decision("local-risk")
        relationships.append(_relationship(source_id, local, "SUPPORTS"))
        impacted.add(local)
        foreign_tenant_id = f"{tenant_id}-foreign"
        foreign_tenant_node_id = f"{scenario_id}:tenant:foreign"
        foreign_decision = f"{scenario_id}:foreign-tenant:decision"
        tenant_node_by_id[foreign_tenant_id] = foreign_tenant_node_id
        nodes.extend(
            (
                _node(foreign_tenant_node_id, "tenant", foreign_tenant_id),
                _node(foreign_decision, "decision", foreign_tenant_id, decision_type="foreign"),
            )
        )
        relationships.extend(
            (
                _relationship(source_id, foreign_decision, "SUPPORTS"),
            )
        )
        decisions.append(foreign_decision)
    elif scenario_type == "approval_invalidation":
        approval_id = f"{scenario_id}:approval:primary"
        nodes.append(_node(approval_id, "approval", tenant_id, status="approved"))
        relationships.append(_relationship(source_id, approval_id, "SUPPORTS"))
        decision = add_decision("approved-decision", approval_required=True)
        relationships.append(_relationship(approval_id, decision, "APPROVES"))
        impacted.add(decision)
    elif scenario_type == "conflicting_sources":
        decision = add_decision("conflicting-conclusion")
        relationships.extend(
            (
                _relationship(source_id, decision, "SUPPORTS"),
                _relationship(updated_id, decision, "CHALLENGES"),
            )
        )
        impacted.add(decision)
    else:
        decision = add_decision("primary")
        relationships.append(_relationship(source_id, decision, "SUPPORTS"))
        if invalidates_source:
            impacted.add(decision)

    # Add deterministic, disconnected graph load so measurements cover more than a single path.
    for side_index in range(rng.randrange(0, 3)):
        add_decision(f"unrelated-{side_index + 1}", decision_type="unrelated")

    for node in nodes:
        if node["kind"] != "tenant":
            owner_id = tenant_node_by_id[node["tenant_id"]]
            relationships.append(_relationship(owner_id, node["id"], "OWNS"))

    expected_memory_valid = not (invalidates_source and memory_related)
    expected_affected = sorted(impacted)
    expected_unaffected = sorted(set(decisions) - impacted)
    explanation = (
        f"{scenario_type.replace('_', ' ')}: the original evidence is "
        f"{'invalidated by the update' if invalidates_source else 'still current'}; "
        f"{len(expected_affected)} decision(s) should be invalidated and "
        f"agent memory is {'valid' if expected_memory_valid else 'stale'}."
    )

    return {
        "scenario_id": scenario_id,
        "scenario_type": scenario_type,
        "seed": seed,
        "tenant_id": tenant_id,
        "source_evidence_id": source_id,
        "updated_evidence_id": updated_id,
        "original_evidence": original,
        "updated_evidence": updated,
        "events": events,
        "nodes": nodes,
        "relationships": relationships,
        "expected_affected_decisions": expected_affected,
        "expected_unaffected_decisions": expected_unaffected,
        "expected_memory_valid": expected_memory_valid,
        "expected_memory_ids": [memory_id],
        "explanation": explanation,
    }


def generate_fixtures(count: int = 50, seed: int = 98) -> dict[str, Any]:
    """Return the complete fixture document for the requested seed and count."""
    if count < len(SCENARIO_TYPES):
        raise ValueError(f"count must be at least {len(SCENARIO_TYPES)} to cover every scenario type")
    scenarios = [make_scenario(index, seed + index * 104729) for index in range(count)]
    return {"schema_version": 1, "seed": seed, "scenario_count": count, "scenarios": scenarios}


def write_fixtures(path: Path, count: int = 50, seed: int = 98) -> dict[str, Any]:
    """Generate fixtures and write them as stable formatted JSON."""
    document = generate_fixtures(count=count, seed=seed)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return document


def main() -> int:
    """Generate the default fixture file from command-line options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=98)
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--output", type=Path, default=Path("fixtures/scenarios.json"))
    args = parser.parse_args()
    document = write_fixtures(args.output, count=args.count, seed=args.seed)
    sys.stdout.write(f"Wrote {document['scenario_count']} scenarios to {args.output}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
