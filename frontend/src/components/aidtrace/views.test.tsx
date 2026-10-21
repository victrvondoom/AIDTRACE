import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { MemorySnapshot } from "@/lib/lab-api";
import { buildLineage } from "@/lib/aidtrace-lineage";
import type { AidtraceData } from "./data";
import { cypherPresets, LineageView, TimelineView } from "./views";

vi.mock("next/dynamic", () => ({ default: () => () => null }));

describe("cypherPresets", () => {
  const node = (id: string, type: string) => ({ id, label: id, type, props: {} });
  const edge = (source: string, target: string, rel: string) => ({ source, target, rel, weight: 1, certainty: "definite" as const, at: null, until: null, disabled: false });

  it("keeps the two generic presets when there is no persisted graph", () => {
    expect(cypherPresets(null).map((p) => p.label)).toEqual(["Node counts", "Relationship stats"]);
  });

  it("builds presets from the labels and relationship types the graph actually holds", () => {
    const graph = {
      nodes: [node("s1", "Supplier"), node("s2", "Supplier"), node("c1", "Claim"), node("d1", "Decision")],
      edges: [edge("c1", "s1", "SUPPORTED_BY"), edge("d1", "c1", "RELIES_ON"), edge("d1", "s2", "RELIES_ON")],
    };
    const presets = cypherPresets(graph);
    expect(presets.map((p) => p.label)).toContain("Sample Supplier");
    expect(presets.map((p) => p.label)).toContain("RELIES_ON links");
    expect(presets.find((p) => p.label === "Sample Supplier")?.query).toBe("MATCH (n:`Supplier`) RETURN n.id AS id, labels(n)[0] AS type LIMIT 10");
  });

  it("never turns a value that is not a plain identifier into Cypher", () => {
    const graph = { nodes: [node("x", "Bad`Label; DROP")], edges: [edge("x", "x", "rel with space")] };
    const presets = cypherPresets(graph);
    expect(presets.map((p) => p.label)).toEqual(["Node counts", "Relationship stats"]);
    expect(presets.every((p) => !p.query.includes("DROP") && !p.query.includes("rel with space"))).toBe(true);
  });
});

const snap: MemorySnapshot = {
  sources: [
    { id: "src:a", title: "Supplier audit", status: "ACTIVE", version_label: "v1", authority_level: 3 },
    { id: "src:b", title: "Audit copy", status: "ACTIVE", version_label: "v1", authority_level: 1 },
  ],
  memories: [{
    id: "mem:1", memory_kind: "SEMANTIC", summary: "Packaging D ranks first", agent_id: "agent:gc", status: "STALE", verification_status: "VERIFIED", confidence: 0.9,
    independent_sources: 1, recorded_at: "2026-10-01T00:00:00Z", last_verified_at: "2026-10-01T00:00:00Z", investigation_ref: "", blocked_reason: "memory is STALE",
    claims: [{ id: "claim:1", fact_key: "emissions", fact_value: 5, status: "SUPERSEDED" }],
    sources: [{ id: "src:a", status: "ACTIVE", document_id: null, content_sha256: "h1" }, { id: "src:b", status: "ACTIVE", document_id: null, content_sha256: "h1" }],
  }],
  decisions: [{ id: "dec:1", summary: "Prefer Packaging D", status: "INVALIDATED", revision_n: 2, dependency_ids: ["mem:1"], revision_id: "r2", graph_revision: "g2" }],
  actions: [{ id: "act:1", summary: "Place a trial order", status: "SUSPENDED", eligibility: { eligible: false, reasons: ["decision is INVALIDATED"], decision_id: "dec:1", approval_current: false } }],
  approvals: [], changes: [], agents: [],
};

const data = (over: Partial<AidtraceData> = {}): AidtraceData => ({
  demo: null, health: null, snap, handoffs: [], site: null, scenario: null, lineage: buildLineage(snap), errors: {}, loading: false, refreshMemory: async () => ({ snap: null, site: null }), ...over,
});

describe("LineageView", () => {
  it("shows records read from the graph, flags stale ones and counts copies once", () => {
    render(<LineageView data={data()} selection={null} onSelect={() => {}} />);
    expect(screen.getByTestId("aidtrace-lineage")).toHaveTextContent("2 sources → 1 origin");
    expect(screen.getByTestId("aidtrace-lineage")).toHaveTextContent("2 of 2 sources carry a content hash");
    expect(screen.getByText("Packaging D ranks first")).toBeInTheDocument();
    expect(screen.getByText(/stale or blocked/)).toBeInTheDocument();
  });

  it("reports a selection when a record is clicked", () => {
    const onSelect = vi.fn();
    render(<LineageView data={data()} selection={null} onSelect={onSelect} />);
    fireEvent.click(screen.getByTitle(/Prefer Packaging D/));
    expect(onSelect).toHaveBeenCalledWith({ kind: "decision", id: "dec:1", label: "Prefer Packaging D" });
  });

  it("explains an empty graph instead of inventing lineage", () => {
    const empty: MemorySnapshot = { ...snap, sources: [], memories: [], decisions: [], actions: [] };
    render(<LineageView data={data({ snap: empty, lineage: buildLineage(empty) })} selection={null} onSelect={() => {}} />);
    expect(screen.getByText("No evidence lineage yet")).toBeInTheDocument();
    expect(screen.getByText(/Choose Investigate Risk/)).toBeInTheDocument();
  });

  it("labels each source by what it can prove", () => {
    render(<LineageView data={data()} selection={null} onSelect={() => {}} />);
    expect(screen.getByText("Original source")).toBeInTheDocument();
    expect(screen.getByText("Repeated citation")).toBeInTheDocument();
  });

  it("surfaces a memory-service failure", () => {
    render(<LineageView data={data({ lineage: null, errors: { memory: "memory offline" } })} selection={null} onSelect={() => {}} />);
    expect(screen.getByRole("alert")).toHaveTextContent("memory offline");
  });
});

describe("TimelineView", () => {
  it("merges graph history with this session's runs, newest first", () => {
    const withChange: MemorySnapshot = { ...snap, changes: [{ id: "c1", verdict: "SUPERSEDED", reason: "Grid factor revised", observed_at: "2026-10-02T09:00:00Z" }] };
    render(<TimelineView data={data({ snap: withChange })} runs={[{ at: "2026-10-03T10:00:00Z", kind: "investigation", text: "Investigated Packaging D" }]} onSelect={() => {}} />);
    const items = screen.getAllByRole("listitem").map((li) => li.textContent ?? "");
    expect(items[0]).toContain("Investigated Packaging D");
    expect(items.some((t) => t.includes("SUPERSEDED: Grid factor revised"))).toBe(true);
    expect(items.some((t) => t.includes("agent:gc recorded: Packaging D ranks first"))).toBe(true);
  });

  it("says when there is no history instead of inventing events", () => {
    const empty: MemorySnapshot = { ...snap, memories: [], decisions: [], actions: [], approvals: [], changes: [] };
    render(<TimelineView data={data({ snap: empty })} runs={[]} onSelect={() => {}} />);
    expect(screen.getByText("No activity yet")).toBeInTheDocument();
  });
});
