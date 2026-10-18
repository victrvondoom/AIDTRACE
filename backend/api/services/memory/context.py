"""Bounded, provenance-bearing context from a verified FalkorDB memory recall.

The caller supplies the result of ``AgentMemory.recall(verified_only=True)`` so
the graph records exactly which memories were made available to the agent.
These records are retrieved evidence, never instructions or final findings.
"""
from __future__ import annotations

import json
from typing import Any

from api.services.drift.model import ContractError, Verification

MAX_CONTEXT_BYTES = 24_000
MAX_LINEAGE_ITEMS = 200


def build_llm_context(recall: dict[str, Any], *, fact_key: str) -> dict[str, Any]:
    """Keep source-version and claim IDs attached to every usable memory."""
    entries: list[dict[str, Any]] = []
    lineage_items = 0
    for memory in recall["usable"]:
        if memory.get("verification_status") != Verification.VERIFIED.value:
            raise ContractError("unverified memory cannot enter factual LLM context")
        claims = memory["claims"]
        sources = memory["sources"]
        lineage_items += len(claims) + len(sources)
        if lineage_items > MAX_LINEAGE_ITEMS:
            raise ContractError("memory context exceeds the lineage budget")
        entries.append({
            "memory_id": memory["id"],
            "kind": memory.get("memory_kind"),
            "summary": memory.get("summary", ""),
            "confidence": memory.get("confidence"),
            "recorded_at": memory.get("recorded_at"),
            "verification_status": memory["verification_status"],
            "claims": [{"id": c["id"], "fact_key": c["fact_key"], "fact_value": c["fact_value"]} for c in claims],
            "source_versions": [{"id": s["id"], "document_id": s["document_id"], "content_sha256": s["content_sha256"]} for s in sources],
        })
    output = {
        "context_type": "untrusted_graph_memory",
        "agent_id": recall["agent_id"],
        "fact_key": fact_key,
        "recall_session_id": recall["session_id"],
        "entries": entries,
        "blocked": [{"memory_id": m["id"], "reason": m["blocked_reason"]} for m in recall["blocked"]],
        "influenced_by": recall["influenced_by"],
    }
    if len(json.dumps(output, ensure_ascii=False, default=str).encode("utf-8")) > MAX_CONTEXT_BYTES:
        raise ContractError("memory context exceeds the response budget")
    return output
