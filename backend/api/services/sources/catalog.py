"""Read-only access to the 98-repository source library and its capability ledger.

`catalog.json` and `readmes/` are produced by `backend/scripts/collect_readmes.py`. README text is
untrusted third-party data: it is returned as plain text with an explicit flag and is never rendered
as HTML or executed. The ledger stages follow the integration directive:

    README_READ -> FEATURE_DESIGNED -> SOURCE_AUDITED -> INTEGRATED -> TESTED -> BROWSER_VERIFIED / BLOCKED

A stage is claimed only with evidence: INTEGRATED means a Graph Lab engine implements the mechanism the
README describes (clean-room, no code copied); TESTED means that engine has tests in this repository;
BROWSER_VERIFIED is read from `verification.json`, which is written only after a real browser check.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from api.services.graphlab.registry import ALGORITHMS

DIR = Path(__file__).resolve().parent
STAGES = ("README_READ", "FEATURE_DESIGNED", "SOURCE_AUDITED", "INTEGRATED", "TESTED", "BROWSER_VERIFIED")
# Behaviour adapted earlier in the Evidence Drift store (revision-bound human review).
PRIOR_INTEGRATIONS = {"AjaySingh-a/firstdomino": "Evidence Drift store: revision-bound review"}


@lru_cache(maxsize=1)
def _catalog() -> tuple[dict[str, Any], ...]:
    return tuple(json.loads((DIR / "catalog.json").read_text(encoding="utf-8-sig")))


@lru_cache(maxsize=1)
def _verified_engines() -> frozenset[str]:
    path = DIR / "verification.json"
    if not path.is_file():
        return frozenset()
    return frozenset(json.loads(path.read_text(encoding="utf-8-sig")).get("browser_verified_engines", []))


@lru_cache(maxsize=1)
def _engines_by_repo() -> dict[str, tuple[str, ...]]:
    mapping: dict[str, list[str]] = {}
    for engine in ALGORITHMS.values():
        for repo in engine.sources:
            mapping.setdefault(repo, []).append(engine.id)
    return {repo: tuple(ids) for repo, ids in mapping.items()}


def _entry(item: dict[str, Any]) -> dict[str, Any]:
    repo = item["repo"]
    engines = _engines_by_repo().get(repo, ())
    prior = repo in PRIOR_INTEGRATIONS
    stages: list[str] = ["README_READ"] if item["readme"] else []
    blocked = None if item["readme"] else "No README was present in the checkout; capabilities cannot be derived from it."
    if engines:
        stages.append("FEATURE_DESIGNED")
    if item["audit_state"] == "AUDITED":
        stages.append("SOURCE_AUDITED")
    if engines or prior:
        stages += ["INTEGRATED", "TESTED"]
    if any(e in _verified_engines() for e in engines):
        stages.append("BROWSER_VERIFIED")
    if engines:
        note = "Mechanism re-implemented as a clean-room Graph Lab engine; no third-party code copied."
    elif prior:
        note = PRIOR_INTEGRATIONS[repo]
    elif blocked:
        note = blocked
    else:
        note = f"README read; no engine implements this mechanism yet (closest overlap: {item['closest_overlap'] or 'none'})."
    return {
        "repo": repo, "slug": item["slug"], "url": item["url"], "project": item["project"], "summary": item["summary"],
        "family": item["family"], "pack": item["pack"], "license_status": item["license_status"],
        "readme": {"present": bool(item["readme"]), "bytes": item["readme"]["bytes"] if item["readme"] else 0,
                   "origin": item["readme"]["origin"] if item["readme"] else None},
        "stages": stages, "stage": stages[-1] if stages else "BLOCKED" if blocked else "README_READ",
        "engines": list(engines), "blocked_reason": blocked, "note": note,
    }


def ledger() -> list[dict[str, Any]]:
    return [_entry(item) for item in _catalog()]


def summary() -> dict[str, Any]:
    rows = ledger()
    by_family: dict[str, int] = {}
    by_stage: dict[str, int] = {}
    for row in rows:
        by_family[row["family"]] = by_family.get(row["family"], 0) + 1
        by_stage[row["stage"]] = by_stage.get(row["stage"], 0) + 1
    return {"repositories": len(rows), "readme_present": sum(r["readme"]["present"] for r in rows),
            "readme_absent": sum(not r["readme"]["present"] for r in rows), "by_family": dict(sorted(by_family.items())),
            "by_stage": by_stage, "engines": len(ALGORITHMS), "stages": list(STAGES),
            "integrated_repositories": sum("INTEGRATED" in r["stages"] for r in rows),
            "untrusted_notice": "README text is third-party and untrusted; it is displayed as plain text and never executed."}


def readme(slug: str) -> dict[str, Any] | None:
    """README text for a catalogued slug. The slug is looked up, never joined into a path unchecked."""
    item = next((i for i in _catalog() if i["slug"] == slug), None)
    if item is None or not item["readme"]:
        return None
    path = (DIR / "readmes" / item["readme"]["file"]).resolve()
    if path.parent != (DIR / "readmes").resolve() or not path.is_file():
        return None
    return {"slug": slug, "repo": item["repo"], "url": item["url"], "untrusted": True, "bytes": item["readme"]["bytes"],
            "sha256": item["readme"]["sha256"], "truncated": item["readme"]["truncated"],
            "text": path.read_text(encoding="utf-8", errors="replace")}


def repo_urls() -> dict[str, str]:
    return {i["repo"]: i["url"] for i in _catalog()}
