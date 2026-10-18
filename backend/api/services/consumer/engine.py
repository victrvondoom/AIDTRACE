"""RESOLVE consumer engine with FalkorDB: intake, parallel specialists, graph reconciliation, verification, planning.

Order of work
  1. Intake: which institutions and domains the case involves, read from the graph
  2. Domain specialists run in parallel. Each reports only its own domain's view (its remedies,
     the evidence those remedies need, its obligations)
  3. Cross-domain investigator reads the graph for shared evidence, dependencies and competing remedies
  4. Deterministic verifier decides each strategy; the independent Cypher cross-check must agree
  5. Evidence-gap investigator simulates each missing item in an isolated graph and ranks them
  6. Planner: verified strategies only; conflicts go to the user; a draft is created only if verified
  7. Persist AgentRun, Decision and GraphRevision nodes, and a DRAFT ProposedAction when one exists

If FalkorDB fails at any point, the result is GRAPH_UNAVAILABLE with no decision. Nothing falls back.
"""
import time
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from api.services.consumer import actions, graphdb, simulate, verifier
from api.services.consumer.remedy_conflicts import recommend_drops, unique_recovery_values


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _domains(store) -> list[dict]:
    rows = store.query("MATCH (c:CitizenCase)-[:INVOLVES]->(i:Institution)-[:IN_DOMAIN]->(d:Domain) "
                       "RETURN d.id, d.name, i.id, i.name, i.kind ORDER BY d.id, i.id")
    domains: dict[str, dict] = {}
    for d_id, d_name, i_id, i_name, kind in rows:
        entry = domains.setdefault(d_id, {"id": d_id, "name": d_name, "institutions": []})
        entry["institutions"].append({"id": i_id, "name": i_name, "kind": kind})
    return list(domains.values())


def _specialist(store, domain: dict) -> dict:
    started = time.perf_counter()
    rows = store.query(
        "MATCH (d:Domain {id: $d})<-[:IN_DOMAIN]-(m:Remedy)<-[:PROPOSES]-(s:Strategy)-[:REQUIRES]->(c:Condition) "
        "OPTIONAL MATCH (c)-[:REQUIRES_EVIDENCE]->(e:Evidence) "
        "RETURN m.id, s.id, c.id, collect(e.id), collect(e.status) ORDER BY m.id, s.id, c.id",
        {"d": domain["id"]})
    local: dict[str, dict] = {}
    for remedy, strategy, cond, ev_ids, ev_status in rows:
        entry = local.setdefault(remedy, {"remedy_id": remedy, "strategy_id": strategy, "ready": True,
                                          "conditions": [], "missing_evidence": []})
        entry["conditions"].append(cond)
        for eid, status in zip(ev_ids, ev_status):
            if status != "PRESENT":
                entry["ready"] = False
                entry["missing_evidence"].append(eid)
    obligations = store.query(
        "MATCH (d:Domain {id: $d})<-[:IN_DOMAIN]-(i:Institution)<-[:OWED_BY]-(o:Obligation) "
        "RETURN i.name, o.description ORDER BY i.name", {"d": domain["id"]})
    return {"agent": f"{domain['name']} specialist", "domain": domain["id"],
            "institutions": [i["name"] for i in domain["institutions"]],
            "obligations": [{"institution": r[0], "description": r[1]} for r in obligations],
            "local_view": sorted(local.values(), key=lambda x: x["remedy_id"]),
            "ms": round((time.perf_counter() - started) * 1000, 1)}


def _cross_domain(facts: dict, verdicts: list[dict]) -> dict:
    by_strategy = {v["strategy_id"]: v for v in verdicts}
    ev_strategies: dict[str, set] = defaultdict(set)
    for sid, conds in facts["strategy_conditions"].items():
        for cid in conds:
            for eid in facts["cond_evidence"].get(cid, []):
                ev_strategies[eid].add(sid)
    shared = []
    for eid, sids in sorted(ev_strategies.items()):
        domains = sorted({d for s in sids for d in by_strategy[s]["domains"]})
        if len(domains) >= 2:
            shared.append({"evidence_id": eid, "type": facts["evidence"][eid]["type"],
                           "status": facts["evidence"][eid]["status"],
                           "strategies": sorted(sids), "domains": domains})
    deps = []
    for dep in facts["dependencies"]:
        sids = sorted(s for s, conds in facts["strategy_conditions"].items() if dep["condition"] in conds)
        deps.append({"condition": dep["condition"], "depends_on": f"{dep['on_id']} ({dep['on_type']})",
                     "strategies": sids})
    remedy_strategy = {meta["remedy_id"]: sid for sid, meta in facts["strategies"].items()}
    claimers: dict[str, set] = defaultdict(set)
    for claim in facts["recovery_claims"]:
        sid = remedy_strategy.get(claim["remedy"])
        if sid and by_strategy[sid]["verdict"] != verifier.REJECTED:
            claimers[claim["event"]].add(sid)
    conflicts = [{"event": event, "strategies": sorted(sids),
                  "domains": sorted({d for s in sids for d in by_strategy[s]["domains"]})}
                 for event, sids in sorted(claimers.items()) if len(sids) >= 2]
    return {"shared_evidence": shared, "dependencies": deps, "conflicts": conflicts}


def _plan(verdicts: list[dict], cross: dict, gaps: list[dict], mismatches: list[dict]) -> dict:
    if mismatches:
        return {"status": "BLOCKED", "reason": "independent Cypher check disagrees with the verifier",
                "mismatches": mismatches, "verified": [], "rejected": [], "insufficient": [],
                "conflicts": [], "draft_strategy_id": None, "alternatives": [], "next_evidence": None}
    verified = [v for v in verdicts if v["verdict"] == verifier.VERIFIED]
    verified_ids = {v["strategy_id"] for v in verified}
    conflicts = [c for c in cross["conflicts"] if set(c["strategies"]) <= verified_ids]
    rejected = [{"strategy_id": v["strategy_id"], "title": v["title"], "reasons": v["reasons"]}
                for v in verdicts if v["verdict"] == verifier.REJECTED]
    insufficient = [{"strategy_id": v["strategy_id"], "title": v["title"], "blocked_by": v["blocked_by"],
                     "missing_evidence": v["missing_evidence"], "unverified_rules": v["unverified_rules"],
                     "reasons": v["reasons"]}
                    for v in verdicts if v["verdict"] == verifier.INSUFFICIENT]
    next_gap = next((g for g in gaps if g["verified_gain"] > 0), None)
    if not verified:
        return {"status": "NO_VERIFIED_STRATEGY", "reason": "no strategy is verified on current evidence",
                "verified": [], "rejected": rejected, "insufficient": insufficient, "conflicts": [],
                "draft_strategy_id": None, "alternatives": [], "next_evidence": next_gap}
    best = sorted(verified, key=lambda v: (-len(v["domains"]), v["strategy_id"]))[0]
    alternatives = []
    for c in conflicts:
        if best["strategy_id"] in c["strategies"]:
            others = [s for s in c["strategies"] if s != best["strategy_id"]]
            alternatives.append({"event": c["event"], "conflicts_with": others,
                                 "message": (f"{', '.join(others)} is also verified but claims recovery for "
                                             f"{c['event']} that {best['strategy_id']} also claims. "
                                             "The user chooses one.")})
    status = "NEEDS_USER_DECISION" if alternatives else "READY_FOR_REVIEW"
    return {"status": status, "reason": None, "verified": [v["strategy_id"] for v in verified],
            "rejected": rejected, "insufficient": insufficient, "conflicts": conflicts,
            "draft_strategy_id": best["strategy_id"], "alternatives": alternatives,
            "next_evidence": next_gap}


def _persist(store, run_id: str, specialists: list[dict], verdicts: list[dict], plan: dict,
             revision: str, facts: dict) -> dict:
    store.query("MATCH (r:AgentRun) DETACH DELETE r")
    store.query("MATCH (d:Decision) DETACH DELETE d")
    # Keep an unapproved draft only while it still matches the planned strategy and current revision.
    keep_strategy = plan["draft_strategy_id"] or ""
    store.query("MATCH (a:ProposedAction) WHERE a.status = 'DRAFT' AND "
                "(a.revision <> $rev OR a.strategy_id <> $s) DETACH DELETE a",
                {"rev": revision, "s": keep_strategy})
    names = [f"{s['agent']}" for s in specialists] + ["Cross-domain investigator", "Verifier",
                                                       "Independent Cypher check", "Planner"]
    store.query("UNWIND $rows AS r CREATE (a:AgentRun {id: r.id, run_id: r.run_id, agent: r.agent, "
                "status: 'DONE', at: r.at})",
                {"rows": [{"id": f"{run_id}-{i}", "run_id": run_id, "agent": n, "at": _now()}
                          for i, n in enumerate(names)]})
    store.query("UNWIND $rows AS r CREATE (d:Decision {id: r.id, strategy_id: r.s, verdict: r.v, "
                "revision: r.rev, run_id: r.run_id})",
                {"rows": [{"id": f"{run_id}-{v['strategy_id']}", "s": v["strategy_id"],
                           "v": v["verdict"], "rev": revision, "run_id": run_id} for v in verdicts]})
    store.query("UNWIND $rows AS r MATCH (d:Decision {id: r.id}) MATCH (s:Strategy {id: r.s}) "
                "CREATE (d)-[:DECIDES]->(s)",
                {"rows": [{"id": f"{run_id}-{v['strategy_id']}", "s": v["strategy_id"]} for v in verdicts]})
    store.query("MERGE (g:GraphRevision {id: $gid}) SET g.hash = $rev, g.created_at = $ts",
                {"gid": f"REV-{revision}", "rev": revision, "ts": _now()})
    draft = None
    if plan["draft_strategy_id"]:
        approved = store.query("MATCH (a:ProposedAction) WHERE a.status = 'APPROVED_LOCAL' AND a.strategy_id = $s "
                               "AND a.approved_revision = $rev RETURN count(a)",
                               {"s": plan["draft_strategy_id"], "rev": revision})[0][0]
        if approved:
            # Already approved at this revision: do not offer a second approval for the same content.
            store.query("MATCH (a:ProposedAction) WHERE a.status = 'DRAFT' AND a.strategy_id = $s "
                        "DETACH DELETE a", {"s": plan["draft_strategy_id"]})
            return {"decisions_written": len(verdicts), "draft": None}
        existing = store.query("MATCH (a:ProposedAction) WHERE a.status = 'DRAFT' AND a.strategy_id = $s "
                               "AND a.revision = $rev RETURN a.id, a.body LIMIT 1",
                               {"s": plan["draft_strategy_id"], "rev": revision})
        if existing:
            # Same revision, same strategy: keep the action ID, refresh the text to the current template.
            verdict = next(v for v in verdicts if v["strategy_id"] == plan["draft_strategy_id"])
            body = actions.draft_text(verdict, facts)
            store.query("MATCH (a:ProposedAction {id: $id}) SET a.body = $body", {"id": existing[0][0], "body": body})
            draft = {"action_id": existing[0][0], "status": "DRAFT",
                     "strategy_id": plan["draft_strategy_id"], "revision": revision, "body": body}
        else:
            verdict = next(v for v in verdicts if v["strategy_id"] == plan["draft_strategy_id"])
            draft = actions.create_draft(store, verdict, facts, revision)
    return {"decisions_written": len(verdicts), "draft": draft}


def _resolution(store, facts: dict, plan: dict) -> dict:
    """Which conflicting verified remedies to drop, at the least recovery value forgone (advisory only).

    The plan status and the draft are unchanged. The user still chooses. See capabilities/remedy_conflicts.py.
    """
    conflicts = plan["conflicts"]
    if not conflicts:
        return recommend_drops([], {})
    members = {s for c in conflicts for s in c["strategies"]}
    event_evidence: dict[str, list[str]] = defaultdict(list)
    for event, evidence in store.query(
            "MATCH (e:Event)-[:EVIDENCED_BY]->(v:Evidence) RETURN e.id, v.id ORDER BY e.id, v.id"):
        event_evidence[event].append(evidence)
    values = unique_recovery_values(facts, event_evidence, members)
    return recommend_drops(conflicts, values)


def _unavailable(message: str, started: float) -> dict:
    return {"status": "GRAPH_UNAVAILABLE", "message": message,
            "decision": None, "note": "No decision was made. The engine does not fall back to another store.",
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1)}


def analyze(store, run_id: str | None = None) -> dict:
    started = time.perf_counter()
    run_id = run_id or f"RUN-{uuid.uuid4().hex[:8]}"
    trace: list[dict] = []
    try:
        facts = verifier.load_facts(store)
        revision = graphdb.compute_revision(store)["revision"]
        domains = _domains(store)
        trace.append({"agent": "Case intake", "event": "loaded", "detail": f"{facts['case_id']}: "
                      f"{len(domains)} domain(s), {len(facts['strategies'])} strategies"})
        with ThreadPoolExecutor(max_workers=max(1, len(domains))) as pool:
            specialists = list(pool.map(lambda d: _specialist(store, d), domains))
        for s in specialists:
            trace.append({"agent": s["agent"], "event": "reported",
                          "detail": f"{len(s['local_view'])} remedy(ies) in domain, {s['ms']} ms"})
        verdicts = verifier.verify_all(facts)
        mismatches = verifier.cypher_cross_check(store, facts, verdicts)
        cross = _cross_domain(facts, verdicts)
        trace.append({"agent": "Cross-domain investigator", "event": "reconciled",
                      "detail": f"{len(cross['shared_evidence'])} shared evidence item(s), "
                                f"{len(cross['dependencies'])} dependency(ies), "
                                f"{len(cross['conflicts'])} conflict(s)"})
        trace.append({"agent": "Verifier", "event": "decided",
                      "detail": ", ".join(f"{v['strategy_id']}={v['verdict']}" for v in verdicts)})
        trace.append({"agent": "Independent Cypher check", "event": "compared",
                      "detail": "agrees" if not mismatches else f"{len(mismatches)} mismatch(es)"})
        gaps = simulate.evidence_gap_ranking(store, verdicts)
        trace.append({"agent": "Evidence-gap investigator", "event": "simulated",
                      "detail": f"{len(gaps)} candidate(s) tested in isolated graphs"})
        plan = _plan(verdicts, cross, gaps, mismatches)
        plan["resolution"] = _resolution(store, facts, plan)
        persisted = _persist(store, run_id, specialists, verdicts, plan, revision, facts)
        trace.append({"agent": "Planner", "event": "planned", "detail": plan["status"]})
    except LookupError as exc:
        return {"status": "NO_CASE", "message": str(exc),
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 1)}
    except Exception as exc:  # any FalkorDB failure ends the run with no decision
        return _unavailable(f"FalkorDB query failed: {type(exc).__name__}: {str(exc)[:160]}", started)

    return {
        "status": "OK", "run_id": run_id, "case_id": facts["case_id"], "revision": revision,
        "domains": domains, "specialists": specialists, "verdicts": verdicts,
        "cross_domain": cross, "evidence_gaps": gaps[:5], "plan": plan,
        "independent_check": {"agrees": not mismatches, "mismatches": mismatches},
        "draft": persisted["draft"], "trace": trace,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
    }
