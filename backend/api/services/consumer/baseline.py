"""Non-graph baseline, used only to measure what the graph adds. It is deliberately simple.

Checklist rule: a remedy is recommended when every evidence item its conditions name is on file.
It does not check claim arithmetic, rule citations, source conflicts, or dependencies between remedies,
and it has no view of other domains. This is how a per-domain document checklist typically behaves.
"""
from api.services.consumer import verifier


def run(store) -> dict:
    facts = verifier.load_facts(store)
    recommended = []
    for sid in sorted(facts["strategies"]):
        evidence_ids = {e for cid in facts["strategy_conditions"].get(sid, [])
                        for e in facts["cond_evidence"].get(cid, [])}
        if all(facts["evidence"][e]["status"] == "PRESENT" for e in evidence_ids):
            recommended.append(sid)
    return {"method": "checklist: recommend when every named document is on file",
            "recommended": recommended, "conflicts_found": 0, "dependencies_found": 0,
            "evidence_gaps_ranked": 0}
