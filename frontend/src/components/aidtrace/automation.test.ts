import { beforeEach, describe, expect, it, vi } from "vitest";
import type { MemorySnapshot } from "@/lib/lab-api";

const lab = vi.hoisted(() => ({
  analyzeLab: vi.fn(), getSiteGraph: vi.fn(), greenchainDemo: vi.fn(), greenchainHealth: vi.fn(), greenchainWhatIf: vi.fn(), memoryHandoffs: vi.fn(),
  memorySnapshot: vi.fn(), memoryRecordScenario: vi.fn(), memoryPreviewRevision: vi.fn(), memoryRevise: vi.fn(),
}));
vi.mock("@/lib/lab-api", () => lab);

import { investigateRisk, latestScenarioId, SYNTHETIC_REVISION, updateEvidence, type Stage } from "./automation";
import type { AidtraceData } from "./data";

const snap: MemorySnapshot = {
  sources: [{ id: "src:a", title: "Ember", status: "ACTIVE", version_label: "v1", authority_level: 2 }],
  memories: [{
    id: "gc:s1:mem:1", memory_kind: "SEMANTIC", summary: "Illustrative Packaging D ranks first", agent_id: "agent:gc", status: "STALE", verification_status: "VERIFIED", confidence: 0.9,
    independent_sources: 1, recorded_at: "2026-10-01T00:00:00Z", last_verified_at: "2026-10-01T00:00:00Z", investigation_ref: "", blocked_reason: "memory is STALE",
    claims: [{ id: "gc:s1:est:Illustrative_Packaging_D:v1", fact_key: "emissions", fact_value: 5, status: "SUPERSEDED" }],
    sources: [{ id: "src:a", status: "ACTIVE", document_id: null, content_sha256: "h1" }],
  }],
  decisions: [{ id: "gc:s1:decision:1", summary: "Recommend Illustrative Packaging D for the component", status: "INVALIDATED", revision_n: 1, dependency_ids: ["gc:s1:mem:1"], revision_id: "r1", graph_revision: "g1" }],
  actions: [], approvals: [], changes: [], agents: [],
};
const site = { graph: { nodes: [{ id: "gc:s1:est:Illustrative_Packaging_D:v1", label: "est D", type: "Claim", props: {} }, { id: "gc:s1:mem:1", label: "memory", type: "Memory", props: {} }], edges: [] }, empty: false, truncated: false };
const maker = (id: string, name: string, eco: number, current = false) => ({
  id, name, isCurrent: current, ecoScore: eco, componentId: "c1", location: { countryCode: "PT", country: "Portugal" },
  manufacturingEmissionsTco2e: { q10: 1, q50: 5, q90: 9 }, transportEmissionsTco2e: 0.5, certifications: [],
});
const data = (over: Partial<AidtraceData> = {}): AidtraceData => ({
  demo: { mode: "ILLUSTRATIVE_DEMO", notice: "", product: "cardboard packaging", destination: "US", transport_mode: "sea", results: [], graph: { nodes: [], edges: [] } },
  health: null, snap, handoffs: [], site, lineage: null, errors: {}, loading: false,
  scenario: { manufacturers: [maker("m-d", "Illustrative Packaging D", 10), maker("m-b", "Illustrative Packaging B", 20, true)], components: [] } as unknown as AidtraceData["scenario"],
  refreshMemory: vi.fn(async () => ({ snap, site })), ...over,
});

beforeEach(() => { vi.clearAllMocks(); });

describe("latestScenarioId", () => {
  it("reads the GreenChain scenario from decision ids", () => {
    expect(latestScenarioId(snap.decisions)).toBe("s1");
    expect(latestScenarioId([])).toBeNull();
  });
});

describe("investigateRisk", () => {
  it("traverses the persisted FalkorDB graph from the supplier's claims and reports real stages", async () => {
    lab.analyzeLab.mockImplementation(async (_algo: string, _src: unknown, params: { direction: string }) => ({
      result: { node_marks: params.direction === "reverse" ? { "gc:s1:est:Illustrative_Packaging_D:v1": "changed", "gc:s1:mem:1": "impacted" } : {} },
    }));
    lab.greenchainWhatIf.mockResolvedValue({ removed: "Illustrative Packaging D", top_before: "D", top_after: "B", recommendation_changes: true, rank_changes: [] });
    const seen: Stage[][] = [];
    const r = await investigateRisk({ data: data(), supplierId: "m-d" }, (s) => seen.push(s));
    expect(lab.analyzeLab).toHaveBeenCalledWith("blast_radius", { site_graph: true }, expect.objectContaining({ changed: ["gc:s1:est:Illustrative_Packaging_D:v1"] }));
    expect(r.traversal).toBe("FalkorDB site graph");
    expect(r.dependents.map((d) => d.id)).toEqual(["gc:s1:mem:1"]);
    expect(r.decisions).toEqual([expect.objectContaining({ id: "gc:s1:decision:1", stale: true })]);
    expect(r.recorded).toBe("already recorded");
    const last = seen[seen.length - 1];
    expect(last.find((s) => s.id === "cyber")?.status).toBe("skipped");
    expect(last.find((s) => s.id === "summary")?.status).toBe("done");
    expect(r.uncertainty.join(" ")).toMatch(/No live security/);
  });

  it("records a baseline first when the graph holds no decision", async () => {
    lab.memoryRecordScenario.mockResolvedValue({ scenario_id: "s1" });
    const empty: MemorySnapshot = { ...snap, memories: [], decisions: [] };
    const refresh = vi.fn(async () => ({ snap, site }));
    lab.analyzeLab.mockResolvedValue({ result: { node_marks: {} } });
    lab.greenchainWhatIf.mockResolvedValue(null);
    const r = await investigateRisk({ data: data({ snap: empty, refreshMemory: refresh }), supplierId: "m-d" }, () => {});
    expect(lab.memoryRecordScenario).toHaveBeenCalledOnce();
    expect(refresh).toHaveBeenCalled();
    expect(r.recorded).toBe("recorded now");
  });

  it("refuses to run, rather than invent results, when the scenario is not loaded", async () => {
    await expect(investigateRisk({ data: data({ scenario: null }), supplierId: null }, () => {})).rejects.toThrow(/not loaded/);
  });
});

describe("updateEvidence", () => {
  const revised = {
    duplicate: false, dataset: "EMBER", revision: { country: "PT", factor: 50, label: "x" }, cascade: { verdict: "INVALIDATED", invalidated: [{ id: "n1", label: "memory", before: "VALID", after: "STALE", depth: 1, via: [] }], audit_hash: "abc" },
    ranking: [], recommendation_changed: true, top_before: "Illustrative Packaging D", top_after: "Illustrative Packaging B", old_decision: { id: "d", status: "INVALIDATED" },
    old_action: { id: "a", eligibility: { eligible: false, reasons: [], decision_id: "d", approval_current: false } }, new_proposal: { decision_id: "d2", action_id: "a2", eligibility: { eligible: true, reasons: [], decision_id: "d2", approval_current: false } }, new_memory_id: "m2",
  };

  it("previews, applies the labelled synthetic revision and reports the changed recommendation", async () => {
    lab.memoryPreviewRevision.mockResolvedValue({ top_before: "Illustrative Packaging D", top_after: "Illustrative Packaging B", recommendation_changes: true, ranking: [] });
    lab.memoryRevise.mockResolvedValue(revised);
    const d = data();
    const r = await updateEvidence(d, () => {});
    expect(lab.memoryPreviewRevision).toHaveBeenCalledWith(expect.objectContaining({ scenario_id: "s1", dataset: "EMBER", country: "PT", factor: 50 }));
    expect(lab.memoryRevise).toHaveBeenCalledOnce();
    expect(SYNTHETIC_REVISION.label).toMatch(/synthetic/i);
    expect(r).toMatchObject({ recommendationChanged: true, topBefore: "Illustrative Packaging D", topAfter: "Illustrative Packaging B", newProposal: true, alreadyApplied: false });
    expect(r.invalidated).toHaveLength(1);
    expect(d.refreshMemory).toHaveBeenCalled();
  });

  it("does not reapply an already-applied revision", async () => {
    lab.memoryPreviewRevision.mockResolvedValue({ top_before: "D", top_after: "B", recommendation_changes: true, ranking: [] });
    lab.memoryRevise.mockResolvedValue({ duplicate: true });
    const r = await updateEvidence(data(), () => {});
    expect(r.alreadyApplied).toBe(true);
    expect(r.invalidated).toEqual([]);
  });

  it("surfaces a backend failure instead of continuing", async () => {
    lab.memoryPreviewRevision.mockRejectedValue(new Error("graph unavailable"));
    await expect(updateEvidence(data(), () => {})).rejects.toThrow("graph unavailable");
    expect(lab.memoryRevise).not.toHaveBeenCalled();
  });
});
