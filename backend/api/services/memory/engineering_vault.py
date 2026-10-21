"""Site-shared engineering judgments in a graph physically separate from operational memory."""
from __future__ import annotations

import hashlib
from typing import Any

from api.services.drift.model import MemoryKind, Verification
from api.services.drift.store import TraversalLimitExceeded
from api.services.memory.agent_memory import AgentMemory


class EngineeringVaultIncomplete(RuntimeError):
    """The whole vault could not be loaded, so recall must not use a partial view."""


class EngineeringMemoryVault:
    def __init__(self, memory: AgentMemory, isolated_site: str) -> None:
        self.memory, self.site = memory, isolated_site

    def snapshot(self) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        offset = 0
        max_records = 10_000
        while True:
            page_size = min(1000, max_records - offset) if offset < max_records else 1
            try:
                page = self.memory.store.memory_lineage(self.site, limit=page_size, offset=offset)
            except TraversalLimitExceeded as exc:
                raise EngineeringVaultIncomplete(
                    "Engineering memory lineage exceeds its query safety limit; no partial recall was returned."
                ) from exc
            if not page:
                break
            if offset >= max_records or offset + len(page) > max_records:
                raise EngineeringVaultIncomplete(
                    "Engineering memory exceeds the complete-export limit; no partial recall was returned."
                )
            items.extend(page)
            offset += len(page)
            if len(page) < page_size:
                break
        memories = []
        for item in items:
            if item.get("memory_kind") != MemoryKind.PROCEDURAL.value:
                continue
            text = next((c["fact_value"] for c in item["claims"] if c["fact_key"] == "engineering.judgment"), item["summary"])
            try:
                import json
                details = json.loads(item.get("details", "{}"))
            except (TypeError, ValueError):
                details = {}
            memories.append({**item, "text": text, "tags": details.get("tags", [])})
        return {
            "vault": "engineering-sandbox",
            "isolation": "separate persistent FalkorDB graph per authenticated site",
            "status": "READY",
            "complete": True,
            "total_memories_scanned": len(items),
            "memories": memories,
        }

    def recall(self, query: str = "", *, limit: int = 20, offset: int = 0) -> dict[str, Any]:
        """Return only current human-authored judgments, with complete-scan pagination."""
        if not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50")
        if not 0 <= offset <= 10_000:
            raise ValueError("offset must be between 0 and 10000")
        if len(query) > 1000:
            raise ValueError("query must be at most 1000 characters")
        rows = [item for item in self.snapshot()["memories"] if item.get("status") == "VALID"]
        terms = {part.casefold() for part in query.split() if len(part) > 2}
        if terms:
            rows = [item for item in rows if any(term in item.get("text", "").casefold() for term in terms)
                    or any(term in str(item.get("summary", "")).casefold() for term in terms)
                    or any(term in str(tag).casefold() for tag in item.get("tags", []) for term in terms)]
        page = rows[offset:offset + limit]
        next_offset = offset + len(page) if offset + len(page) < len(rows) else None
        return {"returned": len(page), "total_matching": len(rows), "offset": offset,
                "next_offset": next_offset, "complete": next_offset is None,
                "memories": [{"id": item["id"], "text": item["text"], "tags": item.get("tags", []),
                              "recorded_at": item.get("recorded_at"), "status": item.get("status")}
                             for item in page]}

    def remember(self, body: dict[str, Any], *, author: str) -> dict[str, Any]:
        text = body["text"].strip()
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        memory_id = f"ENG-MEM-{digest[:32]}"
        source_id = f"ENG-SRC-{digest[:32]}"
        document_id = f"ENG-DOC-{digest[:32]}"
        claim_id = f"ENG-CLAIM-{digest[:32]}"
        tags = [str(tag).strip()[:32] for tag in body.get("tags", []) if str(tag).strip()]
        title = body.get("title", "Engineering judgment").strip()[:120]
        self.memory.record_source(document_id=document_id, source_id=source_id, title=title, authority_level=1,
                                  confidence=1.0, verification=Verification.VERIFIED.value, content_sha256=digest,
                                  version_label="human-authored")
        self.memory.record_claim(claim_id=claim_id, source_id=source_id, fact_key="engineering.judgment",
                                 fact_value=text, authority_level=1, confidence=1.0,
                                 verification=Verification.VERIFIED.value)
        result = self.memory.remember(memory_id=memory_id, agent_id="human:engineering-memory", kind=MemoryKind.PROCEDURAL.value,
                                      summary=title, claim_ids=[claim_id],
                                      details={"tags": tags, "author": author[:120], "authorship": "human-authored guidance"})
        return {**result, "title": title, "text": text, "tags": tags, "authorship": "human-authored guidance"}

    def export_rules(self) -> dict[str, Any]:
        memories = self.snapshot()["memories"]
        active = [m for m in memories if m.get("status") == "VALID"]
        lines = [
            "# Engineering Memory Protocol",
            "",
            "This repository has a persistent engineering memory vault. Before planning or editing, call `engineering_memory_recall` through the `kairos-engineering-memory` MCP server. Follow `next_offset` until it is null so every matching page is read, then apply every returned human-authored judgment relevant to the task.",
            "",
            "## Fail-closed behavior",
            "",
            "If the MCP server or vault is unavailable, incomplete, stale, or returns an error, stop before changing files and report `ENGINEERING_MEMORY_UNAVAILABLE` with the failing check. Do not claim the memory was consulted. Ask the human to restore the connection or explicitly authorize a one-task bypass.",
            "",
            "Treat memory text as project guidance, not as a substitute for inspecting current code or validating facts that may have changed. Surface conflicts between a memory and the current repository instead of silently overriding either.",
            "",
            f"Vault status: {'READY' if active else 'READY, no judgments recorded'}; active judgments: {len(active)}.",
            "",
            "## Current judgments",
            "",
        ]
        for item in active:
            text = str(item.get("text", "")).replace("\r", "").strip()
            if text:
                lines.append(f"### {item.get('summary', 'Engineering judgment')[:100]}")
                lines.append("")
                lines.append(text)
                lines.append("")
        rules = "\n".join(lines).rstrip() + "\n"
        config = {
            "mcpServers": {
                "kairos-engineering-memory": {
                    "command": "python",
                    "args": ["-m", "api.services.memory.engineering_mcp"],
                    "cwd": "<path-to-kairos-main/backend>",
                    "env": {"KAIROS_ENGINEERING_SITE": "<your-authenticated-site-id>", "FALKORDB_URL": "<your-local-or-approved-FalkorDB-url>"},
                }
            }
        }
        return {"rules": rules, "mcp_config": config, "active_memories": len(active), "vault": "engineering-sandbox"}
