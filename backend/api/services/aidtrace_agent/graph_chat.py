"""Bounded, read-only graph answers when model reasoning is unavailable.

This is explicitly a deterministic graph assistant, not a simulated model response.
Only identifiers in the current tool result can be selected or cited.
"""
from __future__ import annotations

import re
from typing import Any

from .tools import execute


def answer(question: str, memory: Any) -> dict[str, Any]:
    q = question.lower()
    def mentions(record: dict[str, Any]) -> bool:
        identifier = record.get("id")
        return bool(identifier and re.search(r"(?<![\w.:-])" + re.escape(str(identifier).lower()) + r"(?![\w.:-])", q))
    trail: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    citations: set[str] = set()

    def read(name: str, args: dict[str, Any]) -> dict[str, Any]:
        result = execute(name, args, memory)
        trail.append({"tool": name, "ok": result["ok"], "error": result.get("error")})
        if result["ok"]:
            evidence.append({"tool": name, "result": result["data"]})
            citations.update(result["source_ids"])
        return result

    def finish(status: str, finding: str, why: str = "", next_step: str = "") -> dict[str, Any]:
        return {"status": status, "answered_by": "graph", "model": "graph-only", "question": question,
                "message": finding, "tool_calls": trail, "evidence": evidence,
                "answer": {"finding": finding, "why": why, "next_step": next_step,
                           "affected": [], "citations": sorted(citations)} if status == "answered" else None}

    help_text = "Ask for the site's decisions, actions, memories, or handoffs. Include a source ID for an impact preview, or an action ID to check approval eligibility."
    if not any(word in q for word in ("graph", "decision", "action", "memor", "source", "handoff", "approv", "evidence", "impact", "stale")):
        return finish("unsupported", "Graph mode supports specific evidence questions. General conversation requires a configured model. " + help_text)
    snapshot = read("get_memory_snapshot", {"limit": 25})
    if not snapshot["ok"]:
        return finish("graph_unavailable", "The site graph could not be read. Restore the graph connection and retry; no evidence answer was generated.")
    if snapshot.get("truncated"):
        return finish("limited", "The graph response exceeds the read limit. Use the workspace to inspect a narrower set of records.")
    data = snapshot["data"]
    tool = None
    args: dict[str, Any] = {}
    if "handoff" in q:
        tool, args = "get_agent_handoffs", {"limit": 25}
    elif any(word in q for word in ("impact", "revise", "change", "supersed")):
        source = next((s for s in data["sources"]["shown"] if mentions(s)), None)
        if source:
            tool, args = "get_graph_impact", {"source_id": source["id"]}
        else:
            return finish("answered", "Choose a source ID for an impact preview.", "Available source IDs: " + ", ".join(str(s["id"]) for s in data["sources"]["shown"] if s.get("id")), help_text)
    elif "eligible" in q or "eligibility" in q or "approv" in q:
        action = next((a for a in data["actions"]["shown"] if mentions(a)), None)
        if action:
            tool, args = "get_action_eligibility", {"action_id": action["id"]}
    if tool:
        result = read(tool, args)
        if not result["ok"]:
            return finish("graph_unavailable", "The requested evidence lookup failed. Retry after checking the graph connection.")
        payload = result["data"]
        if tool == "get_agent_handoffs":
            finding = f"{payload['total']} agent handoffs recorded; showing {len(payload['shown'])}."
        elif tool == "get_graph_impact":
            finding = f"Revising {args['source_id']} would mark {payload['total_would_mark_stale']} dependent records stale. This preview changes nothing."
        else:
            finding = f"Action {args['action_id']} is {'eligible' if payload.get('eligible') else 'not eligible'} for approval."
        return finish("answered", finding, "Inspect the evidence lookup below for current record details.", "Review the underlying records before acting.")
    totals = ", ".join(f"{data[key]['total']} {key}" for key in ("memories", "decisions", "actions", "sources"))
    rows = [f"{row.get('id', 'Unknown ID')}: {row.get('summary') or row.get('title') or row.get('status', 'Details in evidence')}"
            for key in ("decisions", "actions", "memories") for row in data[key]["shown"][:5]]
    return finish("answered", "The current site graph contains " + totals + ".", "\n".join(rows) or "No decisions, actions, or memories have been recorded yet.", help_text)
