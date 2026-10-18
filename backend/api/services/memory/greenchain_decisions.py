"""GreenChain procurement decisions as evidence-aware memory.

`record_scenario` scores a supplier set with GreenChain's real models and writes the result into the site graph:

    dataset versions (USEEIO, Ember, GLEC, ND-GAIN)  <-  claims (top supplier, modelled estimates)  <-  agent memory
        <-  decision "recommend X"  <-  plan  <-  action proposal "place a trial order" (needs a human)

`revise_dataset` then replays "one reference dataset was revised": the revised factor is applied to one country's suppliers, the
real composite scorer re-ranks, and the evidence cascade runs on the persisted graph, so the memory, decision and approval that
rested on the old dataset are marked stale, the decision is re-evaluated against the new ranking, and a stale approval is refused.

The dataset revision is a COUNTERFACTUAL supplied by the caller (country and factor). It is not a claim that a published dataset
changed by that amount; the scenario's candidates are the illustrative ones GreenChain ships for demonstration.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from api.services.drift.model import Label, Rel, stable_hash
from api.services.memory.agent_memory import AgentMemory, _slug
from domains.greenchain import kairos_adapter as adapter

AGENT = "agent:greenchain-scorer"
DATASETS = tuple(adapter.DATASETS)


def _src(dataset: str, sid: str, version: int) -> str:
    return f"dataset:{dataset}:{sid}:v{version}"


def _estimate(row: dict[str, Any]) -> float:
    return round(float((row.get("emission_factor") or {}).get("q50_tco2e") or 0.0), 3)


def _rank_table(scored: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"name": r["name"], "rank": r["rank"], "total_tco2e": round(float((r.get("scores") or {}).get("total_tco2e") or 0.0), 2),
             "manufacturing_q50": _estimate(r), "country": r.get("country")} for r in scored]


def _claim_all_datasets(mem: AgentMemory, claim_id: str, sid: str, versions: dict[str, int]) -> None:
    """An estimate rests on every dataset: link the claim to each dataset's current version."""
    for ds in DATASETS:
        mem.store.link(mem.site, Label.CLAIM, claim_id, Rel.SUPPORTED_BY, Label.SOURCE_VERSION, _src(ds, sid, versions[ds]))


def record_scenario(mem: AgentMemory, *, scenario_id: str, transport_mode: str = "sea") -> dict[str, Any]:
    sid = _slug(scenario_id)
    scored = adapter.score_candidates(adapter.demo_candidates(), transport_mode=transport_mode)
    versions = {ds: 1 for ds in DATASETS}
    for ds, (label, version) in adapter.DATASETS.items():
        mem.record_source(document_id=f"dataset:{ds}", source_id=_src(ds, sid, 1), title=label, authority_level=2, confidence=0.95,
                          content_sha256=stable_hash([ds, version]), version_label=version)
    mem.register_agent(AGENT, "GreenChain scorer", specialty="supplier emissions scoring", system="greenchain")
    top, runner = scored[0], scored[1]
    top_claim = f"gc:{sid}:top:v1"
    mem.record_claim(claim_id=top_claim, source_id=_src(DATASETS[0], sid, 1), fact_key=f"top_supplier:{sid}", fact_value=top["name"], authority_level=2, confidence=0.9)
    est_claim = f"gc:{sid}:est:{_slug(top['name'])}:v1"
    mem.record_claim(claim_id=est_claim, source_id=_src(DATASETS[0], sid, 1), fact_key=f"emissions_q50:{sid}:{top['name']}", fact_value=_estimate(top), authority_level=2, confidence=0.9)
    for claim in (top_claim, est_claim):
        _claim_all_datasets(mem, claim, sid, versions)
    ef = top.get("emission_factor") or {}
    memory_id = f"gc:{sid}:mem:1"
    mem.remember(memory_id=memory_id, agent_id=AGENT, kind="SEMANTIC", claim_ids=[top_claim, est_claim], investigation_ref=f"greenchain:{sid}",
                 summary=f"{top['name']} ranks first under {transport_mode} transport: modelled manufacturing {ef.get('q50_tco2e')} tCO2e "
                         f"(80% interval {ef.get('q10_tco2e')} to {ef.get('q90_tco2e')}); {runner['name']} is second.",
                 details={"transport_mode": transport_mode, "ranking": [r["name"] for r in scored]})
    decision_id, action_id = f"gc:{sid}:decision", f"gc:{sid}:action"
    mem.propose_decision(decision_id=decision_id, summary=f"Recommend {top['name']} for the corrugated packaging component", memory_ids=[memory_id],
                         claim_ids=[top_claim], conditions=[{"key": f"top_supplier:{sid}", "op": "==", "value": top["name"], "material": True}],
                         plan_id=f"gc:{sid}:plan", plan_summary=f"Request a quotation and a trial order from {top['name']}.", action_id=action_id,
                         action_summary=f"Place a trial order with {top['name']} (requires human approval; nothing is sent).", actor="greenchain-scorer")
    return {"scenario_id": sid, "top": top["name"], "ranking": _rank_table(scored), "memory_id": memory_id, "decision_id": decision_id,
            "action_id": action_id, "claims": [top_claim, est_claim], "datasets": {ds: _src(ds, sid, 1) for ds in DATASETS}}


def revise_dataset(mem: AgentMemory, *, scenario_id: str, dataset: str, country: str, factor: float, label: str,
                   transport_mode: str = "sea") -> dict[str, Any]:
    sid = _slug(scenario_id)
    if dataset not in DATASETS:
        raise ValueError(f"dataset must be one of {DATASETS}")
    before = adapter.score_candidates(adapter.demo_candidates(), transport_mode=transport_mode)
    after = adapter.score_candidates(adapter.demo_candidates(), transport_mode=transport_mode, revision={"country": country, "factor": factor})
    top_old, top_new = before[0], after[0]
    tag = stable_hash([country, factor, label])[:8]
    change_id = f"gc:{sid}:change:{dataset}:{tag}"
    versions = {ds: 1 for ds in DATASETS}
    versions[dataset] = 2
    old_top_claim, new_top_claim = f"gc:{sid}:top:v1", f"gc:{sid}:top:v2:{tag}"
    old_est = f"gc:{sid}:est:{_slug(top_old['name'])}:v1"
    new_est = f"gc:{sid}:est:{_slug(top_new['name'])}:v2:{tag}"
    cascade = mem.supersede_source(
        old_source_id=_src(dataset, sid, 1), change_id=change_id, reason=f"{label}: modelled factor x{factor} for {country}",
        new_source={"document_id": f"dataset:{dataset}", "source_id": _src(dataset, sid, 2), "title": f"{adapter.DATASETS[dataset][0]} ({label})", "authority_level": 2,
                    "confidence": 0.95, "version_label": label, "content_sha256": stable_hash([dataset, label, country, factor])},
        new_claims=[{"claim_id": new_top_claim, "fact_key": f"top_supplier:{sid}", "fact_value": top_new["name"], "replaces": old_top_claim},
                    {"claim_id": new_est, "fact_key": f"emissions_q50:{sid}:{top_new['name']}", "fact_value": _estimate(top_new),
                     "replaces": old_est if top_old["name"] == top_new["name"] else None}])
    if cascade.get("duplicate"):
        return {"duplicate": True, **cascade}
    for claim in (new_top_claim, new_est):
        _claim_all_datasets(mem, claim, sid, versions)
    ef = top_new.get("emission_factor") or {}
    new_memory = f"gc:{sid}:mem:{tag}"
    mem.remember(memory_id=new_memory, agent_id=AGENT, kind="SEMANTIC", claim_ids=[new_top_claim, new_est], investigation_ref=f"greenchain:{sid}",
                 summary=f"After '{label}' ({dataset}, {country} x{factor}), {top_new['name']} ranks first: modelled manufacturing {ef.get('q50_tco2e')} tCO2e.",
                 details={"revision": {"dataset": dataset, "country": country, "factor": factor}, "ranking": [r["name"] for r in after]})
    decision_id, action_id = f"gc:{sid}:decision", f"gc:{sid}:action"
    reeval = mem.reevaluate_decision(decision_id=decision_id, new_dependency_ids=[new_memory, new_top_claim],
                                     current_facts={f"top_supplier:{sid}": (new_top_claim, top_new["name"])},
                                     reason=f"{label}: top supplier is now {top_new['name']}.")
    proposal = None
    if reeval["status"] == "INVALIDATED":
        proposal = mem.propose_decision(
            decision_id=f"gc:{sid}:decision:{tag}", summary=f"Recommend {top_new['name']} for the corrugated packaging component",
            memory_ids=[new_memory], claim_ids=[new_top_claim],
            conditions=[{"key": f"top_supplier:{sid}", "op": "==", "value": top_new["name"], "material": True}],
            plan_id=f"gc:{sid}:plan:{tag}", plan_summary=f"Request a quotation and a trial order from {top_new['name']}.",
            action_id=f"gc:{sid}:action:{tag}", action_summary=f"Place a trial order with {top_new['name']} (requires human approval; nothing is sent).",
            actor="greenchain-scorer")
    b, a = {r["name"]: r for r in _rank_table(before)}, {r["name"]: r for r in _rank_table(after)}
    return {
        "duplicate": False, "dataset": dataset, "revision": {"country": country, "factor": factor, "label": label}, "cascade": cascade,
        "ranking": [{"name": n, "rank_before": b[n]["rank"], "rank_after": a[n]["rank"], "total_before": b[n]["total_tco2e"],
                     "total_after": a[n]["total_tco2e"], "country": b[n]["country"]} for n in a],
        "recommendation_changed": top_old["name"] != top_new["name"], "top_before": top_old["name"], "top_after": top_new["name"],
        "old_decision": {"id": decision_id, "status": reeval["status"], "conditions": reeval["conditions"], "revision": reeval["revision"]},
        "old_action": {"id": action_id, "eligibility": mem.eligibility(action_id)},
        "new_proposal": ({"decision_id": proposal["decision_id"], "action_id": proposal["action_id"], "eligibility": mem.eligibility(proposal["action_id"])} if proposal else None),
        "new_memory_id": new_memory,
    }


def preview_revision(*, dataset: str, country: str, factor: float, transport_mode: str = "sea") -> dict[str, Any]:
    """Re-rank under a revised factor WITHOUT writing anything: the non-destructive version of `revise_dataset`."""
    if dataset not in DATASETS:
        raise ValueError(f"dataset must be one of {DATASETS}")
    before = adapter.score_candidates(adapter.demo_candidates(), transport_mode=transport_mode)
    after = adapter.score_candidates(adapter.demo_candidates(), transport_mode=transport_mode, revision={"country": country, "factor": factor})
    b, a = {r["name"]: r for r in _rank_table(before)}, {r["name"]: r for r in _rank_table(after)}
    return {"read_only": True, "dataset": dataset, "revision": {"country": country, "factor": factor}, "counterfactual": True,
            "top_before": before[0]["name"], "top_after": after[0]["name"], "recommendation_changes": before[0]["name"] != after[0]["name"],
            "ranking": [{"name": n, "country": b[n]["country"], "rank_before": b[n]["rank"], "rank_after": a[n]["rank"], "total_before": b[n]["total_tco2e"], "total_after": a[n]["total_tco2e"]} for n in a]}


def scenario_report(mem: AgentMemory, *, scenario_id: str) -> dict[str, Any]:
    """A procurement memo for one scenario, written only from what is in the graph: the recommendation and its state, the evidence it
    rests on, every revision with its dependency path, and the approval receipts. Anything unproven is stated as such."""
    sid = _slug(scenario_id)
    snap = mem.snapshot()
    prefix = f"gc:{sid}:"
    decisions = [d for d in snap["decisions"] if d["id"].startswith(prefix)]
    if not decisions:
        raise LookupError("no GreenChain scenario with that id has been recorded")
    actions = {a["id"]: a for a in snap["actions"] if a["id"].startswith(prefix)}
    memories = [m for m in snap["memories"] if m["id"].startswith(prefix)]
    sources = [x for x in snap["sources"] if f":{sid}:" in x["id"]]
    changes = [c for c in snap["changes"] if c["id"].startswith(prefix)]
    approvals = [a for a in mem.store.list_nodes(mem.site, Label.APPROVAL, limit=200) if a.get("decision_id", "").startswith(prefix)]
    lines = [f"# GreenChain procurement memo: scenario {sid}", "", f"Generated {datetime.now(UTC).isoformat(timespec='seconds')}. Written from the site graph only.", "",
             "> Candidates are illustrative, not real suppliers. Emissions are modelled intensities with uncertainty, not factory measurements, and certifications are unverified claims. "
             "Dataset revisions shown here are counterfactuals entered by a user, not changes to a published dataset.", "", "## Recommendation", ""]
    for d in sorted(decisions, key=lambda x: x["id"]):
        action = next((a for a in actions.values() if a["eligibility"].get("decision_id") == d["id"]), None)
        state = action["eligibility"] if action else {}
        lines.append(f"- **{d.get('summary')}** (decision `{d['id']}`, revision {d.get('revision_n')}): status **{d.get('status')}**. "
                     f"Action `{action['id'] if action else 'none'}` is **{action.get('status') if action else 'n/a'}**; "
                     + ("approval for the current revision is on record." if state.get("approval_current") else
                        ("it can be approved now." if state.get("eligible") else "it cannot be approved: " + "; ".join(state.get("reasons", ["no action"])) + ".")))
    lines += ["", "## Evidence behind it", ""]
    for m in sorted(memories, key=lambda x: x.get("recorded_at", "")):
        lines.append(f"- Memory `{m['id']}` ({m.get('status')}): {m.get('summary')} Supported by {len(m['claims'])} claim(s) from {len(m['sources'])} dataset version(s).")
    lines += ["", "Dataset versions:", ""] + [f"- `{x['id']}` {x.get('title')} ({x.get('version_label')}): {x.get('status')}" for x in sorted(sources, key=lambda x: x["id"])]
    lines += ["", "## Revision history", ""]
    if not changes:
        lines.append("No dataset revision has been applied to this scenario.")
    for c in sorted(changes, key=lambda x: x.get("observed_at", "")):
        result = json.loads(c.get("result_json", "{}") or "{}")
        lines.append(f"- `{c['id']}` at {c.get('observed_at')}: {c.get('reason')}. Authority verdict **{c.get('verdict')}**.")
        for hit in result.get("invalidated", []):
            lines.append(f"  - {hit['label']} `{hit['id']}`: {hit['before']} -> {hit['after']} via {' -> '.join(hit['via'])}")
    lines += ["", "## Approval receipts", ""]
    if not approvals:
        lines.append("No approval has been recorded.")
    for a in sorted(approvals, key=lambda x: x.get("approved_at", "")):
        lines.append(f"- `{a['id']}`: {a.get('approval_status')} for revision `{a.get('revision_id')}` (hash `{str(a.get('graph_revision'))[:12]}`), approved by {a.get('approved_by')} at {a.get('approved_at')}.")
    lines += ["", "Nothing in this memo was sent to a supplier, and no purchase was made."]
    return {"scenario_id": sid, "markdown": "\n".join(lines), "decisions": len(decisions), "revisions": len(changes), "approvals": len(approvals)}
