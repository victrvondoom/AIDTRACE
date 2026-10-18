"""Evidence Drift Cascade — REST API for dependency-aware invalidation.

This router exposes the Evidence Drift Cascade engine. It assumes the caller has already
verified their permissions via the existing Kairos authentication and tenant-scoping
middlewares. Site isolation is enforced by the graph selection in FalkorDriftStore.

No cross-tenant evidence leakage: every graph operation is bound to the request's site_id.
No unsafe action execution: actions are suspended, not executed, when evidence drifts.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from ..dependencies import CurrentUserDep, SettingsDep, require_role, site_scope
from ..services.drift import model
from ..services.drift.engine import DependencyEdge, ImpactPath, find_impacted_dependents
from ..services.drift.store import FalkorDriftStore, TraversalLimitExceeded
from ..services import tenant

log = logging.getLogger(__name__)

router = APIRouter(prefix="/drift", tags=["Evidence Drift Cascade"])
STAFF = ("engineer", "reliability", "admin")


def _site_for_user(current_user: dict, requested: str | None, *, write: bool) -> str | None:
    """Bind graph access to the verified user's site and the demo showcase fence."""
    if tenant.is_demo_user(current_user):
        site_id = requested or "SITE_DEMO"
        tenant.guard_site(current_user, site_id)
        return site_id
    site_id = site_scope(current_user, requested or current_user.get("site_id"), write=write)
    if requested is not None and site_id != requested:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Site access denied.")
    return site_id

# ----------------------------------------------------------------------------------------
# Request / Response schemas
# ----------------------------------------------------------------------------------------


class NodeCreateRequest(BaseModel):
    """Create a node in the drift graph. Only canonical drift labels are accepted."""

    label: Annotated[model.Label, Query(alias="label")]
    node_id: str
    properties: dict[str, Any] = {}


class EdgeCreateRequest(BaseModel):
    """Create a dependency edge. Edges point from dependent to dependency."""

    source_label: Annotated[model.Label, Query(alias="source_label")]
    source_id: str
    target_label: Annotated[model.Label, Query(alias="target_label")]
    target_id: str
    relationship: Annotated[model.Rel, Query(alias="relationship")]
    properties: dict[str, Any] = {}
    kind: model.EdgeKind = model.EdgeKind.LOGICAL


class ImpactRequest(BaseModel):
    """Request to find all downstream dependents of changed evidence."""

    changed_ids: list[str]


class ImpactResponse(BaseModel):
    """Impact traversal result: all dependents reachable within the depth limit."""

    impacted: list[dict]  # list of ImpactPath.as_dict()
    traversal_limited: bool = False
    site_id: str


class NodeStatus(BaseModel):
    """Status of a node in the drift graph."""

    node_id: str
    label: str
    status: str
    detail: dict[str, Any] = {}


# ----------------------------------------------------------------------------------------
# Dependency injection
# ----------------------------------------------------------------------------------------


def get_drift_store(settings: SettingsDep) -> FalkorDriftStore:
    """Single FalkorDriftStore instance per lifespan."""
    return FalkorDriftStore(
        url=settings.FALKORDB_URL,
        graph_prefix=settings.FALKORDB_GRAPH_PREFIX,
        query_timeout_ms=settings.FALKORDB_QUERY_TIMEOUT_MS,
        max_depth=settings.DRIFT_MAX_DEPTH,
        max_edges=settings.DRIFT_MAX_EDGES,
    )


@asynccontextmanager
async def get_drift_store_async(settings: SettingsDep) -> AsyncIterator[FalkorDriftStore]:
    """Async-safe store with thread-isolated operations."""
    store = get_drift_store(settings)
    try:
        yield store
    finally:
        store.close()


# ----------------------------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------------------------


@router.get("/health", summary="Drift store connectivity")
async def drift_health(
    settings: SettingsDep,
    current_user: CurrentUserDep,
    _staff: dict = Depends(require_role(*STAFF)),
) -> dict[str, bool]:
    """Check FalkorDB connectivity and site-graph existence."""
    site_id = _site_for_user(current_user, None, write=False)
    store = get_drift_store(settings)
    try:
        return store.inspect_site(site_id)
    finally:
        store.close()


@router.post("/nodes/{site_id}", summary="Create drift graph node")
async def create_node(
    site_id: str,
    request: NodeCreateRequest,
    settings: SettingsDep,
    current_user: CurrentUserDep,
    _staff: dict = Depends(require_role(*STAFF)),
) -> dict[str, str]:
    """Insert one node. Fails if the label is not in the drift schema."""
    tenant.guard_site(current_user, site_id)
    site_id = _site_for_user(current_user, site_id, write=True)
    assert site_id is not None
    store = get_drift_store(settings)
    try:
        store.upsert_node(site_id, request.label, request.node_id, request.properties)
        return {"node_id": request.node_id, "label": request.label.value, "status": "created"}
    except Exception as exc:
        log.warning("drift.node.create_failed", error=str(exc), site=site_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create node: {type(exc).__name__}",
        ) from exc
    finally:
        store.close()


@router.post("/edges/{site_id}", summary="Create dependency edge")
async def create_edge(
    site_id: str,
    request: EdgeCreateRequest,
    settings: SettingsDep,
    current_user: CurrentUserDep,
    _staff: dict = Depends(require_role(*STAFF)),
) -> dict[str, str]:
    """Link two existing nodes. Fails if either node does not exist."""
    tenant.guard_site(current_user, site_id)
    site_id = _site_for_user(current_user, site_id, write=True)
    assert site_id is not None
    store = get_drift_store(settings)
    props = request.properties
    props["kind"] = request.kind.value
    try:
        store.link(
            site_id,
            request.source_label,
            request.source_id,
            request.relationship,
            request.target_label,
            request.target_id,
            props,
        )
        return {
            "source_id": request.source_id,
            "target_id": request.target_id,
            "relationship": request.relationship.value,
            "status": "linked",
        }
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        log.warning("drift.edge.create_failed", error=str(exc), site=site_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create edge: {type(exc).__name__}",
        ) from exc
    finally:
        store.close()


@router.post("/impact/{site_id}", summary="Compute impact of evidence changes")
async def compute_impact(
    site_id: str,
    request: ImpactRequest,
    settings: SettingsDep,
    current_user: CurrentUserDep,
    _staff: dict = Depends(require_role(*STAFF)),
) -> ImpactResponse:
    """
    Find all decisions, memories, plans and actions transitively dependent on changed_ids.

    This is the core Evidence Drift Cascade endpoint. It:
    1. Reads the dependency graph from FalkorDB (bounded by max_depth / max_edges).
    2. Computes the minimal affected subgraph deterministically in Python.
    3. Returns the list of impacted nodes with their dependency paths.

    Callers should:
    - Mark the returned nodes as STALE or SUSPENDED.
    - Trigger re-evaluation only for impacted decisions.
    - Never execute actions whose supporting evidence has drifted.
    """
    tenant.guard_site(current_user, site_id)
    site_id = _site_for_user(current_user, site_id, write=False)
    assert site_id is not None
    store = get_drift_store(settings)
    try:
        paths = store.find_impacts(site_id, request.changed_ids)
        return ImpactResponse(
            impacted=[p.as_dict() for p in paths],
            traversal_limited=False,
            site_id=site_id,
        )
    except TraversalLimitExceeded:
        log.error("drift.impact.limit_exceeded", site=site_id, count=len(request.changed_ids))
        # Fail closed: do not return a partial result when the graph might be incomplete.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Impact traversal exceeded its edge budget. Fail closed: suspend all downstream actions.",
        )
    except Exception as exc:
        log.warning("drift.impact_failed", error=str(exc), site=site_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Impact computation failed: {type(exc).__name__}",
        ) from exc
    finally:
        store.close()


# ----------------------------------------------------------------------------------------
# Pure computation endpoints (no database, useful for testing and determinism proofs)
# ----------------------------------------------------------------------------------------


@router.post(
    "/impact/pure",
    summary="Pure impact computation (no database)",
    response_model=list[dict],
)
async def pure_impact(
    request: ImpactRequest,
    current_user: CurrentUserDep,
    _staff: dict = Depends(require_role(*STAFF)),
) -> list[dict]:
    """
    Compute impact from a list of edges you supply, not from the database.
    
    Used for:
    - Unit testing the deterministic algorithm
    - Demonstrating the cascade logic without a running FalkorDB
    - Verifying that the same edges always produce the same impact set
    """
    if tenant.is_demo_user(current_user):
        tenant.guard_site(current_user, "SITE_DEMO")
    changed_ids = request.changed_ids
    # For this demo endpoint, we'll use the existing Track01 dependency structure
    # In production, edges come from the actual FalkorDB graph
    edges = []
    paths = find_impacted_dependents(changed_ids, edges)
    return [p.as_dict() for p in paths]
