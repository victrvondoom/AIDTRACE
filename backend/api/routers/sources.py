"""Source library routes: the 98 research repositories, their READMEs and the capability ledger."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.dependencies import require_role
from api.services.sources import catalog

router = APIRouter()
STAFF = ("engineer", "reliability", "admin")


@router.get("/summary", summary="Counts by family, ledger stage and README availability")
async def sources_summary(_staff: dict = Depends(require_role(*STAFF))) -> dict:
    return catalog.summary()


@router.get("/repos", summary="Search the repository ledger")
async def list_repos(
    family: str | None = Query(None, max_length=80),
    stage: str | None = Query(None, max_length=24),
    engine: str | None = Query(None, max_length=40),
    q: str | None = Query(None, max_length=80),
    limit: int = Query(120, ge=1, le=200),
    offset: int = Query(0, ge=0, le=1000),
    _staff: dict = Depends(require_role(*STAFF)),
) -> dict:
    rows = catalog.ledger()
    needle = (q or "").strip().lower()
    rows = [r for r in rows
            if (not family or r["family"] == family) and (not stage or r["stage"] == stage or stage in r["stages"])
            and (not engine or engine in r["engines"])
            and (not needle or needle in f"{r['repo']} {r['project']} {r['summary']}".lower())]
    return {"total": len(rows), "items": rows[offset:offset + limit]}


@router.get("/readme", summary="Third-party README text (untrusted, plain text)")
async def get_readme(slug: str = Query(pattern=r"^[A-Za-z0-9_.-]+__[A-Za-z0-9_.-]+$", max_length=160),
                     _staff: dict = Depends(require_role(*STAFF))) -> dict:
    found = catalog.readme(slug)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No README is recorded for this repository.")
    return found


@router.get("/ledger", summary="Machine-readable capability ledger for all repositories")
async def get_ledger(_staff: dict = Depends(require_role(*STAFF))) -> dict:
    return {"stages": list(catalog.STAGES) + ["BLOCKED"], "items": catalog.ledger()}
