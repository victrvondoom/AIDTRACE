import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { MemorySnapshot } from "@/lib/lab-api";
import { buildLineage } from "@/lib/aidtrace-lineage";
import type { AidtraceData } from "../data";

vi.mock("next/dynamic", () => ({ default: () => () => null }));
vi.mock("@/features/feature-host", () => ({
  Boundary: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  FEATURES: ["greenchain", "simulations", "resolveai", "consumer", "cybersecurity", "fraud", "memory", "evidence-drift", "graph", "agents", "reports", "capabilities"]
    .map((id) => ({ id, name: id, status: "INTEGRATED_TESTED", category: "x", backend: "x", summary: "", render: () => null })),
}));

import { deriveSupplierContext } from "./context";
import { ExtensionLauncher } from "./launcher";
import { EXTENSIONS, EXTENSION_CATEGORIES, NEEDS_EXTERNAL_STORES, extensionById, isAvailable, searchExtensions, tabForPath } from "./registry";
import { LEGACY_ROUTES, extensionForPath, resolveRoute } from "./legacy-routes";

describe("legacy route table", () => {
  it("resolves params, query strings and specific-before-generic patterns", () => {
    expect(resolveRoute("/assets/register")?.route.pattern).toBe("/assets/register");
    expect(resolveRoute("/assets/EQ-101")).toMatchObject({ params: { id: "EQ-101" }, route: { pattern: "/assets/:id", serverPage: true } });
    expect(resolveRoute("/documents/D1/topology")?.route.pattern).toBe("/documents/:id/topology");
    expect(resolveRoute("/documents?page=2")).toMatchObject({ query: { page: "2" }, path: "/documents?page=2" });
    expect(resolveRoute("/governance/conflicts/C-9/")?.params).toEqual({ id: "C-9" });
  });

  it("returns null for anything that is not a migrated page", () => {
    expect(resolveRoute("/not-a-page")).toBeNull();
    expect(extensionForPath("/login")).toBeNull();
  });

  it("marks exactly the async server pages", () => {
    expect(LEGACY_ROUTES.filter((r) => r.serverPage).map((r) => r.pattern).sort()).toEqual(
      ["/assets", "/assets/:id", "/briefs", "/briefs/:id", "/documents", "/documents/:id", "/offboarding"].sort());
  });
});

describe("extension registry", () => {
  it("has unique ids and every extension sits in a known category", () => {
    const ids = EXTENSIONS.map((e) => e.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const e of EXTENSIONS) expect(EXTENSION_CATEGORIES).toContain(e.category);
    for (const c of EXTENSION_CATEGORIES) expect(EXTENSIONS.some((e) => e.category === c)).toBe(true);
  });

  it("gives every tab exactly one source: a migrated page or a native body", () => {
    for (const e of EXTENSIONS) {
      expect(e.tabs.length).toBeGreaterThan(0);
      for (const t of e.tabs) expect(Boolean(t.path) !== Boolean(t.body)).toBe(true);
    }
  });

  it("keeps every tab path and every migrated route owned by a registered extension", () => {
    for (const e of EXTENSIONS) for (const t of e.tabs) if (t.path) expect(extensionForPath(t.path), `${e.id}:${t.path}`).toBe(e.id);
    for (const r of LEGACY_ROUTES) expect(extensionById(r.extension), r.pattern).not.toBeNull();
  });

  it("covers every original capability the brief names", () => {
    const ids = EXTENSIONS.map((e) => e.id);
    for (const id of ["greenchain", "supplier-registry", "risk-analytics", "assistant", "rca", "connected-graph", "events", "evidence-vault", "coverage", "knowledge-transfer", "projects",
      "governance", "audit", "compliance", "notices", "resolveai", "cyberflow", "track1", "agent-memory", "evidence-drift"]) expect(ids).toContain(id);
  });

  it("searches title, keywords and description, best match first", () => {
    expect(searchExtensions(EXTENSIONS, "").length).toBe(EXTENSIONS.length);
    expect(searchExtensions(EXTENSIONS, "oisd").map((e) => e.id)).toContain("compliance");
    expect(searchExtensions(EXTENSIONS, "upload")[0].id).toBe("evidence-vault");
    expect(searchExtensions(EXTENSIONS, "zzzz-no-such-thing")).toEqual([]);
  });

  it("finds the tab for a path by the longest matching prefix", () => {
    const gov = extensionById("governance")!;
    expect(tabForPath(gov, "/governance")?.id).toBe("queues");
    expect(tabForPath(gov, "/governance/conflicts/C-1")?.id).toBe("conflicts");
    expect(tabForPath(gov, "/assets")).toBeNull();
  });

  it("applies the same role rules the old pages had", () => {
    const compliance = extensionById("compliance")!;
    expect(isAvailable(compliance, "engineer")).toBe(true);
    expect(isAvailable(extensionById("governance")!, "compliance")).toBe(false);
    expect(isAvailable(extensionById("system-health")!, "engineer")).toBe(false);
    expect(isAvailable(extensionById("system-health")!, "admin")).toBe(true);
  });

  it("states honest scope for engines that are narrower than their name", () => {
    expect(extensionById("compliance")?.scope).toMatch(/plant regulations/i);
    expect(extensionById("rca")?.scope).toMatch(/not been adapted/i);
    expect(extensionById("cyberflow")).toMatchObject({ status: "partial" });
  });
});

describe("ExtensionLauncher", () => {
  afterEach(cleanup);

  it("is closed until opened, then lists categories and filters as you type", () => {
    // The full registry, so search and categories are checked over every page, including the ones the default list hides.
    const { rerender } = render(<ExtensionLauncher open={false} role="engineer" onClose={() => {}} onSelect={() => {}} extensions={EXTENSIONS} />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    rerender(<ExtensionLauncher open role="engineer" onClose={() => {}} onSelect={() => {}} extensions={EXTENSIONS} />);
    expect(screen.getByRole("dialog", { name: "Extensions" })).toBeInTheDocument();
    for (const c of EXTENSION_CATEGORIES) expect(screen.getByRole("region", { name: c })).toBeInTheDocument();
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "audit pack" } });
    expect(screen.getByRole("button", { name: /Compliance & Controls/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /GreenChain/ })).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "zzzz" } });
    expect(screen.getByText(/No extension matches/)).toBeInTheDocument();
  });

  it("selects an extension, closes on Escape, and disables what the role cannot open", () => {
    const onSelect = vi.fn(); const onClose = vi.fn();
    render(<ExtensionLauncher open role="compliance" onClose={onClose} onSelect={onSelect} extensions={EXTENSIONS} />);
    expect(screen.getByRole("button", { name: /Governance/ })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: /Compliance & Controls/ }));
    expect(onSelect).toHaveBeenCalledWith("compliance");
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });

  // Pages whose stores are not running here are left out of the default list, and the single workflow page is listed instead.
  it("lists the workflow page and hides the pages that need external stores", () => {
    render(<ExtensionLauncher open role="engineer" onClose={() => {}} onSelect={() => {}} />);
    expect(screen.getByRole("button", { name: /Investigation Workflow/ })).toBeInTheDocument();
    for (const id of NEEDS_EXTERNAL_STORES) {
      const title = extensionById(id)?.title ?? id;
      expect(screen.queryByRole("button", { name: new RegExp(`^${title.replace(/[&()]/g, "\\$&")}`) }), id).not.toBeInTheDocument();
    }
    expect(extensionById("compliance")).not.toBeNull();
  });
});

describe("shared supplier context", () => {
  const maker = (id: string, name: string) => ({ id, name, isCurrent: false, ecoScore: 10, componentId: "c", location: { countryCode: "PT", country: "Portugal" },
    manufacturingEmissionsTco2e: { q10: 1, q50: 5, q90: 9 }, transportEmissionsTco2e: 1, certifications: [] });
  const snap: MemorySnapshot = {
    sources: [], approvals: [], changes: [], agents: [],
    memories: [{ id: "gc:s1:mem:1", memory_kind: "SEMANTIC", summary: "Illustrative Packaging D ranks first", agent_id: "a", status: "STALE", verification_status: "VERIFIED", confidence: 0.9, independent_sources: 1,
      recorded_at: "", last_verified_at: "", investigation_ref: "", blocked_reason: null, claims: [{ id: "gc:s1:est:Illustrative_Packaging_D:v1", fact_key: "k", fact_value: 1, status: "ACTIVE" }],
      sources: [{ id: "s1", status: "ACTIVE", document_id: null, content_sha256: "h" }, { id: "s2", status: "ACTIVE", document_id: null, content_sha256: null }] }],
    decisions: [{ id: "gc:s1:d1", summary: "Recommend D", status: "INVALIDATED", revision_n: 1, dependency_ids: ["gc:s1:mem:1"], revision_id: "r", graph_revision: "g" }],
    actions: [{ id: "a1", summary: "Order", status: "SUSPENDED", eligibility: { eligible: false, reasons: ["stale"], decision_id: "gc:s1:d1", approval_current: false } }],
  };
  const data = (over: Partial<AidtraceData> = {}): AidtraceData => ({
    demo: null, health: null, snap, handoffs: [], site: null, lineage: buildLineage(snap), errors: {}, loading: false, refreshMemory: async () => ({ snap, site: null }),
    scenario: { manufacturers: [maker("m-d", "Illustrative Packaging D"), maker("m-b", "Illustrative Packaging B")], components: [] } as unknown as AidtraceData["scenario"], ...over,
  });

  it("derives a selected supplier's analytics from the graph, counting only what exists", () => {
    const c = deriveSupplierContext({ data: data(), selection: { kind: "supplier", id: "m-d", label: "Illustrative Packaging D" }, investigation: null, recommended: null });
    expect(c).toMatchObject({ selected: true, name: "Illustrative Packaging D", staleMemories: 1, sources: 2, unhashedSources: 1, blockedDecisions: 1, pendingReviews: 0 });
    expect(c.dependents).toBeNull();
  });

  it("reports unknown, not zero, for a supplier the graph knows nothing about", () => {
    const c = deriveSupplierContext({ data: data(), selection: { kind: "supplier", id: "m-b", label: "Illustrative Packaging B" }, investigation: null, recommended: null });
    expect(c).toMatchObject({ selected: true, staleMemories: null, sources: null, blockedDecisions: null, pendingReviews: null });
  });

  it("falls back to the recommended supplier when nothing is selected, and says so", () => {
    const c = deriveSupplierContext({ data: data(), selection: null, investigation: null, recommended: "Illustrative Packaging D" });
    expect(c).toMatchObject({ selected: false, name: "Illustrative Packaging D", staleMemories: 1 });
  });
});
