"""Site scoped, revisioned text evidence intake for the agent memory graph."""
from __future__ import annotations

import hashlib
import json
import threading
from typing import Any
from uuid import UUID

from api.services.drift.engine import ImpactPath
from api.services.drift.model import (
    ContractError, EvidenceStrength, Label, MemoryKind, Rel, Verdict, Verification,
    check_key, now_iso, resolve_authority, stable_hash,
)
from api.services.memory.agent_memory import AgentMemory

MANUAL_AUTHORITY = 5
INTAKE_CONFIDENCE_FLOOR = 0.7
AGENT_ID = "agent:evidence-intake"
_locks_guard = threading.Lock()
_request_locks: dict[tuple[str, str], threading.Lock] = {}


class EvidenceIntakeConflict(RuntimeError):
    """The reviewed evidence or request identity changed before import."""


def _lock(site: str, request_id: str) -> threading.Lock:
    with _locks_guard:
        return _request_locks.setdefault((site, request_id), threading.Lock())


def _ids(request_id: UUID) -> dict[str, str]:
    suffix = request_id.hex
    return {
        "source_id": f"intake:source:{suffix}",
        "document_id": f"intake:document:{suffix}",
        "memory_id": f"intake:memory:{suffix}",
        "request_node_id": f"intake:request:{suffix}",
        "change_id": f"intake:change:{suffix}",
    }


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _impact_revision(mem: AgentMemory, source_id: str) -> tuple[str, list[dict[str, Any]]]:
    """Hash the current source and all traversed dependants for compare-and-set import."""
    source = mem._need(Label.SOURCE_VERSION, source_id)
    paths: list[ImpactPath] = mem.store.find_impacts(mem.site, [source_id])
    state: list[dict[str, Any]] = [{"id": source_id, "label": "SourceVersion", "properties": source["props"]}]
    affected: list[dict[str, Any]] = []
    for path in paths:
        node = mem.store.read_node(mem.site, path.node_id)
        if not node or node["labels"][0] == Label.DECISION_REVISION.value:
            continue
        props = node["properties"]
        state.append({"id": path.node_id, "label": node["labels"][0], "properties": props, "path": list(path.path)})
        affected.append({"id": path.node_id, "label": node["labels"][0], "status": props.get("status", "UNKNOWN"),
                         "depth": path.depth, "via": list(path.path),
                         "summary": props.get("summary") or props.get("fact_key") or ""})
    state.sort(key=lambda row: (row["label"], row["id"]))
    return stable_hash(state), affected


def _fingerprint(body: dict[str, Any]) -> str:
    stable = {k: body.get(k) for k in ("title", "version_label", "content", "claims", "supersedes_source_id", "human_verified")}
    return stable_hash(stable)


def _prepared(mem: AgentMemory, body: dict[str, Any]) -> dict[str, Any]:
    keys = [check_key(claim["fact_key"]) for claim in body["claims"]]
    if len(keys) != len(set(keys)):
        raise ContractError("each source claim must use a distinct fact key")
    ids = _ids(body["request_id"])
    content_hash = _content_hash(body["content"])
    old_id = body.get("supersedes_source_id")
    impact = None
    expected_hash = expected_revision = None
    verdict = Verdict.IMPORT.value
    if old_id:
        old = mem._need(Label.SOURCE_VERSION, old_id)["props"]
        expected_revision, impacted = _impact_revision(mem, old_id)
        expected_hash = old.get("content_sha256")
        incumbent = EvidenceStrength(int(old.get("authority_level", 3)), old.get("verification_status", Verification.UNVERIFIED.value), float(old.get("confidence", 0)))
        challenger = EvidenceStrength(MANUAL_AUTHORITY, Verification.VERIFIED.value if body.get("human_verified") else Verification.UNVERIFIED.value, INTAKE_CONFIDENCE_FLOOR)
        verdict = (Verdict.REJECT.value if old.get("status") != "ACTIVE" else
                   Verdict.CONTEST.value if not body.get("human_verified") else resolve_authority(incumbent, challenger).value)
        impact = {"source_id": old_id, "would_mark_stale": impacted, "read_only": True}
    claims = body["claims"]
    return {
        "read_only": True, "request_id": str(body["request_id"]), "content_sha256": content_hash,
        **ids, "claim_ids": [f"{ids['source_id']}:claim:{index + 1}" for index in range(len(claims))],
        "verification_status": Verification.VERIFIED.value if body.get("human_verified") else Verification.UNVERIFIED.value,
        "authority_level": MANUAL_AUTHORITY, "confidence": INTAKE_CONFIDENCE_FLOOR,
        "confidence_basis": "intake minimum gate; confidence was not measured", "supersedes_source_id": old_id,
        "expected_source_hash": expected_hash, "expected_source_revision": expected_revision,
        "verdict": verdict, "impact": impact,
    }


def preview(mem: AgentMemory, body: dict[str, Any]) -> dict[str, Any]:
    """Read-only preview. No graph nodes or edges are written."""
    return _prepared(mem, body)


def _write_claims(mem: AgentMemory, body: dict[str, Any], prepared: dict[str, Any], *, verification: str,
                  old_claims: dict[str, str] | None = None) -> list[str]:
    old_claims = old_claims or {}
    for index, claim in enumerate(body["claims"]):
        claim_id = prepared["claim_ids"][index]
        mem.record_claim(claim_id=claim_id, source_id=prepared["source_id"], fact_key=claim["fact_key"],
                         fact_value=claim["fact_value"], authority_level=MANUAL_AUTHORITY, confidence=INTAKE_CONFIDENCE_FLOOR,
                         verification=verification)
        previous = old_claims.get(claim["fact_key"])
        if previous:
            mem.store.link(mem.site, Label.CLAIM, claim_id, Rel.CONTRADICTS, Label.CLAIM, previous)
    return prepared["claim_ids"]


def import_evidence(mem: AgentMemory, body: dict[str, Any]) -> dict[str, Any]:
    """Import a new immutable version, rejecting stale previews and replaying idempotently."""
    request_id = str(body["request_id"])
    with _lock(mem.site, request_id):
        ids = _ids(body["request_id"])
        fingerprint = _fingerprint(body)
        prior = mem.store.read_node(mem.site, ids["request_node_id"])
        if prior:
            props = prior["properties"]
            if props.get("payload_fingerprint") != fingerprint:
                raise EvidenceIntakeConflict("This request ID was already used with different evidence.")
            result = json.loads(props.get("result_json", "{}"))
            if result:
                return {**result, "duplicate": True}
            raise EvidenceIntakeConflict("This request is already being processed; refresh the graph before retrying.")

        prepared = _prepared(mem, body)
        if prepared["verdict"] == Verdict.REJECT.value:
            raise ContractError("The selected source version is not active or the evidence did not pass the authority checks.")
        old_id = body.get("supersedes_source_id")
        verification = prepared["verification_status"]
        invalidated: list[dict[str, Any]] = []
        verdict = prepared["verdict"]
        old_claims: dict[str, str] = {}

        if old_id:
            if not body.get("expected_source_revision"):
                raise ContractError("Preview this source revision before importing it.")
            if body.get("expected_source_hash") != prepared["expected_source_hash"] or body.get("expected_source_revision") != prepared["expected_source_revision"]:
                raise EvidenceIntakeConflict("Evidence or its dependencies changed after preview. Refresh and review the impact again.")
            for path in mem.store.find_impacts(mem.site, [old_id]):
                node = mem.store.read_node(mem.site, path.node_id)
                if node and node["labels"][0] == Label.CLAIM.value:
                    fact_key = node["properties"].get("fact_key")
                    if fact_key:
                        old_claims[fact_key] = path.node_id

        source = {"document_id": prepared["document_id"], "source_id": prepared["source_id"], "title": body["title"],
                  "authority_level": MANUAL_AUTHORITY, "confidence": INTAKE_CONFIDENCE_FLOOR, "version_label": body["version_label"],
                  "content_sha256": prepared["content_sha256"], "extra": {"content_excerpt": body["content"][:1000], "intake_request_id": request_id,
                  "confidence_basis": "intake minimum gate; confidence was not measured",
                  **({"reviewed_by": body.get("reviewed_by", "unknown")} if body.get("human_verified") else {})}}
        if old_id and verdict == Verdict.REPLACE:
            claims = [{"claim_id": prepared["claim_ids"][i], "fact_key": claim["fact_key"], "fact_value": claim["fact_value"],
                       "replaces": old_claims.get(claim["fact_key"])} for i, claim in enumerate(body["claims"])]
            cascade = mem.supersede_source(old_source_id=old_id, new_source={**source, "verification": verification},
                                           new_claims=claims, change_id=ids["change_id"], reason=f"Imported {body['title']} {body['version_label']}.")
            invalidated = cascade.get("invalidated", [])
        else:
            mem.record_source(**source, verification=verification)
            _write_claims(mem, body, prepared, verification=verification, old_claims=old_claims if old_id else None)
            if old_id:
                mem.store.link(mem.site, Label.SOURCE_VERSION, prepared["source_id"], Rel.CONTRADICTS, Label.SOURCE_VERSION, old_id)

        mem.store.update_node_properties(mem.site, Label.DOCUMENT, prepared["document_id"], {"content": body["content"]})
        claim_ids = prepared["claim_ids"]
        mem.register_agent(AGENT_ID, "Evidence intake", specialty="human-reviewed evidence capture", system="kairos")
        remembered = mem.remember(memory_id=prepared["memory_id"], agent_id=AGENT_ID, kind=MemoryKind.EPISODIC.value,
                                  summary=f"{body['title']} ({body['version_label']}): {body['content'][:350]}", claim_ids=claim_ids,
                                  investigation_ref=f"evidence-intake:{request_id}", details={"content_sha256": prepared["content_sha256"],
                                  "verification_status": verification, "supersedes_source_id": old_id or "",
                                  **({"reviewed_by": body.get("reviewed_by", "unknown")} if body.get("human_verified") else {})})
        at = now_iso()
        mem.store.upsert_node(mem.site, Label.CHANGE, ids["request_node_id"], {
            "request_id": request_id, "payload_fingerprint": fingerprint, "source_id": prepared["source_id"],
            "verdict": verdict, "observed_at": at, "reason": f"Evidence intake: {body['title']} {body['version_label']}",
            "result_json": "{}",
        })
        result = {**prepared, "read_only": False, "imported": True, "duplicate": False, "observed_at": at,
                  "verified": remembered["verified"], "invalidated": invalidated,
                  "note": ("Source and downstream records were revised." if verdict == Verdict.REPLACE else
                           "Evidence was stored without changing the prior source or its dependent decisions." if old_id else
                           "New source and claims were added to the site graph."),
                  "impact": prepared["impact"]}
        mem.store.update_node_properties(mem.site, Label.CHANGE, ids["request_node_id"], {"result_json": json.dumps(result, sort_keys=True)})
        return result
