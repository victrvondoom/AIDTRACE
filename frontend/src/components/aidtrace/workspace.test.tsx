import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { MemorySnapshot } from "@/lib/lab-api";
import { buildLineage } from "@/lib/aidtrace-lineage";
import type { AidtraceData } from "./data";

const snap: MemorySnapshot = {
  sources: [{ id: "src:a", title: "Ember", status: "ACTIVE", version_label: "v1", authority_level: 2 }],
  memories: [], approvals: [], changes: [], agents: [],
  decisions: [{ id: "gc:s1:d1", summary: "Recommend Illustrative Packaging D for the component", status: "ACTIVE", revision_n: 1, dependency_ids: [], revision_id: "r1", graph_revision: "g1" }],
  actions: [{ id: "a1", summary: "Place a trial order", status: "PROPOSED", eligibility: { eligible: true, reasons: [], decision_id: "gc:s1:d1", approval_current: false } }],
};
const fixture: AidtraceData = {
  demo: { mode: "ILLUSTRATIVE_DEMO", notice: "", product: "cardboard packaging", destination: "US", transport_mode: "sea", results: [], graph: { nodes: [], edges: [] } },
  health: null, snap, handoffs: [], site: null,
  scenario: { manufacturers: [{ id: "m1", name: "Illustrative Packaging D", isCurrent: false, ecoScore: 10, componentId: "c", location: { countryCode: "PT", country: "Portugal" }, manufacturingEmissionsTco2e: { q10: 1, q50: 5, q90: 9 }, transportEmissionsTco2e: 1, certifications: [] }], components: [] } as unknown as AidtraceData["scenario"], lineage: buildLineage(snap), errors: {}, loading: false, refreshMemory: async () => ({ snap, site: null }),
};
const hook = vi.hoisted(() => ({ calls: 0 }));

vi.mock("./data", async (orig) => ({ ...(await orig<typeof import("./data")>()), useAidtraceData: () => { hook.calls += 1; return fixture; } }));
vi.mock("@/features/feature-host", () => ({
  Boundary: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  FEATURES: [{ id: "greenchain", name: "GreenChain", status: "INTEGRATED_TESTED", category: "x", backend: "x", summary: "s", render: () => <p>GreenChain extension body</p> }],
}));
vi.mock("./views", () => ({
  toneOf: () => "neutral",
  GlobeView: ({ onSelect, selection }: { onSelect: (s: { kind: "supplier"; id: string; label: string }) => void; selection: { label: string } | null }) => (
    <div data-testid="globe-view"><button onClick={() => onSelect({ kind: "supplier", id: "m1", label: "Illustrative Packaging D" })}>pick supplier</button><span>selected:{selection?.label ?? "none"}</span></div>),
  GraphView: () => <div data-testid="graph-view" />,
  LineageView: ({ selection }: { selection: { label: string } | null }) => <div data-testid="lineage-view">lineage selected:{selection?.label ?? "none"}</div>,
  TimelineView: () => <div data-testid="timeline-view" />,
}));

import { AidtraceWorkspace } from "./workspace";

describe("AidtraceWorkspace", () => {
  afterEach(cleanup);

  it("opens on the globe with one input and the three primary actions, and no legacy navigation", () => {
    render(<AidtraceWorkspace />);
    expect(screen.getByRole("tab", { name: "Globe", selected: true })).toBeInTheDocument();
    expect(screen.getByTestId("globe-view")).toBeInTheDocument();
    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual(["Globe", "Graph", "Lineage", "Timeline"]);
    expect(screen.getByPlaceholderText("Ask about a supplier, risk, or decision…")).toBeInTheDocument();
    const actions = screen.getByRole("list", { name: "Primary actions" });
    expect(actions).toHaveTextContent("Investigate Risk");
    expect(actions).toHaveTextContent("Update Evidence");
    expect(actions).toHaveTextContent("Review Decision");
    expect(screen.queryByText(/legacy/i)).not.toBeInTheDocument();
  });

  it("keeps the selection when the view changes and does not reload data", () => {
    render(<AidtraceWorkspace />);
    fireEvent.click(screen.getByText("pick supplier"));
    expect(screen.getByText("selected:Illustrative Packaging D")).toBeInTheDocument();
    const renders = hook.calls;
    fireEvent.click(screen.getByRole("tab", { name: "Lineage" }));
    expect(screen.getByTestId("lineage-view")).toHaveTextContent("lineage selected:Illustrative Packaging D");
    expect(screen.getByTestId("aidtrace-inspector")).toHaveTextContent("Packaging D");
    expect(hook.calls - renders).toBeLessThan(5); // re-renders only: the data hook owns one set of requests for the whole session
  });

  it("keeps the extensions launcher closed until asked, then opens an extension inside the workspace", () => {
    render(<AidtraceWorkspace />);
    expect(screen.queryByRole("dialog", { name: "Extensions" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("aidtrace-extensions-button"));
    expect(screen.getByRole("dialog", { name: "Extensions" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^GreenChain/ }));
    expect(screen.queryByRole("dialog", { name: "Extensions" })).not.toBeInTheDocument();
    expect(screen.getByTestId("aidtrace-extension")).toHaveAttribute("data-extension", "greenchain");
    expect(screen.getByText("GreenChain extension body")).toBeInTheDocument();
    expect(screen.queryByTestId("globe-view")).not.toBeInTheDocument();
    expect(window.location.pathname).toBe("/");
  });

  it("returns to the globe with the investigation exactly as it was after closing an extension", () => {
    render(<AidtraceWorkspace />);
    fireEvent.click(screen.getByText("pick supplier"));
    fireEvent.click(screen.getByTestId("aidtrace-extensions-button"));
    fireEvent.click(screen.getByRole("button", { name: /^GreenChain/ }));
    expect(screen.getByTestId("aidtrace-context-bar")).toHaveTextContent("Packaging D selected on the globe");
    fireEvent.click(screen.getByRole("button", { name: /back to workspace|close greenchain/i }));
    expect(screen.getByTestId("globe-view")).toBeInTheDocument();
    expect(screen.getByText("selected:Illustrative Packaging D")).toBeInTheDocument();
  });

  it("closes an open extension when a workspace view is chosen", () => {
    render(<AidtraceWorkspace />);
    fireEvent.click(screen.getByTestId("aidtrace-extensions-button"));
    fireEvent.click(screen.getByRole("button", { name: /^GreenChain/ }));
    fireEvent.click(screen.getByRole("tab", { name: "Lineage" }));
    expect(screen.queryByTestId("aidtrace-extension")).not.toBeInTheDocument();
    expect(screen.getByTestId("lineage-view")).toBeInTheDocument();
  });

  it("opens the decision review from the third action, with state read from backend fields", () => {
    render(<AidtraceWorkspace />);
    fireEvent.click(screen.getByRole("button", { name: /Review Decision/ }));
    expect(screen.getByRole("button", { name: /^Decision/, expanded: true })).toBeInTheDocument();
    expect(screen.getByText("Needs review")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve" })).toBeEnabled();
  });
});
