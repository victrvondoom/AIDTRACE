import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { getDriftDemo, getPendingConflicts, getPendingQuarantine, getSlaReport, getComplianceDashboard, getEvents, getHealthDetailed, runDriftDemo } from "@/lib/api";
import ManagementPage from "./page";

vi.mock("@/lib/api", () => ({
  getToken: vi.fn().mockReturnValue(null), // use-role -> auth.getMe reads it; no token = the signed-out dev default
  // ReasoningWorkspace reads these four on mount; shapes mirror the real response types in @/lib/api.
  getFalkorHealth: vi.fn().mockResolvedValue({ data: { reachable: true, site_graph_exists: true }, source: "live" }),
  getModelCatalog: vi.fn().mockResolvedValue({ data: { models: [], fine_tuning: { status: "not_connected", registry_available: false } }, source: "live" }),
  getValidationCorpusStats: vi.fn().mockResolvedValue({ data: { total_corpus_size: 0, by_entity_type: {}, last_updated_at: null }, source: "live" }),
  getAnnotationStats: vi.fn().mockResolvedValue({ data: { total: 0, corrections_this_week: 0, top_corrected_entity_types: [] }, source: "live" }),
  getDriftDemo: vi.fn().mockResolvedValue({ data: {
    case_id: "DEMO-DRIFT-HV-001", scenario: "synthetic_only", seeded: true,
    source_before: "DEMO-DRIFT-SOP-V1", source_after: "DEMO-DRIFT-SOP-V2",
    sources: [
      { id: "DEMO-DRIFT-SOP-V1", status: "SUPERSEDED", authority_level: 4, verification_status: "VERIFIED", confidence: 0.94, event_time: "2026-10-01T08:00:00Z" },
      { id: "DEMO-DRIFT-SOP-V2", status: "ACTIVE", authority_level: 2, verification_status: "VERIFIED", confidence: 0.99, event_time: "2026-10-18T08:00:00Z" },
    ],
    condition_results: [{ key: "inspection_interval_days", op: "==", value: 180, actual: 90, claim_id: "DEMO-DRIFT-CLAIM-V2", holds: false }],
    impact_paths: [{ node_id: "DEMO-DRIFT-ACTION-001", depth: 5, path: ["DEMO-DRIFT-SOP-V1", "DEMO-DRIFT-CLAIM-V1", "DEMO-DRIFT-MEMORY-001", "DEMO-DRIFT-DECISION-001", "DEMO-DRIFT-PLAN-001", "DEMO-DRIFT-ACTION-001"] }],
    action_eligibility: "SUSPENDED", statuses: { "DEMO-DRIFT-ACTION-001": "SUSPENDED" },
    human_review: { approval_id: "DEMO-DRIFT-APPROVAL-REV-001", approved_revision_id: "DEMO-DRIFT-DECISION-REV-001", approval_status: "VALID_FOR_PRIOR_REVISION", matches_current_revision: false },
    decision_revision: { previous_revision_id: "DEMO-DRIFT-DECISION-REV-001", previous_graph_revision: "a".repeat(64), current_revision_id: "DEMO-DRIFT-DECISION-REV-002", current_graph_revision: "b".repeat(64) },
    audit_chain_hash: "c".repeat(64), external_actions_executed: false,
  }, source: "live" }),
  runDriftDemo: vi.fn(),
  getPendingConflicts: vi.fn().mockResolvedValue({ data: { total: 3, items: [] }, source: "live" }),
  getComplianceDashboard: vi.fn().mockResolvedValue({
    data: { total_gaps: { critical: 2, major: 1, minor: 0 }, by_framework: {}, by_asset_class: {} },
    source: "live",
  }),
  getSlaReport: vi.fn().mockResolvedValue({
    data: {
      checked_at: "2026-07-15T08:00:00Z",
      escalated_this_run: { conflicts: 0, quarantine_items: 0 },
      overdue_conflicts: [{ conflict_id: "c1", track: "technical", asset_id: "P-101", sla_deadline: "2026-07-14T08:00:00Z", escalated_at: null, status: "open" }],
      overdue_conflicts_total: 1,
      overdue_quarantine_items: [{ item_id: "q1", asset_id: null, input_type: "field_note", sla_due_at: "2026-07-13T08:00:00Z", escalated_at: null }],
      overdue_quarantine_total: 1,
    },
    source: "live",
  }),
  getPendingQuarantine: vi.fn().mockResolvedValue({ data: { items: [], total: 5 }, source: "live" }),
  getEvents: vi.fn().mockResolvedValue({
    data: {
      items: [{ event_id: "e1", event_type: "work_order_created", occurred_at: "2026-07-15T07:00:00Z", priority: "high", payload: {}, acknowledged: false }],
      total: 1,
    },
    source: "live",
  }),
  getHealthDetailed: vi.fn().mockResolvedValue({
    data: {
      overall: "degraded",
      checked_at: "2026-07-15T08:00:00Z",
      services: [{ name: "Neo4j", status: "healthy", latency_ms: 12 }, { name: "Qdrant", status: "degraded" }],
    },
    source: "live",
  }),
}));

describe("ManagementPage", () => {
  afterEach(cleanup);

  it("keeps the overview decision flow responsive and data-driven", async () => {
    render(<ManagementPage />);

    expect(screen.getByTestId("overview-workspace")).toHaveClass("max-w-[1400px]");
    await waitFor(() => expect(screen.getByTestId("overview-health")).toHaveTextContent("Qdrant"));
    expect(screen.getByTestId("overview-kpis")).toHaveClass("grid-cols-2", "lg:grid-cols-4");
    expect(screen.getByTestId("overview-priority-layout")).toHaveClass("lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]");
    const proof = await screen.findByTestId("overview-evidence-proof");
    expect(proof).toHaveTextContent("Earlier procedure");
    expect(proof).toHaveTextContent("180 days");
    expect(proof).toHaveTextContent("90 days");
    expect(proof).toHaveTextContent("SUSPENDED");
    expect(screen.getByTestId("overview-health")).toHaveTextContent("Degraded");
    expect(screen.getByRole("link", { name: /network state.*degraded/i })).toHaveAttribute("href", "/overview/plant-state");

    // KPI deep links (spec §4).
    expect(screen.getByRole("link", { name: /open conflicts/i })).toHaveAttribute("href", "/governance/conflicts");
    expect(screen.getByRole("link", { name: /overdue sla items/i })).toHaveAttribute("href", "/governance/sla");
    expect(screen.getByRole("link", { name: /critical gaps/i })).toHaveAttribute("href", "/compliance");

    // Attention ranking (spec §5): overdue conflict first, then quarantine, then gaps.
    const attention = screen.getByTestId("overview-needs-attention");
    expect(attention).toHaveTextContent("Overdue conflict, Technical");
    expect(attention).toHaveTextContent("Overdue quarantine, Field note");
    expect(attention).toHaveTextContent("2 critical compliance gaps");

    // Signals feed rows deep-link to the event.
    const signals = screen.getByTestId("overview-recent-signals");
    expect(signals.querySelector('a[href="/events/e1"]')).not.toBeNull();
    expect(signals.querySelector('a[href="/events/e1"] span[title="Work Order Created"]')).toHaveClass("whitespace-normal", "break-words");
  });

  it("re-reads persisted evidence after replay to keep full source provenance visible", async () => {
    vi.mocked(runDriftDemo).mockResolvedValueOnce({} as never);
    render(<ManagementPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Replay proof" }));

    await waitFor(() => expect(getDriftDemo).toHaveBeenCalledTimes(2));
    expect(vi.mocked(runDriftDemo).mock.invocationCallOrder[0]).toBeLessThan(
      vi.mocked(getDriftDemo).mock.invocationCallOrder[1],
    );
    expect(await screen.findByText(/Verified graph versions · authority 4/)).toHaveTextContent("authority 4 → 2");
  });

  it("keeps available data visible and identifies sources that fail", async () => {
    vi.mocked(getPendingConflicts).mockRejectedValueOnce(new Error("conflict service unavailable"));
    render(<ManagementPage />);

    await waitFor(() => expect(screen.getByTestId("overview-partial")).toHaveTextContent("Open conflicts"));
    expect(screen.queryByTestId("overview-error")).not.toBeInTheDocument();
    expect(screen.getByTestId("overview-evidence-proof")).toHaveTextContent("180 days");
    expect(screen.getByTestId("overview-kpis")).toBeInTheDocument();
  });

  it("surfaces a retry-able error card when all overview sources fail", async () => {
    vi.mocked(getPendingConflicts).mockRejectedValueOnce(new Error("conflict service unavailable"));
    vi.mocked(getPendingQuarantine).mockRejectedValueOnce(new Error("quarantine service unavailable"));
    vi.mocked(getSlaReport).mockRejectedValueOnce(new Error("SLA service unavailable"));
    vi.mocked(getComplianceDashboard).mockRejectedValueOnce(new Error("compliance service unavailable"));
    vi.mocked(getEvents).mockRejectedValueOnce(new Error("events service unavailable"));
    render(<ManagementPage />);

    await waitFor(() => expect(screen.getByTestId("overview-error")).toHaveTextContent("Overview services unavailable"));
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("distinguishes unavailable plant health from a healthy state", async () => {
    vi.mocked(getHealthDetailed).mockRejectedValueOnce(new Error("health unavailable"));
    render(<ManagementPage />);

    await waitFor(() => expect(screen.getByRole("link", { name: /network state.*unavailable/i })).toBeInTheDocument());
  });
});
