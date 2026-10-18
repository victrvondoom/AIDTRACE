import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { MemorySnapshot } from "@/lib/lab-api";
import { buildLineage } from "@/lib/aidtrace-lineage";
import type { AidtraceData } from "./data";
import { LineageView } from "./views";

vi.mock("next/dynamic", () => ({ default: () => () => null }));

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
  demo: null, health: null, snap, handoffs: [], scenario: null, lineage: buildLineage(snap), errors: {}, loading: false, refreshMemory: async () => {}, ...over,
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
  });

  it("surfaces a memory-service failure", () => {
    render(<LineageView data={data({ lineage: null, errors: { memory: "memory offline" } })} selection={null} onSelect={() => {}} />);
    expect(screen.getByRole("alert")).toHaveTextContent("memory offline");
  });
});
