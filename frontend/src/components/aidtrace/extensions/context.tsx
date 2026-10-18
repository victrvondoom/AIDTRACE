"use client";

// One canonical workspace state, shared by the globe, the inspector and every extension. The workspace owns it; extensions only read it and ask the workspace
// to change it, so selecting Supplier A on the globe is the same selection Risk Analytics, Connected Graph, Evidence and Governance see.
import { createContext, useContext } from "react";
import { buildLineage, chainOf, decisionState, isUnsafe } from "@/lib/aidtrace-lineage";
import type { MemoryDecision, MemoryRecord } from "@/lib/lab-api";
import type { EvidenceResult, InvestigationResult } from "../automation";
import type { AidtraceData, Selection, ViewId } from "../data";
import type { RunLogEntry } from "../views";

export interface AidtraceContextValue {
  data: AidtraceData;
  selection: Selection;
  select: (s: Selection) => void;
  investigation: InvestigationResult | null;
  evidence: EvidenceResult | null;
  /** The supplier the graph currently recommends, read from the newest valid decision. */
  recommended: string | null;
  view: ViewId;
  runs: RunLogEntry[];
  /** Open an extension in the centre, optionally at one of its pages. The address bar never changes. */
  openExtension: (id: string, path?: string) => void;
}

const Ctx = createContext<AidtraceContextValue | null>(null);
export const AidtraceProvider = Ctx.Provider;
export function useAidtrace(): AidtraceContextValue {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAidtrace must be used inside the AIDTRACE workspace");
  return v;
}

type Maker = NonNullable<AidtraceData["scenario"]>["manufacturers"][number];

export interface SupplierContext {
  /** True when the user picked this supplier; false when it is only the currently recommended one. */
  selected: boolean;
  id: string | null; name: string | null; maker: Maker | undefined;
  memories: MemoryRecord[];
  /** `null` means unknown (the graph holds no memory about this supplier), which is not the same as 0. */
  staleMemories: number | null;
  sources: number | null; unhashedSources: number | null;
  decisions: MemoryDecision[]; blockedDecisions: number | null; pendingReviews: number | null;
  dependents: number | null; dependencies: number | null;
}

const plain = (n: string) => n.replace("Illustrative ", "");

/** Everything the analytics need to say about one supplier, derived from the snapshot, lineage and the latest investigation. No value is invented. */
export function deriveSupplierContext(ctx: Pick<AidtraceContextValue, "data" | "selection" | "investigation" | "recommended">): SupplierContext {
  const { data, selection, investigation, recommended } = ctx;
  const makers = data.scenario?.manufacturers ?? [];
  const picked = selection?.kind === "supplier" ? makers.find((m) => m.id === selection.id) : undefined;
  const maker = picked ?? makers.find((m) => m.name === recommended);
  const base: SupplierContext = { selected: Boolean(picked), id: maker?.id ?? null, name: maker?.name ?? null, maker, memories: [], staleMemories: null, sources: null, unhashedSources: null,
    decisions: [], blockedDecisions: null, pendingReviews: null, dependents: null, dependencies: null };
  const snap = data.snap;
  if (!maker || !snap) return base;
  const needle = plain(maker.name).toLowerCase();
  const memories = snap.memories.filter((m) => m.summary.toLowerCase().includes(needle) || m.claims.some((c) => c.id.includes(maker.name.replace(/ /g, "_"))));
  const lineage = buildLineage(snap);
  const downstream = new Set<string>();
  for (const m of memories) for (const id of chainOf(lineage, m.id).downstream) downstream.add(id);
  const decisions = snap.decisions.filter((d) => downstream.has(d.id));
  const sourceIds = new Set(memories.flatMap((m) => m.sources.map((s) => s.id)));
  const hashed = new Set(memories.flatMap((m) => m.sources.filter((s) => s.content_sha256).map((s) => s.id)));
  const mine = investigation && investigation.supplierId === maker.id ? investigation : null;
  const actionFor = (id: string) => snap.actions.find((a) => a.eligibility.decision_id === id);
  return {
    ...base, memories, decisions,
    staleMemories: memories.length ? memories.filter((m) => isUnsafe(m.status)).length : null,
    sources: memories.length ? sourceIds.size : null, unhashedSources: memories.length ? sourceIds.size - hashed.size : null,
    blockedDecisions: memories.length ? decisions.filter((d) => decisionState(d, actionFor(d.id)).tone === "danger").length : null,
    pendingReviews: memories.length ? decisions.filter((d) => { const s = decisionState(d, actionFor(d.id)).label; return s === "Needs review" || s === "Re-evaluated"; }).length : null,
    dependents: mine ? mine.dependents.length : null, dependencies: mine ? mine.dependencies.length : null,
  };
}
