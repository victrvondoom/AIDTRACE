"""Record a ResolveAI investigation as evidence-backed agent memory, so another agent can recall it later.

ResolveAI's worker returns retrieved, scored passages from its indexed corpora. Each passage becomes a source version (identified by the
hash of the retrieved text, so two copies of one passage are one source), each source supports a claim ("this document bears on this
case"), and one EPISODIC memory summarises the investigation and points at those claims. If any source is later superseded, the memory
and everything built on it goes stale through the same cascade as every other memory.

Nothing here claims the passages prove anything about the case: they are retrieved reference material, and the memory says so.
"""
from __future__ import annotations

import re
from typing import Any

from api.services.drift.model import Verification, stable_hash
from api.services.memory.agent_memory import AgentMemory, _slug

AGENT = "agent:resolveai-investigator"
MAX_EVIDENCE = 8


def _authority_level(evidence: dict[str, Any]) -> int:
    """Map the worker's authority score onto Kairos's 1 (strongest) to 5 scale."""
    score = float((evidence.get("evidence_scores") or {}).get("authority_score", 0.5))
    return 1 if score >= 0.95 else 2 if score >= 0.8 else 3 if score >= 0.6 else 4


def remember_investigation(mem: AgentMemory, *, case_id: str, institution: str, domain: str, investigation: dict[str, Any]) -> dict[str, Any]:
    evidence = [e for e in investigation.get("evidence", []) if e.get("retrieved_chunk")][:MAX_EVIDENCE]
    if not evidence:
        return {"remembered": False, "reason": "The investigation retrieved no evidence, so there is nothing to remember."}
    cid = _slug(case_id)
    mem.register_agent(AGENT, "ResolveAI investigator", specialty=f"{domain} case investigation", system="resolveai")
    claim_ids: list[str] = []
    seen: set[str] = set()
    for e in evidence:
        digest = stable_hash(re.sub(r"\s+", " ", e["retrieved_chunk"]).strip())
        if digest in seen:
            continue  # a repeated passage is one source, not corroboration
        seen.add(digest)
        known = str(e.get("authority", "")).strip().lower() not in ("", "unknown")
        verification = Verification.VERIFIED.value if known else Verification.UNVERIFIED.value
        confidence = min(0.99, max(0.05, float(e.get("confidence", 0.5))))
        source_id = f"ra:src:{digest[:20]}"
        mem.record_source(document_id=f"ra:doc:{_slug(str(e.get('title') or digest[:12]))}", source_id=source_id, title=str(e.get("title") or "Untitled source")[:120],
                          authority_level=_authority_level(e), confidence=confidence, verification=verification, content_sha256=digest,
                          extra={"authority": str(e.get("authority", "unknown"))[:80], "worker_chunk_id": str(e.get("chunk_id") or "")[:80]})
        claim_id = f"ra:claim:{cid}:{digest[:12]}"
        mem.record_claim(claim_id=claim_id, source_id=source_id, fact_key=f"evidence_for_case:{cid}", fact_value=str(e.get("title") or "source")[:120],
                         authority_level=_authority_level(e), confidence=confidence, verification=verification)
        claim_ids.append(claim_id)
    memory_id = f"ra:mem:{cid}:{stable_hash(claim_ids)[:8]}"
    titles = ", ".join(sorted({str(e.get("title"))[:50] for e in evidence}))[:300]
    out = mem.remember(memory_id=memory_id, agent_id=AGENT, kind="EPISODIC", claim_ids=claim_ids, investigation_ref=f"resolveai:{case_id}",
                       summary=f"Retrieved {len(claim_ids)} reference passage(s) for a {domain} dispute with {institution}: {titles}. Reference material only; not a finding about the case.",
                       details={"case_id": case_id, "mode": investigation.get("mode"), "llm_used": bool(investigation.get("llm_used"))})
    return {"remembered": True, "memory_id": memory_id, "claims": claim_ids, "independent_sources": out["independent_sources"], "verified": out["verified"]}
