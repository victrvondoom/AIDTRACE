import { describe, expect, it } from "vitest";
import type { MemorySnapshot } from "@/lib/lab-api";
import { buildLineage, chainOf, decisionState, isUnsafe } from "./aidtrace-lineage";

const snap: MemorySnapshot = {
  sources: [
    { id: "src:a", title: "Supplier audit", status: "ACTIVE", version_label: "v1", authority_level: 3 },
    { id: "src:b", title: "Audit copy", status: "ACTIVE", version_label: "v1", authority_level: 1 },
  ],
  memories: [{
    id: "mem:1", memory_kind: "FINDING", summary: "Supplier X has low emissions", agent_id: "agent:gc", status: "STALE", verification_status: "VERIFIED", confidence: 0.9,
    independent_sources: 1, recorded_at: "2026-10-01T00:00:00Z", last_verified_at: "2026-10-01T00:00:00Z", investigation_ref: "", blocked_reason: "source superseded",
    claims: [{ id: "claim:1", fact_key: "supplier_x.emissions", fact_value: 42, status: "ACTIVE" }],
    sources: [{ id: "src:a", status: "ACTIVE", document_id: null, content_sha256: "h1" }, { id: "src:b", status: "ACTIVE", document_id: null, content_sha256: "h1" }],
  }],
  decisions: [{ id: "dec:1", summary: "Prefer supplier X", status: "ACTIVE", revision_n: 2, dependency_ids: ["mem:1", "missing"], revision_id: "r2", graph_revision: "g2" }],
  actions: [{ id: "act:1", summary: "Issue purchase order", status: "PROPOSED", eligibility: { eligible: false, reasons: ["evidence is stale"], decision_id: "dec:1", approval_current: false } }],
  approvals: [], changes: [], agents: [],
};

describe("aidtrace lineage", () => {
  const lineage = buildLineage(snap);

  it("counts copies of one origin once", () => {
    expect(lineage.sourceCount).toBe(2);
    expect(lineage.originCount).toBe(1);
  });

  it("labels sources by what they can prove, never calling an unhashed source independent", () => {
    const trust = Object.fromEntries(lineage.nodes.filter((n) => n.kind === "source").map((n) => [n.id, n.trust]));
    expect(trust).toEqual({ "src:a": "Original source", "src:b": "Repeated citation" });
    const unhashed = buildLineage({ ...snap, memories: [{ ...snap.memories[0], sources: [{ id: "src:c", status: "ACTIVE", document_id: null, content_sha256: null }] }] });
    expect(unhashed.nodes.find((n) => n.id === "src:c")?.trust).toBe("Unverified");
  });

  it("links source and claim to memory, memory to decision, decision to action, and drops dangling dependencies", () => {
    const edges = lineage.edges.map((e) => `${e.from}>${e.to}`);
    expect(edges).toEqual(expect.arrayContaining(["src:a>mem:1", "claim:1>mem:1", "mem:1>dec:1", "dec:1>act:1"]));
    expect(edges.some((e) => e.includes("missing"))).toBe(false);
  });

  it("finds what a source supports and what a decision rests on", () => {
    const down = chainOf(lineage, "src:a").downstream;
    expect([...down].sort()).toEqual(["act:1", "dec:1", "mem:1"]);
    expect([...chainOf(lineage, "dec:1").upstream].sort()).toEqual(["claim:1", "mem:1", "src:a", "src:b"]);
  });

  it("flags stale and blocked states as unsafe", () => {
    expect(isUnsafe("STALE")).toBe(true);
    expect(isUnsafe("VALID")).toBe(false);
  });

  it("derives a decision's state from backend fields only", () => {
    const eligible = { eligibility: { eligible: true, reasons: [], approval_current: false } };
    expect(decisionState({ status: "INVALIDATED", revision_n: 2 }, undefined).label).toBe("Stale evidence");
    expect(decisionState({ status: "ACTIVE", revision_n: 1 }, { eligibility: { eligible: false, reasons: ["evidence is stale"], approval_current: false } })).toMatchObject({ label: "Approval blocked", reason: "evidence is stale" });
    expect(decisionState({ status: "ACTIVE", revision_n: 1 }, eligible).label).toBe("Needs review");
    expect(decisionState({ status: "ACTIVE", revision_n: 3 }, eligible).label).toBe("Re-evaluated");
    expect(decisionState({ status: "ACTIVE", revision_n: 1 }, { eligibility: { eligible: true, reasons: [], approval_current: true } }).label).toBe("Valid");
  });
});
