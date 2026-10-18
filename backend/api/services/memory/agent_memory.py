"""Evidence-aware agent memory on the Kairos site graph (FalkorDB).

This is the general mechanism behind the Evidence Drift demo: agents record what they concluded, each conclusion points at the
claims and source versions that support it, and when an authoritative source is superseded the dependants are found by graph
traversal, marked stale, and any approval that rested on them stops being usable.

    SourceVersion <-SUPPORTED_BY- Claim <-DERIVED_FROM- Memory <-DEPENDS_ON- Decision <-DEPENDS_ON- Plan <-DEPENDS_ON- ActionProposal
                                                                    Decision -HAS_REVISION-> DecisionRevision <-ON_REVISION- Approval

Rules enforced here, not left to callers:
  * a memory is VALID only while every claim and source behind it is ACTIVE; recall refuses STALE/INVALIDATED memory and
    reports why, so an agent cannot lean on it silently;
  * copies of the same source are not corroboration: independent support is counted by distinct content hash / document;
  * a superseding source must pass the authority check (a weaker or unverified source can only contest, never replace);
  * an approval is bound to the decision revision it reviewed; any later change to the dependency state voids its use;
  * superseding the same change twice has no second effect (idempotent), and only true dependants are touched.
Synchronous (FalkorDB client); call from async routes through asyncio.to_thread.
"""
from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from api.services.drift.model import (
    ActionStatus,
    ContractError,
    DerivedStatus,
    EvidenceStrength,
    Label,
    MemoryKind,
    Rel,
    SourceStatus,
    Verdict,
    Verification,
    evaluate_conditions,
    now_iso,
    parse_conditions,
    resolve_authority,
    stable_hash,
)
from api.services.drift.store import FalkorDriftStore

_STALE_ON_CHANGE = {"Memory": DerivedStatus.STALE.value, "Decision": DerivedStatus.STALE.value, "Plan": DerivedStatus.STALE.value}


def _slug(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._:-" else "_" for ch in value)[:100]


class AgentMemory:
    def __init__(self, store: FalkorDriftStore, site_id: str) -> None:
        self.store, self.site = store, site_id

    # ------------------------------------------------------------------ evidence
    def record_source(self, *, document_id: str, source_id: str, title: str, authority_level: int = 3, confidence: float = 0.9,
                      verification: str = Verification.VERIFIED.value, content_sha256: str | None = None, version_label: str = "v1",
                      observed_at: str | None = None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        at = observed_at or now_iso()
        self.store.upsert_node(self.site, Label.DOCUMENT, document_id, {"title": title})
        self.store.upsert_node(self.site, Label.SOURCE_VERSION, source_id, {
            "title": title, "status": SourceStatus.ACTIVE.value, "authority_level": authority_level, "confidence": confidence,
            "verification_status": verification, "version_label": version_label, "observed_at": at,
            **({"content_sha256": content_sha256} if content_sha256 else {}), **(extra or {}),
        })
        self.store.link(self.site, Label.SOURCE_VERSION, source_id, Rel.VERSION_OF, Label.DOCUMENT, document_id)
        return {"source_id": source_id, "document_id": document_id}

    def record_claim(self, *, claim_id: str, source_id: str, fact_key: str, fact_value: Any, authority_level: int = 3,
                     confidence: float = 0.9, verification: str = Verification.VERIFIED.value) -> dict[str, Any]:
        self.store.upsert_node(self.site, Label.CLAIM, claim_id, {
            "fact_key": fact_key, "fact_value": fact_value, "status": "ACTIVE", "authority_level": authority_level,
            "confidence": confidence, "verification_status": verification, "source_id": source_id,
        })
        self.store.link(self.site, Label.CLAIM, claim_id, Rel.SUPPORTED_BY, Label.SOURCE_VERSION, source_id)
        return {"claim_id": claim_id}

    # ------------------------------------------------------------------ memory
    def register_agent(self, agent_id: str, name: str, *, specialty: str = "", system: str = "kairos") -> None:
        self.store.upsert_node(self.site, Label.AGENT, agent_id, {"name": name, "specialty": specialty, "system": system})

    def remember(self, *, memory_id: str, agent_id: str, kind: str, summary: str, claim_ids: Sequence[str] = (),
                 from_memories: Sequence[str] = (), investigation_ref: str | None = None, details: dict[str, Any] | None = None) -> dict[str, Any]:
        """Store what an agent concluded, tied to the evidence behind it. Refuses to remember from a non-ACTIVE claim."""
        MemoryKind(kind)
        claims = [self._need(Label.CLAIM, c) for c in claim_ids]
        inactive = [c["id"] for c in claims if c["props"].get("status") != "ACTIVE"]
        if inactive:
            raise ContractError(f"cannot remember from claims that are not ACTIVE: {inactive}")
        sources = {c["props"]["source_id"] for c in claims if c["props"].get("source_id")}
        # Independent support: copies of one source (same content hash) count once.
        independent = len({(self.store.read_node(self.site, s) or {"properties": {}})["properties"].get("content_sha256") or s for s in sources})
        verified = bool(claims) and all(c["props"].get("verification_status") == Verification.VERIFIED.value for c in claims)
        at = now_iso()
        session_id = f"session:{_slug(memory_id)}"
        self.store.upsert_node(self.site, Label.AGENT_SESSION, session_id, {"agent_id": agent_id, "investigation_ref": investigation_ref or "", "started_at": at})
        self.store.link(self.site, Label.AGENT, agent_id, Rel.HAS_SESSION, Label.AGENT_SESSION, session_id)
        self.store.upsert_node(self.site, Label.MEMORY, memory_id, {
            "memory_kind": kind, "summary": summary[:500], "agent_id": agent_id, "status": DerivedStatus.VALID.value,
            "verification_status": Verification.VERIFIED.value if verified else Verification.UNVERIFIED.value,
            "confidence": min([c["props"].get("confidence", 0.0) for c in claims], default=0.0),
            "independent_sources": independent, "recorded_at": at, "last_verified_at": at,
            "investigation_ref": investigation_ref or "", **({"details": json.dumps(details, sort_keys=True)[:2000]} if details else {}),
        })
        self.store.link(self.site, Label.AGENT_SESSION, session_id, Rel.PRODUCED, Label.MEMORY, memory_id)
        for c in claims:
            self.store.link(self.site, Label.MEMORY, memory_id, Rel.DERIVED_FROM, Label.CLAIM, c["id"])
        for m in from_memories:
            self._need(Label.MEMORY, m)
            self.store.link(self.site, Label.MEMORY, memory_id, Rel.DERIVED_FROM, Label.MEMORY, m)
        return {"memory_id": memory_id, "status": DerivedStatus.VALID.value, "independent_sources": independent, "verified": verified}

    def recall(self, *, agent_id: str, fact_key: str | None = None, memory_ids: Sequence[str] | None = None, limit: int = 10) -> dict[str, Any]:
        """Memories another agent may use now. STALE/INVALIDATED ones are returned as `blocked` with the reason, never as usable."""
        if not 1 <= limit <= 50:
            raise ContractError("limit must be between 1 and 50")
        rows = self.store.memory_lineage(self.site, limit=200)
        if memory_ids is not None:
            rows = [r for r in rows if r["id"] in set(memory_ids)]
        if fact_key is not None:
            rows = [r for r in rows if any(c["fact_key"] == fact_key for c in r["claims"])]
        rows.sort(key=lambda r: r.get("recorded_at", ""), reverse=True)
        usable, blocked = [], []
        for row in rows:
            reason = self._block_reason(row)
            (blocked if reason else usable).append({**row, "blocked_reason": reason} if reason else row)
        usable = usable[:limit]
        session_id = f"recall:{_slug(agent_id)}:{stable_hash([u['id'] for u in usable] + [fact_key or ''])[:12]}"
        self.store.upsert_node(self.site, Label.AGENT_SESSION, session_id, {"agent_id": agent_id, "kind": "recall", "started_at": now_iso()})
        for u in usable:
            self.store.link(self.site, Label.MEMORY, u["id"], Rel.RECALLED_IN, Label.AGENT_SESSION, session_id)
        return {"agent_id": agent_id, "session_id": session_id, "usable": usable, "blocked": blocked[:limit], "influenced_by": [u["id"] for u in usable]}

    @staticmethod
    def _block_reason(row: dict[str, Any]) -> str | None:
        if row.get("status") != DerivedStatus.VALID.value:
            return f"memory is {row.get('status')}"
        for c in row["claims"]:
            if c["status"] != "ACTIVE":
                return f"claim {c['id']} is {c['status']}"
        for s in row["sources"]:
            if s["status"] != SourceStatus.ACTIVE.value:
                return f"source {s['id']} is {s['status']}"
        return None

    # ------------------------------------------------------------------ decisions and approval
    def _need(self, label: Label, node_id: str) -> dict[str, Any]:
        node = self.store.read_node(self.site, node_id)
        if not node or label.value not in node["labels"]:
            raise ContractError(f"{label.value} '{node_id}' does not exist in this site's graph")
        return {"id": node_id, "props": node["properties"]}

    def _label_of(self, node_id: str) -> Label:
        node = self.store.read_node(self.site, node_id)
        return Label.MEMORY if node and node["labels"][:1] == ["Memory"] else Label.CLAIM

    def propose_decision(self, *, decision_id: str, summary: str, memory_ids: Sequence[str], claim_ids: Sequence[str] = (),
                         conditions: list[dict[str, Any]], plan_id: str, plan_summary: str, action_id: str, action_summary: str,
                         actor: str = "kairos") -> dict[str, Any]:
        for m in memory_ids:
            self._need(Label.MEMORY, m)
        for c in claim_ids:
            self._need(Label.CLAIM, c)
        conds = parse_conditions(conditions)
        conds_json = json.dumps([c.as_dict() for c in conds], sort_keys=True)
        deps = [*memory_ids, *claim_ids]
        self.store.upsert_node(self.site, Label.DECISION, decision_id, {"summary": summary[:500], "status": DerivedStatus.VALID.value, "revision_n": 0, "conditions": conds_json, "proposed_by": actor})
        for m in memory_ids:
            self.store.link(self.site, Label.DECISION, decision_id, Rel.DEPENDS_ON, Label.MEMORY, m)
        for c in claim_ids:
            self.store.link(self.site, Label.DECISION, decision_id, Rel.DEPENDS_ON, Label.CLAIM, c)
        self.store.upsert_node(self.site, Label.PLAN, plan_id, {"summary": plan_summary[:300], "status": DerivedStatus.VALID.value})
        self.store.link(self.site, Label.PLAN, plan_id, Rel.DEPENDS_ON, Label.DECISION, decision_id)
        self.store.upsert_node(self.site, Label.ACTION, action_id, {"summary": action_summary[:300], "status": ActionStatus.PENDING.value, "requires_human_approval": True})
        self.store.link(self.site, Label.ACTION, action_id, Rel.DEPENDS_ON, Label.PLAN, plan_id)
        self.store.link(self.site, Label.ACTION, action_id, Rel.REQUIRES_APPROVAL, Label.DECISION, decision_id)
        revision = self._append_revision(decision_id, deps, DerivedStatus.VALID.value, conds_json, "Initial proposal.")
        return {"decision_id": decision_id, "action_id": action_id, "revision": revision}

    def _head(self, decision_id: str) -> dict[str, Any]:
        node = self._need(Label.DECISION, decision_id)["props"]
        rev_id = node.get("current_revision_id")
        found = self.store.read_node(self.site, rev_id) if rev_id else None
        return {"n": int(node.get("revision_n", 0)), "id": rev_id, "props": found["properties"] if found else {}, "decision": node}

    def _live_hash(self, decision_id: str, dependency_ids: Sequence[str], conditions_json: str) -> str:
        state = []
        for dep in sorted(dependency_ids):
            node = self.store.read_node(self.site, dep)
            props = node["properties"] if node else {}
            state.append([dep, props.get("status", "MISSING"), props.get("fact_value", "")])
        return stable_hash({"decision": decision_id, "conditions": conditions_json, "dependencies": state})

    def _append_revision(self, decision_id: str, deps: Sequence[str], status: str, conds_json: str, reason: str) -> dict[str, Any]:
        head = self._head(decision_id)
        n = head["n"]
        revision = self.store.append_decision_revision(
            self.site, decision_id=decision_id, revision_id=f"{decision_id}:rev:{n + 1}", expected_revision_n=n,
            previous_revision_id=head["id"], graph_revision=self._live_hash(decision_id, deps, conds_json), status=status,
            conditions_json=conds_json, dependency_ids=list(deps), created_at=now_iso(), reason=reason[:300])
        for dep in deps:
            self.store.link(self.site, Label.DECISION_REVISION, revision["revision_id"], Rel.DEPENDS_ON, self._label_of(dep), dep)
        return revision

    def eligibility(self, action_id: str) -> dict[str, Any]:
        """Can this action be approved (or is its approval still usable) right now? Reasons are specific and ordered."""
        self._need(Label.ACTION, action_id)
        edges = self.store.edges_of(self.site, action_id)
        decision_id = next((e["id"] for e in edges["out"] if e["rel"] == "REQUIRES_APPROVAL"), None)
        if not decision_id:
            return {"eligible": False, "reasons": ["action has no decision to approve against"], "decision_id": None, "approval_current": False}
        head = self._head(decision_id)
        reasons: list[str] = []
        if head["decision"].get("status") != DerivedStatus.VALID.value:
            reasons.append(f"decision {decision_id} is {head['decision'].get('status')}")
        deps = list(head["props"].get("dependency_ids") or [])
        for dep in deps:
            node = self.store.read_node(self.site, dep)
            status = (node or {"properties": {}})["properties"].get("status")
            if status not in ("VALID", "ACTIVE"):
                reasons.append(f"dependency {dep} is {status or 'MISSING'}")
        live = self._live_hash(decision_id, deps, head["props"].get("conditions_json", ""))
        if head["props"].get("graph_revision") != live:
            reasons.append("the evidence behind this decision changed after its last revision; re-evaluate it first")
        current = False
        for edge in edges["out"]:
            if edge["rel"] != "APPROVED_BY":
                continue
            ap = (self.store.read_node(self.site, edge["id"]) or {"properties": {}})["properties"]
            if ap.get("approval_status") == "VALID" and ap.get("graph_revision") == head["props"].get("graph_revision") == live:
                current = True
        return {"eligible": not reasons, "reasons": reasons, "decision_id": decision_id, "revision_n": head["n"], "approval_current": current}

    def approve_action(self, action_id: str, reviewer: str, note: str = "") -> dict[str, Any]:
        state = self.eligibility(action_id)
        if not state["eligible"]:
            return {"approved": False, "reasons": state["reasons"], "action_id": action_id}
        head = self._head(state["decision_id"])
        approval_id = f"approval:{_slug(action_id)}:{head['n']}"
        self.store.upsert_node(self.site, Label.APPROVAL, approval_id, {
            "decision_id": state["decision_id"], "revision_id": head["id"], "graph_revision": head["props"]["graph_revision"],
            "approval_status": "VALID", "approved_by": reviewer[:120], "approved_at": now_iso(), "note": note[:300]})
        self.store.link(self.site, Label.ACTION, action_id, Rel.APPROVED_BY, Label.APPROVAL, approval_id)
        self.store.link(self.site, Label.APPROVAL, approval_id, Rel.ON_REVISION, Label.DECISION_REVISION, head["id"])
        self.store.update_node_properties(self.site, Label.ACTION, action_id, {"status": ActionStatus.APPROVED.value})
        return {"approved": True, "action_id": action_id, "approval_id": approval_id, "revision_id": head["id"], "graph_revision": head["props"]["graph_revision"], "reviewer": reviewer}

    # ------------------------------------------------------------------ evidence change
    def supersede_source(self, *, old_source_id: str, new_source: dict[str, Any], new_claims: Sequence[dict[str, Any]], change_id: str,
                         reason: str = "") -> dict[str, Any]:
        """A newer source arrives. If it is authoritative enough, mark everything that rested on the old one stale."""
        prior = self.store.read_node(self.site, change_id)
        if prior:
            return {**json.loads(prior["properties"].get("result_json", "{}")), "duplicate": True}
        old = self._need(Label.SOURCE_VERSION, old_source_id)["props"]
        incumbent = EvidenceStrength(int(old.get("authority_level", 3)), old.get("verification_status", Verification.UNVERIFIED.value), float(old.get("confidence", 0.0)))
        challenger = EvidenceStrength(int(new_source.get("authority_level", 3)), new_source.get("verification", Verification.VERIFIED.value), float(new_source.get("confidence", 0.9)))
        verdict = resolve_authority(incumbent, challenger)
        at = now_iso()
        if verdict != Verdict.REPLACE:
            note = "The new source is not authoritative enough to replace the existing one, so nothing was marked stale."
            result = {"verdict": verdict.value, "invalidated": [], "duplicate": False, "note": note}
            self.store.upsert_node(self.site, Label.CHANGE, change_id, {"verdict": verdict.value, "source_id": new_source["source_id"], "observed_at": at,
                                                                          "reason": reason[:300], "result_json": json.dumps(result)})
            return result
        self.record_source(**{k: v for k, v in new_source.items() if k != "verification"}, verification=new_source.get("verification", Verification.VERIFIED.value))
        replaced: dict[str, str] = {}
        for claim in new_claims:
            self.record_claim(claim_id=claim["claim_id"], source_id=new_source["source_id"], fact_key=claim["fact_key"], fact_value=claim["fact_value"],
                              authority_level=int(new_source.get("authority_level", 3)), confidence=float(new_source.get("confidence", 0.9)))
            if claim.get("replaces"):
                replaced[claim["replaces"]] = claim["claim_id"]
        self.store.update_node_properties(self.site, Label.SOURCE_VERSION, old_source_id, {"status": SourceStatus.SUPERSEDED.value})
        self.store.link(self.site, Label.SOURCE_VERSION, new_source["source_id"], Rel.SUPERSEDES, Label.SOURCE_VERSION, old_source_id)
        impacts = self.store.find_impacts(self.site, [old_source_id])
        affected: list[dict[str, Any]] = []
        self.store.upsert_node(self.site, Label.CHANGE, change_id, {"verdict": verdict.value, "source_id": new_source["source_id"], "observed_at": at, "reason": reason[:300]})
        for path in impacts:
            node = self.store.read_node(self.site, path.node_id)
            if not node:
                continue
            label = node["labels"][0]
            before = node["properties"].get("status", "")
            if label == "Claim":
                after = "SUPERSEDED"
                if path.node_id in replaced:
                    self.store.link(self.site, Label.CLAIM, replaced[path.node_id], Rel.SUPERSEDES, Label.CLAIM, path.node_id)
            elif label in _STALE_ON_CHANGE:
                after = _STALE_ON_CHANGE[label]
            elif label == "ActionProposal":
                after = ActionStatus.SUSPENDED.value if before in (ActionStatus.APPROVED.value, ActionStatus.PENDING.value) else before
            else:
                continue  # DecisionRevision is immutable; context-only nodes are never touched
            self.store.update_node_properties(self.site, Label(label), path.node_id, {"status": after})
            self.store.link(self.site, Label(label), path.node_id, Rel.INVALIDATED_BY, Label.CHANGE, change_id)
            affected.append({"id": path.node_id, "label": label, "before": before, "after": after, "depth": path.depth, "via": list(path.path)})
        for item in [a for a in affected if a["label"] == "ActionProposal"]:
            for edge in self.store.edges_of(self.site, item["id"])["out"]:
                if edge["rel"] == "APPROVED_BY":
                    self.store.update_node_properties(self.site, Label.APPROVAL, edge["id"], {"approval_status": "VOID"})
        result = {"verdict": verdict.value, "old_source": old_source_id, "new_source": new_source["source_id"], "replaced_claims": replaced, "invalidated": affected,
                  "duplicate": False, "audit_hash": stable_hash({"change": change_id, "paths": [a["id"] for a in affected]})}
        self.store.update_node_properties(self.site, Label.CHANGE, change_id, {"result_json": json.dumps(result, sort_keys=True)[:6000]})
        return result

    def reevaluate_decision(self, *, decision_id: str, new_dependency_ids: Sequence[str], current_facts: dict[str, tuple[str, Any]], reason: str,
                            new_summary: str | None = None) -> dict[str, Any]:
        """Re-run a decision's preconditions against the current authoritative claims and append a new revision."""
        head = self._head(decision_id)
        conds = parse_conditions(head["decision"].get("conditions"))
        results = evaluate_conditions(conds, current_facts)
        status = DerivedStatus.VALID.value if results and all(r.holds for r in results) else DerivedStatus.INVALIDATED.value
        for dep in head["props"].get("dependency_ids") or []:
            if dep not in new_dependency_ids:
                self.store.unlink(self.site, decision_id, Rel.DEPENDS_ON, dep)
        for dep in new_dependency_ids:
            self.store.link(self.site, Label.DECISION, decision_id, Rel.DEPENDS_ON, self._label_of(dep), dep)
        if new_summary:
            self.store.update_node_properties(self.site, Label.DECISION, decision_id, {"summary": new_summary[:500]})
        revision = self._append_revision(decision_id, list(new_dependency_ids), status, json.dumps([c.as_dict() for c in conds], sort_keys=True), reason)
        # The plan follows the decision's new state; the action stays unapproved until a human reviews this revision.
        for edge in self.store.edges_of(self.site, decision_id)["in"]:
            if edge["rel"] == "DEPENDS_ON" and edge["label"] == "Plan":
                self.store.update_node_properties(self.site, Label.PLAN, edge["id"], {"status": status})
        return {"decision_id": decision_id, "status": status, "conditions": [r.as_dict() for r in results], "revision": revision}

    def handoffs(self) -> list[dict[str, Any]]:
        """Cross-agent sharing record: producer, recaller and whether the shared memory is still usable."""
        return [{**h, "usable": h["memory_status"] == DerivedStatus.VALID.value} for h in self.store.handoffs(self.site)]

    # ------------------------------------------------------------------ dry run
    def impact_preview(self, source_id: str) -> dict[str, Any]:
        """What WOULD go stale if this source were superseded. Reads the graph and changes nothing."""
        self._need(Label.SOURCE_VERSION, source_id)
        items = []
        for path in self.store.find_impacts(self.site, [source_id]):
            node = self.store.read_node(self.site, path.node_id)
            if node and node["labels"][0] != "DecisionRevision":
                items.append({"id": path.node_id, "label": node["labels"][0], "status": node["properties"].get("status"), "depth": path.depth, "via": list(path.path),
                              "summary": node["properties"].get("summary") or node["properties"].get("fact_key") or ""})
        return {"source_id": source_id, "would_mark_stale": items, "read_only": True}

    # ------------------------------------------------------------------ read model
    def snapshot(self) -> dict[str, Any]:
        memories = self.store.memory_lineage(self.site, limit=200)
        for m in memories:
            m["blocked_reason"] = self._block_reason(m)
        decisions = []
        for d in self.store.list_nodes(self.site, Label.DECISION, limit=100):
            head = self._head(d["id"])
            decisions.append({**d, "dependency_ids": list(head["props"].get("dependency_ids") or []), "revision_id": head["id"], "graph_revision": head["props"].get("graph_revision")})
        actions = [{**a, "eligibility": self.eligibility(a["id"])} for a in self.store.list_nodes(self.site, Label.ACTION, limit=100)]
        return {"memories": memories, "decisions": decisions, "actions": actions,
                "sources": self.store.list_nodes(self.site, Label.SOURCE_VERSION, limit=200), "changes": self.store.list_nodes(self.site, Label.CHANGE, limit=100),
                "agents": self.store.list_nodes(self.site, Label.AGENT, limit=100), "approvals": self.store.list_nodes(self.site, Label.APPROVAL, limit=200)}
