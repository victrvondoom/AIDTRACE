import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GraphLabWorkspace } from "./graph-lab-workspace";
import { analyzeLab } from "@/lib/lab-api";

vi.mock("@/components/graph-views", () => ({ GraphViews: () => <div>Graph canvas</div> }));
vi.mock("@/lib/api", () => ({ runDriftDemo: vi.fn() }));
vi.mock("@/lib/lab-api", () => ({
  getLabAlgorithms: vi.fn(async () => ({ source: "live", data: { algorithms: [{ id: "blast_radius", title: "Blast radius", summary: "Impact", params: [{ name: "depth", kind: "int", label: "Depth", default: 1, options: [], required: false }] }] } })),
  getLabScenarios: vi.fn(async () => ({ source: "live", data: { scenarios: [{ id: "plant_evidence", title: "Plant", recommended: [] }] } })),
  getLabScenario: vi.fn(async () => ({ source: "live", data: { graph: { nodes: [{ id: "a", label: "A", type: "asset", props: {} }], edges: [] }, recommended: [] } })),
  getSiteGraph: vi.fn(),
  analyzeLab: vi.fn(),
}));
const output = (count: number) => ({ algorithm: "blast_radius", graph_source: "scenario:plant_evidence", graph: { nodes: [{ id: "a", label: "A", type: "asset", props: {} }], edges: [] }, result: { summary: { affected: count }, findings: [], node_marks: {}, edge_marks: {}, notes: [] }, elapsed_ms: 1, provenance: { engine: "blast_radius", implementation: "Test engine", status: "TESTED", tests: "unit", readme_derived_hypothesis_from: [] } });

beforeEach(() => { vi.useFakeTimers(); vi.mocked(analyzeLab).mockReset(); vi.mocked(analyzeLab).mockResolvedValue(output(1)); });
afterEach(() => { vi.useRealTimers(); });

async function start() {
  render(<GraphLabWorkspace />);
  await act(async () => {});
  await act(async () => { await vi.advanceTimersByTimeAsync(400); });
}

describe("reactive graph analysis", () => {
  it("analyzes on load and debounces parameter edits", async () => {
    await start();
    expect(analyzeLab).toHaveBeenCalledTimes(1);
    fireEvent.change(screen.getByLabelText("Depth"), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText("Depth"), { target: { value: "3" } });
    await act(async () => { await vi.advanceTimersByTimeAsync(399); });
    expect(analyzeLab).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(analyzeLab).toHaveBeenCalledTimes(2);
    expect(analyzeLab).toHaveBeenLastCalledWith("blast_radius", { scenario: "plant_evidence" }, { depth: 3 }, expect.any(AbortSignal));
  });

  it("cancels superseded analyses and never renders their late result", async () => {
    let resolveOld!: (value: ReturnType<typeof output>) => void;
    vi.mocked(analyzeLab).mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve; }));
    await start();
    const signal = vi.mocked(analyzeLab).mock.calls[0][3];
    fireEvent.change(screen.getByLabelText("Depth"), { target: { value: "4" } });
    expect(signal?.aborted).toBe(true);
    await act(async () => { await vi.advanceTimersByTimeAsync(400); });
    await act(async () => { resolveOld(output(999)); });
    expect(screen.queryByText("999")).not.toBeInTheDocument();
  });

  it("shows analysis failures and recovers on an explicit rerun", async () => {
    vi.mocked(analyzeLab).mockRejectedValueOnce(new Error("Graph unavailable"));
    await start();
    expect(screen.getByRole("alert")).toHaveTextContent("Graph unavailable");
    fireEvent.click(screen.getByRole("button", { name: "Run engine" }));
    await act(async () => { await vi.advanceTimersByTimeAsync(400); });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(analyzeLab).toHaveBeenCalledTimes(2);
  });
});
