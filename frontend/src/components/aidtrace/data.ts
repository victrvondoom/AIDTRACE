"use client";

// Shared data for the AIDTRACE workspace. Every value comes from an existing backend route (GreenChain scoring, the FalkorDB agent-memory snapshot,
// Graph Lab). A failing source reports its own error and leaves the others working; nothing is replaced by an invented value.
import { useCallback, useEffect, useMemo, useState } from "react";
import { apiResultToScenario } from "@/lib/greenchain/api-to-scenario";
import type { ManufacturerResult } from "@/lib/greenchain/api";
import type { ScenarioSearchCsv } from "@/lib/greenchain/csv-to-search";
import { applyScoringLens, DEFAULT_SCORING_WEIGHTS } from "@/lib/greenchain/scoring-lens";
import type { SupplyScenario } from "@/lib/greenchain/supply-chain-scenario";
import type { LabGraph } from "@/lib/graph-layout";
import { buildLineage, isUnsafe, type Lineage } from "@/lib/aidtrace-lineage";
import {
  analyzeLab, greenchainDemo, greenchainHealth, greenchainWhatIf, memoryHandoffs, memorySnapshot,
  type GreenchainDemo, type GreenchainHealth, type Handoff, type MemorySnapshot,
} from "@/lib/lab-api";

export type ViewId = "globe" | "graph" | "lineage" | "workflow" | "memory";
export type Selection = { kind: "supplier" | "node" | "source" | "claim" | "memory" | "decision" | "action"; id: string; label: string } | null;

const COMPONENT = "Corrugated packaging";

/** The graph can return records written by older flows (for example the drift demo) with fields missing. Fill them with explicit "unknown" values
 *  rather than letting a view crash or presenting an invented value. */
export function normalizeSnapshot(raw: MemorySnapshot): MemorySnapshot {
  return {
    ...raw,
    memories: (raw.memories ?? []).map((m) => {
      const sources = m.sources ?? [];
      return { ...m, claims: m.claims ?? [], sources, verification_status: m.verification_status ?? "UNKNOWN", confidence: m.confidence ?? 0,
        independent_sources: m.independent_sources ?? new Set(sources.map((x) => x.content_sha256 ?? x.id)).size, recorded_at: m.recorded_at ?? "", last_verified_at: m.last_verified_at ?? "",
        blocked_reason: m.blocked_reason ?? null, agent_id: m.agent_id ?? "unknown agent", summary: m.summary ?? m.id };
    }),
    decisions: (raw.decisions ?? []).map((d) => ({ ...d, dependency_ids: d.dependency_ids ?? [], revision_n: d.revision_n ?? 0, summary: d.summary ?? d.id })),
    actions: (raw.actions ?? []).map((a) => ({ ...a, summary: a.summary ?? a.id,
      eligibility: a.eligibility ?? { eligible: false, reasons: ["eligibility unavailable"], decision_id: null, approval_current: false } })),
    sources: (raw.sources ?? []).map((x) => ({ ...x, title: x.title ?? x.id, version_label: x.version_label ?? "version unknown", authority_level: x.authority_level ?? 0 })),
    approvals: raw.approvals ?? [], changes: raw.changes ?? [], agents: raw.agents ?? [],
  };
}
const message = (e: unknown, fallback: string) => (e instanceof Error ? e.message : fallback);

export interface AidtraceData {
  demo: GreenchainDemo | null; health: GreenchainHealth | null; snap: MemorySnapshot | null; handoffs: Handoff[];
  scenario: SupplyScenario | null; lineage: Lineage | null;
  errors: { supply?: string; memory?: string };
  loading: boolean;
  refreshMemory: () => Promise<void>;
}

export function useAidtraceData(): AidtraceData {
  const [demo, setDemo] = useState<GreenchainDemo | null>(null);
  const [health, setHealth] = useState<GreenchainHealth | null>(null);
  const [snap, setSnap] = useState<MemorySnapshot | null>(null);
  const [handoffs, setHandoffs] = useState<Handoff[]>([]);
  const [errors, setErrors] = useState<AidtraceData["errors"]>({});
  const [loading, setLoading] = useState(true);

  const refreshMemory = useCallback(async () => {
    try {
      const [s, h] = await Promise.all([memorySnapshot(), memoryHandoffs()]);
      setSnap(normalizeSnapshot(s)); setHandoffs(h.handoffs ?? []); setErrors((e) => ({ ...e, memory: undefined }));
    } catch (e) { setErrors((x) => ({ ...x, memory: message(e, "Agent memory could not be read.") })); }
  }, []);

  useEffect(() => {
    let live = true;
    const supply = Promise.all([greenchainDemo("sea"), greenchainHealth()])
      .then(([d, h]) => { if (live) { setDemo(d); setHealth(h); } })
      .catch((e: unknown) => { if (live) setErrors((x) => ({ ...x, supply: message(e, "GreenChain could not load.") })); });
    const memory = Promise.all([memorySnapshot(), memoryHandoffs()])
      .then(([s, h]) => { if (live) { setSnap(normalizeSnapshot(s)); setHandoffs(h.handoffs ?? []); } })
      .catch((e: unknown) => { if (live) setErrors((x) => ({ ...x, memory: message(e, "Agent memory could not be read.") })); });
    void Promise.all([supply, memory]).then(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, []);

  const scenario = useMemo(() => {
    if (!demo) return null;
    const current = demo.results.find((r) => (r as { is_current?: boolean }).is_current) as ManufacturerResult | undefined;
    const csv: ScenarioSearchCsv = {
      product: demo.product, destination: demo.destination, quantity: 10000, unit: "units", targetCount: null, transportMode: "sea",
      components: [{ component: COMPONENT, currentManufacturer: current?.name ?? "Incumbent", currentCountry: current?.country ?? "CN", currentCity: null,
        currentCertifications: current?.certifications ?? [], currentDisclosureStatus: "none", currentRenewablePct: null, currentRevenueUsdM: null, currentWebsite: null }],
    };
    const base = apiResultToScenario({ product: demo.product, destination: demo.destination, transport_mode: "sea", countries: [], duration_seconds: 0,
      count: demo.results.length, results: demo.results as unknown as ManufacturerResult[] }, csv);
    return applyScoringLens(base, { transportMode: "sea", weights: DEFAULT_SCORING_WEIGHTS });
  }, [demo]);

  const lineage = useMemo(() => (snap ? buildLineage(snap) : null), [snap]);
  return { demo, health, snap, handoffs, scenario, lineage, errors, loading, refreshMemory };
}

// ---- Connected-risk propagation (Graph Lab blast_radius on the supplier graph) -------------------------------------------------------------

export interface Impacted { id: string; label: string; type: string; mark: string }
export interface Propagation { changed: string; dependents: Impacted[]; dependencies: Impacted[] }

/** Which records depend on `nodeId` (reverse) and which it depends on (forward), traversed by the Graph Lab engine over the graph. */
export async function propagate(graph: LabGraph, nodeId: string): Promise<Propagation> {
  const byId = new Map(graph.nodes.map((n) => [n.id, n]));
  const run = async (direction: "reverse" | "forward") => {
    const r = await analyzeLab("blast_radius", { graph }, { changed: [nodeId], direction, max_depth: 6 });
    return Object.entries(r.result.node_marks).filter(([id]) => id !== nodeId).map(([id, mark]) => ({ id, label: byId.get(id)?.label ?? id, type: byId.get(id)?.type ?? "Record", mark }));
  };
  const [dependents, dependencies] = await Promise.all([run("reverse"), run("forward")]);
  return { changed: nodeId, dependents, dependencies };
}

// ---- Question routing ------------------------------------------------------------------------------------------------------------------
// There is no language model here. A question is routed to the engine that can answer it; anything else is declined, with what is supported.

export interface AgentAnswer { question: string; at: string; route: string; ok: boolean; text: string; lines: string[]; select?: Selection }

export const SUGGESTED_QUESTIONS = [
  "Which suppliers become risky if this component manufacturer is compromised?",
  "Which approved procurement decisions rely on outdated evidence?",
  "Which facilities would be affected by this supplier disruption?",
  "What did the agent previously learn about this supplier?",
  "Which alternative supplier has lower operational and environmental risk?",
];

const plain = (name: string) => name.replace("Illustrative ", "");

export async function askAgent(question: string, ctx: { demo: GreenchainDemo | null; scenario: SupplyScenario | null; snap: MemorySnapshot | null; selected: Selection }): Promise<AgentAnswer> {
  const q = question.toLowerCase();
  const at = new Date().toISOString();
  const done = (route: string, text: string, lines: string[] = [], ok = true, select?: Selection): AgentAnswer => ({ question, at, route, ok, text, lines, select });
  const suppliers = ctx.scenario?.manufacturers ?? [];
  const mentioned = suppliers.find((m) => q.includes(plain(m.name).toLowerCase()))
    ?? (ctx.selected && (ctx.selected.kind === "supplier" || ctx.selected.kind === "node") ? suppliers.find((m) => m.name === ctx.selected?.label) : undefined);

  try {
    if (/outdated|stale|rely|relies|invalid|approv/.test(q) && ctx.snap) {
      const bad = ctx.snap.decisions.filter((d) => isUnsafe(d.status));
      const blocked = ctx.snap.actions.filter((a) => !a.eligibility.eligible);
      const lines = [
        ...bad.map((d) => `Decision “${d.summary}” is ${d.status.toLowerCase()} (revision ${d.revision_n}).`),
        ...blocked.map((a) => `Action “${a.summary}” cannot be approved: ${a.eligibility.reasons[0] ?? "not eligible"}.`),
      ];
      return done("FalkorDB agent memory · /agent-memory/snapshot", lines.length ? `${bad.length} decision(s) and ${blocked.length} action(s) no longer stand on current evidence.` : "No decision or action in the graph is currently stale or blocked.", lines);
    }
    if (/previously|learn|remember|memory|know about/.test(q) && ctx.snap) {
      const needle = mentioned ? plain(mentioned.name).toLowerCase() : null;
      const mems = ctx.snap.memories.filter((m) => !needle || m.summary.toLowerCase().includes(needle));
      const lines = mems.slice(0, 8).map((m) => `${m.status.toLowerCase()} · ${m.summary} — ${m.independent_sources} independent source(s), ${m.verification_status.toLowerCase()}${m.blocked_reason ? `, blocked: ${m.blocked_reason}` : ""}`);
      const first = mems[0];
      return done("FalkorDB agent memory · /agent-memory/snapshot", mems.length ? `${mems.length} memor${mems.length === 1 ? "y" : "ies"}${mentioned ? ` mention ${plain(mentioned.name)}` : " recorded in this site's graph"}.` : "Nothing is stored in agent memory yet. Run “Record decision to memory” in the Workflow view.", lines, true, first ? { kind: "memory", id: first.id, label: first.summary } : undefined);
    }
    if (/alternative|lower|best|cleaner|greener/.test(q) && suppliers.length) {
      const ranked = [...suppliers].sort((a, b) => a.ecoScore - b.ecoScore);
      return done("GreenChain scoring · modelled intensities", `Under the default weights and sea transport, ${plain(ranked[0].name)} ranks first. Environmental score only: operational and cyber risk are not part of this ranking.`,
        ranked.map((m, i) => `${i + 1}. ${plain(m.name)} (${m.location.countryCode}) — eco score ${m.ecoScore.toFixed(0)}, ${m.manufacturingEmissionsTco2e.q50.toFixed(0)} tCO2e manufacturing`),
        true, { kind: "supplier", id: ranked[0].id, label: ranked[0].name });
    }
    if (/facilit|disrupt|leave|leaves|remove|lose/.test(q) && ctx.demo) {
      const target = mentioned ?? suppliers.find((m) => m.isCurrent) ?? suppliers[0];
      if (!target) return done("GreenChain what-if", "No supplier is loaded.", [], false);
      const w = await greenchainWhatIf(target.name, "sea");
      return done("GreenChain what-if · /greenchain/whatif/remove-supplier", `Without ${plain(w.removed)}, the top choice ${w.recommendation_changes ? `changes from ${w.top_before} to ${w.top_after}` : `stays ${w.top_after}`}; ${w.rank_changes.length} supplier rank(s) change.`,
        w.rank_changes.map((r) => `${plain(r.name)}: rank ${r.from ?? "—"} → ${r.to}`), true, { kind: "supplier", id: target.id, label: target.name });
    }
    if (/compromis|risky|risk|cyber|propagat|depend|breach/.test(q) && ctx.demo) {
      const node = mentioned
        ? ctx.demo.graph.nodes.find((n) => n.type === "Supplier" && n.label === mentioned.name)
        : ctx.selected?.kind === "node" ? ctx.demo.graph.nodes.find((n) => n.id === ctx.selected?.id) : ctx.demo.graph.nodes.find((n) => n.type === "Supplier");
      if (!node) return done("Graph Lab · blast_radius", "No matching supplier node in the graph.", [], false);
      const p = await propagate(ctx.demo.graph, node.id);
      const lines = [...p.dependents.map((x) => `Depends on ${node.label}: ${x.label} (${x.type})`), ...p.dependencies.map((x) => `${node.label} depends on: ${x.label} (${x.type})`)].slice(0, 12);
      return done("Graph Lab blast_radius over the supplier graph", `${p.dependents.length} record(s) depend on ${node.label}; it depends on ${p.dependencies.length}. Model-only: no live security feed is connected, so this shows reach, not an observed compromise.`, lines, true, { kind: "node", id: node.id, label: node.label });
    }
  } catch (e) {
    return done("backend", `The backend could not answer: ${message(e, "request failed")}.`, [], false);
  }
  return done("not supported", "AIDTRACE answers from its graph engines rather than a language model. Ask about compromised suppliers, outdated approvals, affected facilities, what the agent previously learned, or lower-risk alternatives.", SUGGESTED_QUESTIONS, false);
}
