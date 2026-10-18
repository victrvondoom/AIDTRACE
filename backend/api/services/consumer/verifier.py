"""Deterministic verifier. Language models may propose; only this module decides a strategy's verdict.

Verdicts
  VERIFIED              every required condition is satisfied and every governing rule is citable
  REJECTED              a required condition is contradicted by graph facts (e.g. a claim amount
                        that ignores a recorded refund)
  INSUFFICIENT_EVIDENCE a required document is missing, a rule has no verified source, or sources conflict

cypher_cross_check re-derives the same verdicts with separate, smaller Cypher queries. Any mismatch
blocks the plan, so a bug in one path cannot silently produce an action.
"""
from collections import defaultdict

from api.services.consumer import citations

VERIFIED, REJECTED, INSUFFICIENT = "VERIFIED", "REJECTED", "INSUFFICIENT_EVIDENCE"
SATISFIED, UNSATISFIED, CONTRADICTED = "SATISFIED", "UNSATISFIED", "CONTRADICTED"
UNVERIFIED, SOURCE_CONFLICT = "UNVERIFIED", "SOURCE_CONFLICT"
_RANK = {SATISFIED: 0, UNVERIFIED: 1, SOURCE_CONFLICT: 2, UNSATISFIED: 3, CONTRADICTED: 4}
_TOLERANCE = 0.005


def load_facts(store) -> dict:
    """One read of everything a verdict depends on. Each query is labelled and single-hop."""
    case = store.query("MATCH (c:CitizenCase) RETURN c.id, c.event_date, c.jurisdiction LIMIT 1")
    if not case:
        raise LookupError("no case is loaded in this graph")
    facts = {"case_id": case[0][0], "event_date": case[0][1], "jurisdiction": case[0][2]}
    facts["evidence"] = {r[0]: {"type": r[1], "status": r[2], "amount": r[3] or 0.0}
                         for r in store.query("MATCH (e:Evidence) RETURN e.id, e.type, e.status, e.amount")}
    facts["claims"] = {r[0]: {"amount": r[1] or 0.0, "status": r[2]}
                       for r in store.query("MATCH (c:Claim) RETURN c.id, c.amount, c.status")}
    facts["sources"] = {r[0]: {"title": r[1], "verified": bool(r[2]), "effective_date": r[3] or "",
                               "jurisdiction": r[4], "excerpt": r[5]}
                        for r in store.query("MATCH (s:Source) RETURN s.id, s.title, s.verified, "
                                             "s.effective_date, s.jurisdiction, s.excerpt")}
    facts["rules"] = {r[0]: {"text": r[1], "condition_text": r[2], "source_id": r[3]}
                      for r in store.query("MATCH (r:Rule) RETURN r.id, r.text, r.condition_text, r.source_id")}
    facts["rule_conflicts"] = defaultdict(set)
    for rule_id, source_id in store.query("MATCH (s:Source)-[:CONTRADICTS]->(r:Rule) RETURN r.id, s.id"):
        facts["rule_conflicts"][rule_id].add(source_id)
    facts["conditions"] = {r[0]: {"text": r[1], "check": r[2]}
                           for r in store.query("MATCH (c:Condition) RETURN c.id, c.text, c.check")}
    facts["cond_evidence"] = _group(store.query(
        "MATCH (c:Condition)-[:REQUIRES_EVIDENCE]->(e:Evidence) RETURN c.id, e.id ORDER BY c.id, e.id"))
    facts["cond_rules"] = _group(store.query(
        "MATCH (c:Condition)-[:GOVERNED_BY]->(r:Rule) RETURN c.id, r.id ORDER BY c.id, r.id"))
    facts["cond_claim"] = {r[0]: r[1] for r in store.query(
        "MATCH (c:Condition)-[:CONCERNS]->(k:Claim) RETURN c.id, k.id")}
    facts["claim_evidence"] = _group(store.query(
        "MATCH (k:Claim)-[:INCLUDES]->(e:Evidence) RETURN k.id, e.id ORDER BY k.id, e.id"))
    facts["refunds_of"] = _group(store.query(
        "MATCH (r:Evidence)-[:REFUNDS]->(t:Evidence) RETURN t.id, r.id ORDER BY t.id, r.id"))
    facts["strategy_conditions"] = _group(store.query(
        "MATCH (s:Strategy)-[:REQUIRES]->(c:Condition) RETURN s.id, c.id ORDER BY s.id, c.id"))
    facts["strategies"] = {r[0]: {"title": r[1], "remedy_id": r[2], "remedy_title": r[3], "domains": r[4]}
                           for r in store.query(
                               "MATCH (s:Strategy)-[:PROPOSES]->(m:Remedy) "
                               "OPTIONAL MATCH (m)-[:IN_DOMAIN]->(d:Domain) "
                               "RETURN s.id, s.title, m.id, m.title, collect(DISTINCT d.name) ORDER BY s.id")}
    facts["dependencies"] = [{"condition": r[0], "on_type": r[1], "on_id": r[2]} for r in store.query(
        "MATCH (c:Condition)-[:DEPENDS_ON]->(x) RETURN c.id, labels(x)[0], x.id ORDER BY c.id")]
    facts["recovery_claims"] = [{"event": r[0], "remedy": r[1]} for r in store.query(
        "MATCH (m:Remedy)-[:CLAIMS_RECOVERY_FOR]->(e:Event) RETURN e.id, m.id ORDER BY e.id, m.id")]
    return facts


def _group(rows) -> dict:
    grouped: dict[str, list] = defaultdict(list)
    for key, value in rows:
        grouped[key].append(value)
    return grouped


def net_amount(claim_id: str, facts: dict) -> tuple[float, float, list[str]]:
    """Claimed amount, amount expected after deducting refunds already paid, and the refund ids used."""
    included = facts["claim_evidence"].get(claim_id, [])
    gross = sum(facts["evidence"][e]["amount"] for e in included)
    refund_ids = sorted({r for target in included for r in facts["refunds_of"].get(target, [])
                         if facts["evidence"][r]["status"] == "PRESENT"})
    refunded = sum(facts["evidence"][r]["amount"] for r in refund_ids)
    return facts["claims"][claim_id]["amount"], gross - refunded, refund_ids


def _rule_problems(rule_id: str, facts: dict) -> list[str]:
    return citations.check_rule(facts["rules"][rule_id], facts["sources"],
                                facts["rule_conflicts"].get(rule_id, set()),
                                facts["event_date"], facts["jurisdiction"])


def evaluate_condition(cid: str, facts: dict) -> dict:
    cond = facts["conditions"][cid]
    status = SATISFIED
    reasons, paths, missing, unverified = [], [], [], []

    def worse(current: str, new: str) -> str:
        return new if _RANK[new] > _RANK[current] else current

    if cond["check"] == "evidence":
        for eid in facts["cond_evidence"].get(cid, []):
            ev = facts["evidence"][eid]
            paths.append(f"{cid} -REQUIRES_EVIDENCE-> {eid} [{ev['status']}]")
            if ev["status"] != "PRESENT":
                status = worse(status, UNSATISFIED)
                missing.append(eid)
                reasons.append(f"{eid} {ev['type']} is {ev['status']}")

    if cond["check"] == "claim_net":
        claim_id = facts["cond_claim"].get(cid)
        claimed, expected, refund_ids = net_amount(claim_id, facts)
        paths.append(f"{cid} -CONCERNS-> {claim_id} [claimed {claimed:.2f}]")
        for rid in refund_ids:
            paths.append(f"{rid} -REFUNDS-> ... -INCLUDES-> {claim_id}")
        if abs(claimed - expected) > _TOLERANCE:
            status = worse(status, CONTRADICTED)
            reasons.append(f"{claim_id} claims {claimed:.2f}; {expected:.2f} is expected after deducting "
                           f"refund(s) {', '.join(refund_ids) or 'none'}")

    for rid in facts["cond_rules"].get(cid, []):
        source_id = facts["rules"][rid]["source_id"]
        verified = facts["sources"].get(source_id, {}).get("verified", False)
        paths.append(f"{cid} -GOVERNED_BY-> {rid} -CITES-> {source_id} [{'verified' if verified else 'unverified'}]")
        for problem in _rule_problems(rid, facts):
            if problem == "SOURCE_CONFLICT":
                status = worse(status, SOURCE_CONFLICT)
            else:
                status = worse(status, UNVERIFIED)
                unverified.append(rid)
            reasons.append(f"{rid}: {problem}")

    return {"id": cid, "text": cond["text"], "check": cond["check"], "status": status, "reasons": reasons,
            "paths": paths, "missing_evidence": missing, "unverified_rules": sorted(set(unverified))}


def verify_strategy(sid: str, facts: dict) -> dict:
    conditions = [evaluate_condition(c, facts) for c in facts["strategy_conditions"].get(sid, [])]
    statuses = {c["status"] for c in conditions}
    if CONTRADICTED in statuses:
        verdict = REJECTED
    elif statuses - {SATISFIED}:
        verdict = INSUFFICIENT
    else:
        verdict = VERIFIED
    meta = facts["strategies"][sid]
    return {
        "strategy_id": sid, "title": meta["title"], "remedy_id": meta["remedy_id"],
        "remedy_title": meta["remedy_title"], "domains": meta["domains"], "verdict": verdict,
        "blocked_by": SOURCE_CONFLICT if SOURCE_CONFLICT in statuses else None,
        "conditions": conditions,
        "reasons": [r for c in conditions for r in c["reasons"]],
        "missing_evidence": sorted({e for c in conditions for e in c["missing_evidence"]}),
        "unverified_rules": sorted({r for c in conditions for r in c["unverified_rules"]}),
    }


def verify_all(facts: dict) -> list[dict]:
    return [verify_strategy(sid, facts) for sid in sorted(facts["strategies"])]


def cypher_cross_check(store, facts: dict, verdicts: list[dict]) -> list[dict]:
    """Re-derive each verdict with separate Cypher queries. Returns the list of mismatches (empty = agree)."""
    mismatches = []
    for verdict in verdicts:
        independent_statuses = set()
        for cond in facts["strategy_conditions"].get(verdict["strategy_id"], []):
            rows = store.query(
                "MATCH (c:Condition {id: $c}) OPTIONAL MATCH (c)-[:REQUIRES_EVIDENCE]->(e:Evidence) "
                "WITH c, collect(e.status) AS statuses "
                "OPTIONAL MATCH (c)-[:GOVERNED_BY]->(r:Rule)-[:CITES]->(s:Source) "
                "WITH c, statuses, collect(s.verified AND s.jurisdiction = $jx AND s.effective_date <> '' "
                "AND s.effective_date <= $ed AND toLower(s.excerpt) CONTAINS toLower(r.condition_text)) AS citable "
                "OPTIONAL MATCH (c)-[:GOVERNED_BY]->(r2:Rule)<-[:CONTRADICTS]-(x:Source) "
                "RETURN statuses, citable, count(x)",
                {"c": cond, "jx": facts["jurisdiction"], "ed": facts["event_date"]})
            statuses, citable, conflicts = rows[0]
            if any(s != "PRESENT" for s in statuses):
                independent_statuses.add(UNSATISFIED)
            if any(v is not True for v in citable):
                independent_statuses.add(UNVERIFIED)
            if conflicts:
                independent_statuses.add(SOURCE_CONFLICT)
            if facts["conditions"][cond]["check"] == "claim_net":
                claim_id = facts["cond_claim"][cond]
                net_rows = store.query(
                    "MATCH (k:Claim {id: $k})-[:INCLUDES]->(i:Evidence) WITH k, sum(i.amount) AS gross "
                    "OPTIONAL MATCH (r:Evidence {status: 'PRESENT'})-[:REFUNDS]->(t:Evidence)<-[:INCLUDES]-(k) "
                    "RETURN k.amount, gross, sum(r.amount)",
                    {"k": claim_id})
                claimed, gross, refunded = net_rows[0]
                if abs((claimed or 0) - ((gross or 0) - (refunded or 0))) > _TOLERANCE:
                    independent_statuses.add(CONTRADICTED)
        if CONTRADICTED in independent_statuses:
            independent = REJECTED
        elif independent_statuses:
            independent = INSUFFICIENT
        else:
            independent = VERIFIED
        if independent != verdict["verdict"]:
            mismatches.append({"strategy_id": verdict["strategy_id"], "python": verdict["verdict"],
                               "cypher": independent})
    return mismatches
