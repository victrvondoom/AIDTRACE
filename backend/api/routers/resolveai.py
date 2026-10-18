"""Kairos-native ResolveAI investigation and evidence drift routes."""
from __future__ import annotations

import asyncio

import structlog
from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies import (
    CurrentUserDep,
    FalkorDriftDep,
    site_scope,
    require_role,
)
from api.services import tenant
from api.services.drift.demo_workflow import run_evidence_supersession
from api.services.drift.model import ContractError, check_site

log = structlog.get_logger(__name__)
router = APIRouter()
STAFF = ("engineer", "reliability", "admin")


def _site_for_user(current_user: dict, *, write: bool) -> str:
    site_id = "SITE_DEMO" if tenant.is_demo_user(current_user) else site_scope(
        current_user, current_user.get("site_id"), write=write
    )
    if not site_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="A site assignment is required.")
    try:
        check_site(site_id)
    except ContractError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="A valid site assignment is required.") from exc
    return site_id


@router.get("/drift/demo", summary="Read the isolated synthetic Evidence Drift case")
async def read_drift_demo(
    current_user: CurrentUserDep,
    store: FalkorDriftDep,
    _staff: dict = Depends(require_role(*STAFF)),
) -> dict:
    """Return the local synthetic demonstration state without creating or changing graph data."""
    site_id = _site_for_user(current_user, write=False)
    ids = (
        "DEMO-DRIFT-SOP-V1", "DEMO-DRIFT-SOP-V2", "DEMO-DRIFT-CLAIM-V1",
        "DEMO-DRIFT-CLAIM-V2", "DEMO-DRIFT-MEMORY-001", "DEMO-DRIFT-DECISION-001",
        "DEMO-DRIFT-PLAN-001", "DEMO-DRIFT-ACTION-001", "DEMO-DRIFT-AUDIT-V2",
        "DEMO-DRIFT-DECISION-REV-001", "DEMO-DRIFT-DECISION-REV-002",
        "DEMO-DRIFT-APPROVAL-REV-001", "DEMO-DRIFT-AGENT-CURATOR",
        "DEMO-DRIFT-AGENT-INVESTIGATOR", "DEMO-DRIFT-SESSION-CURATOR",
        "DEMO-DRIFT-SESSION-INVESTIGATOR",
    )
    try:
        nodes = await asyncio.to_thread(lambda: {node_id: store.read_node(site_id, node_id) for node_id in ids})
    except Exception as exc:  # noqa: BLE001
        log.warning("resolveai.drift_read_failed", error=repr(exc), site_id=site_id)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="FalkorDB is unavailable.") from exc
    current_revision_id = (nodes.get("DEMO-DRIFT-DECISION-001") or {}).get("properties", {}).get("current_revision_id")
    current_revision = (nodes.get(current_revision_id) or {}).get("properties") if current_revision_id else None
    prior_revision = (nodes.get("DEMO-DRIFT-DECISION-REV-001") or {}).get("properties")
    approval = (nodes.get("DEMO-DRIFT-APPROVAL-REV-001") or {}).get("properties")
    return {
        "case_id": "DEMO-DRIFT-HV-001",
        "scenario": "synthetic_only",
        "seeded": any(nodes.values()),
        "statuses": {
            node_id: node["properties"].get("status") if node else "NOT_CREATED"
            for node_id, node in nodes.items()
        },
        "decision_head": {
            "revision_n": (nodes.get("DEMO-DRIFT-DECISION-001") or {}).get("properties", {}).get("revision_n"),
            "current_revision_id": current_revision_id,
        },
        "decision_revision": ({
            "previous_revision_id": "DEMO-DRIFT-DECISION-REV-001",
            "previous_graph_revision": (prior_revision or {}).get("graph_revision"),
            "current_revision_id": current_revision_id,
            "current_graph_revision": (current_revision or {}).get("graph_revision"),
        } if current_revision else None),
        "human_review": ({
            "approval_id": "DEMO-DRIFT-APPROVAL-REV-001",
            "approved_revision_id": (approval or {}).get("revision_id"),
            "approval_status": (approval or {}).get("approval_status"),
            "matches_current_revision": bool(current_revision and approval and
                approval.get("graph_revision") == current_revision.get("graph_revision")),
        } if approval else None),
        "approval": approval,
        "agent_sessions": [
            (nodes[node_id] or {}).get("properties") for node_id in
            ("DEMO-DRIFT-SESSION-CURATOR", "DEMO-DRIFT-SESSION-INVESTIGATOR") if nodes.get(node_id)
        ],
        "external_actions_executed": False,
    }


@router.post("/drift/demo", summary="Run the synthetic evidence supersession and revalidation journey")
async def run_drift_demo(
    current_user: CurrentUserDep,
    store: FalkorDriftDep,
    _staff: dict = Depends(require_role(*STAFF)),
) -> dict:
    """Run deterministic synthetic reasoning, source authority, memory, impact and action checks.

    The scenario is hard-coded and isolated; it cannot target real assets or execute plant actions.
    Real/demo tenant scoping remains site-bound, and demo role writes are fenced to showcase IDs.
    """
    if tenant.is_demo_user(current_user):
        tenant.guard_site(current_user, "SITE_DEMO")
        tenant.guard_asset(current_user, "DEMO-HV-PUMP-001")
    site_id = _site_for_user(current_user, write=True)
    try:
        return await asyncio.to_thread(run_evidence_supersession, store, site_id)
    except ContractError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log.warning("resolveai.drift_run_failed", error=repr(exc), site_id=site_id)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="FalkorDB workflow is unavailable.") from exc
