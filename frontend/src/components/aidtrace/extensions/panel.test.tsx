import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { MemorySnapshot } from "@/lib/lab-api";
import { buildLineage } from "@/lib/aidtrace-lineage";
import type { AidtraceData } from "../data";

vi.mock("next/dynamic", () => ({ default: () => () => null }));
vi.mock("@/features/feature-host", () => ({ Boundary: ({ children }: { children: React.ReactNode }) => <>{children}</>, FEATURES: [] }));
vi.mock("@/app/(app)/rca/page", async () => {
  const { default: Link } = await import("next/link");
  return { default: function RcaStub() { return <div><p>rca page</p><Link href="/events">to events</Link><Link href="/hub">to hub</Link><Link href="/nowhere">to nowhere</Link></div>; } };
});

import { AidtraceProvider, useAidtrace, type AidtraceContextValue } from "./context";
import { ExtensionPanel } from "./panel";
import { extensionById, type AidtraceExtension } from "./registry";

const snap: MemorySnapshot = { sources: [], memories: [], decisions: [], actions: [], approvals: [], changes: [], agents: [] };
const maker = { id: "m-d", name: "Illustrative Packaging D", isCurrent: false, ecoScore: 10, componentId: "c", location: { countryCode: "PT", country: "Portugal" },
  manufacturingEmissionsTco2e: { q10: 1, q50: 5, q90: 9 }, transportEmissionsTco2e: 1, certifications: [] };
const data: AidtraceData = { demo: null, health: null, snap, handoffs: [], site: null, lineage: buildLineage(snap), errors: {}, loading: false, refreshMemory: async () => ({ snap, site: null }),
  scenario: { manufacturers: [maker], components: [] } as unknown as AidtraceData["scenario"] };
const ctx = (over: Partial<AidtraceContextValue> = {}): AidtraceContextValue => ({
  data, selection: { kind: "supplier", id: "m-d", label: "Illustrative Packaging D" }, select: () => {}, investigation: null, evidence: null, recommended: null, view: "globe", runs: [], openExtension: () => {}, ...over,
});

function SelectionProbe() { const { selection } = useAidtrace(); return <p data-testid="probe">sees {selection?.label ?? "nothing"}</p>; }
const probeExt: AidtraceExtension = {
  id: "probe", title: "Probe", category: "Investigation & Intelligence", icon: "graph", description: "", keywords: [], contextual: true, backend: [],
  tabs: [{ id: "native", label: "Native", body: SelectionProbe }, { id: "rca", label: "RCA page", path: "/rca" }],
};

describe("ExtensionPanel", () => {
  afterEach(cleanup);

  it("shows the shared selection to the extension and in its context line", () => {
    render(<AidtraceProvider value={ctx()}><ExtensionPanel ext={probeExt} onClose={() => {}} onOpen={() => {}} /></AidtraceProvider>);
    expect(screen.getByTestId("probe")).toHaveTextContent("sees Illustrative Packaging D");
    expect(screen.getByTestId("aidtrace-context-bar")).toHaveTextContent("Packaging D selected on the globe");
    expect(screen.getByText("follows your selection")).toBeInTheDocument();
  });

  it("says the supplier is only the recommended one when nothing is selected", () => {
    render(<AidtraceProvider value={ctx({ selection: null, recommended: "Illustrative Packaging D" })}><ExtensionPanel ext={probeExt} onClose={() => {}} onOpen={() => {}} /></AidtraceProvider>);
    expect(screen.getByTestId("aidtrace-context-bar")).toHaveTextContent("recommended supplier (nothing selected)");
    expect(screen.getByTestId("probe")).toHaveTextContent("sees nothing");
  });

  it("hosts a migrated page in a tab, hands other extensions' links over, and closes back to the workspace", async () => {
    const onOpen = vi.fn(); const onClose = vi.fn();
    await act(async () => { render(<AidtraceProvider value={ctx()}><ExtensionPanel ext={extensionById("rca")!} onClose={onClose} onOpen={onOpen} /></AidtraceProvider>); });
    expect(await screen.findByText("rca page")).toBeInTheDocument();
    fireEvent.click(screen.getByText("to events"));
    expect(onOpen).toHaveBeenCalledWith("events", "/events");
    fireEvent.click(screen.getByText("to nowhere"));
    expect(screen.getByRole("status")).toHaveTextContent("is not available inside the workspace");
    fireEvent.click(screen.getByText("to hub"));
    expect(onClose).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: /back to workspace|close/i }));
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("switches tabs without touching the shared state", () => {
    const select = vi.fn();
    render(<AidtraceProvider value={ctx({ select })}><ExtensionPanel ext={probeExt} onClose={() => {}} onOpen={() => {}} /></AidtraceProvider>);
    fireEvent.click(screen.getByRole("tab", { name: "RCA page" }));
    fireEvent.click(screen.getByRole("tab", { name: "Native" }));
    expect(screen.getByTestId("probe")).toHaveTextContent("sees Illustrative Packaging D");
    expect(select).not.toHaveBeenCalled();
  });

  it("shows an extension's scope note", () => {
    render(<AidtraceProvider value={ctx()}><ExtensionPanel ext={extensionById("rca")!} onClose={() => {}} onOpen={() => {}} /></AidtraceProvider>);
    expect(screen.getByRole("note")).toHaveTextContent(/not been adapted to supplier-disruption/i);
  });
});
