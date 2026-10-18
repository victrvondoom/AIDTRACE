"""Human-approved execution of PROPOSED actions. Mutations here only touch the synthetic graph."""
import hashlib
import json
from datetime import datetime, timezone

from domains.fraud.store import GraphStore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def approve(store: GraphStore, action_id: str) -> dict:
    row = store.query("MATCH (x:Action {id: $id}) RETURN x.status, x.evidence", {"id": action_id})
    if not row:
        return {"error": "unknown action"}
    if row[0][0] != "PROPOSED":
        return {"error": f"action is {row[0][0]}, only PROPOSED actions can be approved"}
    executed_at = _now()
    # Synthetic execution: sets status on the demo graph only. No external system is called.
    targets = store.query(
        "MATCH (x:Action {id: $id}) SET x.status = 'EXECUTED', x.executed_at = $ts "
        "WITH x MATCH (x)-[:TARGETS]->(a:Account) SET a.status = 'FROZEN' "
        "RETURN a.id ORDER BY a.id",
        {"id": action_id, "ts": executed_at})
    target_ids = [t[0] for t in targets]
    receipt_src = json.dumps({"action": action_id, "targets": target_ids,
                              "evidence": row[0][1], "executed_at": executed_at}, sort_keys=True)
    receipt = hashlib.sha256(receipt_src.encode()).hexdigest()
    store.query("MATCH (x:Action {id: $id}) SET x.receipt = $receipt", {"id": action_id, "receipt": receipt})
    return {"action_id": action_id, "status": "EXECUTED", "frozen_accounts": target_ids,
            "executed_at": executed_at, "receipt": receipt}


def reject(store: GraphStore, action_id: str) -> dict:
    row = store.query("MATCH (x:Action {id: $id}) RETURN x.status", {"id": action_id})
    if not row:
        return {"error": "unknown action"}
    if row[0][0] != "PROPOSED":
        return {"error": f"action is {row[0][0]}, only PROPOSED actions can be rejected"}
    store.query("MATCH (x:Action {id: $id}) SET x.status = 'REJECTED', x.rejected_at = $ts",
                {"id": action_id, "ts": _now()})
    return {"action_id": action_id, "status": "REJECTED"}
