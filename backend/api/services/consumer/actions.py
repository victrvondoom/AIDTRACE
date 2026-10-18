"""Reviewable local actions. Nothing here submits to a regulator or an institution.

A draft is bound to the evidence revision it was verified against. Approval checks that:
  1. the reviewer approved the same revision the draft was made from (else STALE_REVISION)
  2. the strategy is still VERIFIED at the current revision (else STRATEGY_NOT_VERIFIED)
If evidence changes after approval, the stored approval no longer matches and the status reads INVALIDATED.
"""
import uuid
from datetime import UTC, datetime

from api.services.consumer import graphdb, verifier


def _now() -> str:
    return datetime.now(UTC).isoformat()


def draft_text(verdict: dict, facts: dict) -> str:
    lines = [
        f"Complaint draft for synthetic case {facts['case_id']}. Not submitted.",
        f"Requested remedy: {verdict['remedy_title']}"
        + ("." if verdict["remedy_title"] == verdict["title"] else f" ({verdict['title']}).") ,
        "Conditions checked against the graph:",
    ]
    for cond in verdict["conditions"]:
        lines.append(f"- {cond['text']}: {cond['status']}")
    for path in sorted({p for c in verdict["conditions"] for p in c["paths"]}):
        lines.append(f"    path: {path}")
    present = sorted(eid for eid, ev in facts["evidence"].items() if ev["status"] == "PRESENT")
    lines.append(f"Evidence on file: {', '.join(present)}")
    lines.append("External submission: disabled. A person must review and send this manually.")
    return "\n".join(lines)


def create_draft(store, verdict: dict, facts: dict, revision: str) -> dict:
    action_id = f"ACT-{uuid.uuid4().hex[:8]}"
    body = draft_text(verdict, facts)
    store.query(
        "CREATE (a:ProposedAction {id: $id, type: 'DRAFT_COMPLAINT', status: 'DRAFT', strategy_id: $s, "
        "revision: $rev, created_at: $ts, body: $body, external_submission: 'disabled', "
        "approved_revision: '', approved_at: '', approved_by: ''})",
        {"id": action_id, "s": verdict["strategy_id"], "rev": revision, "ts": _now(), "body": body})
    store.query("MATCH (a:ProposedAction {id: $id}) MATCH (s:Strategy {id: $s}) CREATE (a)-[:BASED_ON]->(s)",
                {"id": action_id, "s": verdict["strategy_id"]})
    store.query("MERGE (g:GraphRevision {id: $gid}) SET g.hash = $rev, g.created_at = $ts",
                {"gid": f"REV-{revision}", "rev": revision, "ts": _now()})
    store.query("MATCH (a:ProposedAction {id: $id}) MATCH (g:GraphRevision {id: $gid}) "
                "CREATE (a)-[:VERIFIED_AT]->(g)", {"id": action_id, "gid": f"REV-{revision}"})
    return {"action_id": action_id, "status": "DRAFT", "strategy_id": verdict["strategy_id"],
            "revision": revision, "body": body}


def _row(store, action_id: str):
    rows = store.query("MATCH (a:ProposedAction {id: $id}) RETURN a.status, a.strategy_id, a.revision, "
                       "a.approved_revision, a.body, a.approved_by, a.approved_at",
                       {"id": action_id})
    return rows[0] if rows else None


def status_of(store, action_id: str) -> dict:
    row = _row(store, action_id)
    if row is None:
        return {"error": "unknown action"}
    status, strategy_id, revision, approved_rev, body, approved_by, approved_at = row
    current = graphdb.compute_revision(store)["revision"]
    if status == "APPROVED_LOCAL" and approved_rev != current:
        store.query("MATCH (a:ProposedAction {id: $id}) SET a.status = 'INVALIDATED'", {"id": action_id})
        status = "INVALIDATED"
    return {"action_id": action_id, "status": status, "strategy_id": strategy_id, "draft_revision": revision,
            "approved_revision": approved_rev, "current_revision": current, "body": body,
            "approved_by": approved_by, "approved_at": approved_at, "external_submission": "disabled"}


def approve(store, action_id: str, reviewed_revision: str, reviewer: str = "reviewer") -> dict:
    current = graphdb.compute_revision(store)["revision"]
    if reviewed_revision != current:
        return {"error": "STALE_REVISION", "current_revision": current,
                "message": "Evidence changed after this draft was made. Re-run the analysis before approving."}
    row = _row(store, action_id)
    if row is None:
        return {"error": "unknown action"}
    if row[0] != "DRAFT":
        return {"error": f"action is {row[0]}; only DRAFT actions can be approved"}
    verdict = verifier.verify_strategy(row[1], verifier.load_facts(store))
    if verdict["verdict"] != verifier.VERIFIED:
        return {"error": "STRATEGY_NOT_VERIFIED", "verdict": verdict["verdict"], "reasons": verdict["reasons"]}
    approved_at = _now()
    store.query("MATCH (a:ProposedAction {id: $id}) SET a.status = 'APPROVED_LOCAL', a.approved_revision = $rev, "
                "a.approved_at = $ts, a.approved_by = $by",
                {"id": action_id, "rev": current, "ts": approved_at, "by": reviewer})
    return {"action_id": action_id, "status": "APPROVED_LOCAL", "approved_revision": current,
            "approved_at": approved_at, "external_submission": "disabled"}


def reject(store, action_id: str) -> dict:
    row = _row(store, action_id)
    if row is None:
        return {"error": "unknown action"}
    if row[0] != "DRAFT":
        return {"error": f"action is {row[0]}; only DRAFT actions can be rejected"}
    store.query("MATCH (a:ProposedAction {id: $id}) SET a.status = 'REJECTED'", {"id": action_id})
    return {"action_id": action_id, "status": "REJECTED"}
