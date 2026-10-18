"use client";

// The five switchable views of the AIDTRACE centre. They share one selection and one data object owned by the workspace, so switching
// views never reloads data or loses the active investigation.
import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { InteractiveGlobe } from "@/components/features/greenchain/InteractiveGlobe";
import { GraphViews } from "@/components/graph-views";
import { Button, StatusBadge } from "@/components/ui";
import type { LabGraph } from "@/lib/graph-layout";
import type { SupplyScenarioSelectableNodeId } from "@/lib/greenchain/supply-chain-scenario";
import { chainOf, isUnsafe, LINEAGE_COLUMNS, LINEAGE_LABELS, type LineageNode } from "@/lib/aidtrace-lineage";
import {
  getSiteGraph, memoryApprove, memoryImpactPreview, memoryPreviewRevision, memoryRecordScenario, memoryRevise,
  type GcPreview, type GcRevised, type ImpactPreview,
} from "@/lib/lab-api";
import type { AidtraceData, Selection } from "./data";

const CesiumGlobe = dynamic(() => import("@/components/features/greenchain/CesiumGlobe").then((m) => m.CesiumGlobe), {
  ssr: false,
  loading: () => <p role="status" className="grid size-full place-items-center text-caption text-muted">Loading satellite globe…</p>,
});

type Tone = "verified" | "danger" | "caution" | "neutral";
export const toneOf = (status: string): Tone => (isUnsafe(status) ? "danger" : /VALID|ACTIVE|APPROVED|ELIGIBLE/i.test(status) ? "verified" : "caution");
const plain = (name: string) => name.replace("Illustrative ", "");
const when = (iso: string | undefined) => (iso ? iso.slice(0, 16).replace("T", " ") : "—");
const scenarioOf = (id: string) => /^gc:([^:]+):/.exec(id)?.[1] ?? null;
const message = (e: unknown) => (e instanceof Error ? e.message : "The request failed.");

interface ViewProps { data: AidtraceData; selection: Selection; onSelect: (s: Selection) => void }

function Empty({ children }: { children: React.ReactNode }) {
  return <div className="grid size-full place-items-center p-8 text-center text-caption text-muted"><div className="max-w-md space-y-3">{children}</div></div>;
}

/** Records the GreenChain decision as evidence-backed agent memory: the starting point for lineage, memory and re-evaluation. */
export function RecordButton({ data, label = "Record decision to memory" }: { data: AidtraceData; label?: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function record() {
    setBusy(true); setError(null);
    try { await memoryRecordScenario("sea"); await data.refreshMemory(); } catch (e) { setError(message(e)); } finally { setBusy(false); }
  }
  return <span className="inline-flex flex-col items-start gap-1"><Button variant="primary" disabled={busy} onClick={() => void record()}>{busy ? "Recording…" : label}</Button>{error && <span role="alert" className="text-micro text-danger">{error}</span>}</span>;
}

// ---- Globe -----------------------------------------------------------------------------------------------------------------------------

export function GlobeView({ data, selection, onSelect }: ViewProps) {
  const [hovered, setHovered] = useState<SupplyScenarioSelectableNodeId | null>(null);
  const [fallback, setFallback] = useState<string | null>(null);
  const scenario = data.scenario;
  const ranked = useMemo(() => (scenario ? [...scenario.manufacturers].sort((a, b) => a.ecoScore - b.ecoScore) : []), [scenario]);
  const best = useMemo(() => (ranked[0] ? { [ranked[0].componentId]: ranked[0].id } : {}), [ranked]);
  const visible = useMemo(() => Object.fromEntries((scenario?.components ?? []).map((c) => [c.id, true])), [scenario]);
  if (data.errors.supply) return <Empty><p role="alert" className="text-danger">{data.errors.supply}</p><p>The globe needs the GreenChain service. Other views still work.</p></Empty>;
  if (!scenario) return <Empty><p role="status">Loading supplier locations…</p></Empty>;
  const selectedId = selection?.kind === "supplier" ? (selection.id as SupplyScenarioSelectableNodeId) : null;
  const pick = (id: SupplyScenarioSelectableNodeId | null) => {
    const m = id ? scenario.manufacturers.find((x) => x.id === id) : undefined;
    onSelect(m ? { kind: "supplier", id: m.id, label: m.name } : null);
  };
  const globeProps = { scenario, bestEcoManufacturerByComponent: best, routeVisibleByComponent: visible, selectedNodeId: selectedId, hoveredNodeId: hovered, onHoverNode: setHovered, onSelectNode: pick, className: "size-full" };
  return (
    <div className="relative size-full" aria-label="Interactive globe of supplier locations">
      {fallback ? (
        <div className="flex size-full flex-col">
          <p role="status" className="border-b border-line bg-surface p-2 text-micro text-muted">{fallback} Showing the schematic globe instead.</p>
          <div className="min-h-0 flex-1"><InteractiveGlobe {...globeProps} pinnedManufacturerByComponent={{}} /></div>
        </div>
      ) : <CesiumGlobe {...globeProps} onUnsupported={setFallback} />}
    </div>
  );
}

// ---- Graph -----------------------------------------------------------------------------------------------------------------------------

export function GraphView({ data, selection, onSelect }: ViewProps) {
  const [source, setSource] = useState<"scenario" | "site">("scenario");
  const [site, setSite] = useState<{ graph: LabGraph; empty: boolean; truncated: boolean } | null>(null);
  const [siteError, setSiteError] = useState<string | null>(null);
  useEffect(() => {
    if (source !== "site" || site) return;
    let live = true;
    getSiteGraph().then((r) => { if (live) setSite(r.data); }).catch((e: unknown) => { if (live) { setSiteError(message(e)); setSource("scenario"); } });
    return () => { live = false; };
  }, [source, site]);
  const graph = source === "site" && site && !site.empty ? site.graph : data.demo?.graph ?? null;
  if (data.errors.supply && !graph) return <Empty><p role="alert" className="text-danger">{data.errors.supply}</p></Empty>;
  if (!graph) return <Empty><p role="status">Loading the supplier graph…</p></Empty>;
  const supplierNode = selection?.kind === "supplier" ? graph.nodes.find((n) => n.type === "Supplier" && n.label === selection.label)?.id ?? null : null;
  const selectedId = selection?.kind === "node" ? selection.id : supplierNode;
  function pick(id: string) {
    const node = graph?.nodes.find((n) => n.id === id);
    if (!node) return;
    const m = node.type === "Supplier" ? data.scenario?.manufacturers.find((x) => x.name === node.label) : undefined;
    onSelect(m ? { kind: "supplier", id: m.id, label: m.name } : { kind: "node", id: node.id, label: node.label });
  }
  return (
    <div className="flex size-full flex-col overflow-y-auto p-3">
      <div className="mb-2 flex flex-wrap items-center gap-2 text-micro text-muted">
        <Button aria-pressed={source === "scenario"} variant={source === "scenario" ? "primary" : "ghost"} onClick={() => setSource("scenario")}>Supplier graph</Button>
        <Button aria-pressed={source === "site"} variant={source === "site" ? "primary" : "ghost"} onClick={() => setSource("site")}>Persisted FalkorDB graph</Button>
        {source === "site" && site?.empty && <span>Nothing is persisted yet, so the supplier graph is shown. Use “Save to FalkorDB” in the GreenChain extension.</span>}
        {site?.truncated && <span>Truncated to the engine limit.</span>}
        {siteError && <span role="alert" className="text-danger">{siteError}</span>}
      </div>
      <GraphViews graph={graph} selected={selectedId} onSelect={pick} />
    </div>
  );
}

// ---- Lineage ---------------------------------------------------------------------------------------------------------------------------

const CARD_W = 168, CARD_H = 58, GAP = 10, COL_GAP = 36, TOP = 34;

export function LineageView({ data, selection, onSelect }: ViewProps) {
  const lineage = data.lineage;
  if (data.errors.memory) return <Empty><p role="alert" className="text-danger">{data.errors.memory}</p><p>Lineage is read from the agent-memory graph.</p></Empty>;
  if (!lineage) return <Empty><p role="status">Reading the evidence graph…</p></Empty>;
  if (!lineage.nodes.length) return <Empty><p className="text-body font-semibold text-ink">No evidence lineage yet</p><p>Lineage is read from the site graph. Record the supplier decision so its sources, claims and memory are written there.</p><RecordButton data={data} /></Empty>;
  const cols = LINEAGE_COLUMNS.map((kind) => lineage.nodes.filter((n) => n.kind === kind));
  const pos = new Map<string, { x: number; y: number }>();
  cols.forEach((nodes, c) => nodes.forEach((n, r) => pos.set(n.id, { x: c * (CARD_W + COL_GAP), y: TOP + r * (CARD_H + GAP) })));
  const width = LINEAGE_COLUMNS.length * CARD_W + (LINEAGE_COLUMNS.length - 1) * COL_GAP;
  const height = TOP + Math.max(1, ...cols.map((c) => c.length)) * (CARD_H + GAP);
  const active = selection && lineage.nodes.some((n) => n.id === selection.id) ? chainOf(lineage, selection.id) : null;
  const lit = (id: string) => !active || id === selection?.id || active.upstream.has(id) || active.downstream.has(id);
  const unsafeCount = lineage.nodes.filter((n) => isUnsafe(n.status)).length;
  const copies = lineage.sourceCount - lineage.originCount;
  return (
    <div className="flex size-full flex-col" data-testid="aidtrace-lineage">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-line px-4 py-2 text-micro text-muted">
        <span><strong className="text-ink">{lineage.sourceCount} source{lineage.sourceCount === 1 ? "" : "s"} → {lineage.originCount} origin{lineage.originCount === 1 ? "" : "s"}</strong>{copies > 0 && ` · ${copies} cop${copies === 1 ? "y" : "ies"} of an earlier source counted once`}</span>
        <span>{lineage.nodes.length} records · {lineage.edges.length} dependencies read from FalkorDB</span>
        {unsafeCount > 0 && <StatusBadge tone="danger">{unsafeCount} stale or blocked</StatusBadge>}
        <span className="ml-auto">{lineage.hashedCount} of {lineage.sourceCount} sources carry a content hash; the rest are assumed distinct, not verified. Paraphrased copies are not detected (experimental).</span>
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-4">
        <div className="relative" style={{ width, height }}>
          <svg className="absolute inset-0" width={width} height={height} aria-hidden="true">
            {lineage.edges.map((e) => {
              const a = pos.get(e.from), b = pos.get(e.to);
              if (!a || !b) return null;
              const x1 = a.x + CARD_W, y1 = a.y + CARD_H / 2, x2 = b.x, y2 = b.y + CARD_H / 2, mid = (x1 + x2) / 2;
              const on = !active || (lit(e.from) && lit(e.to));
              return <path key={`${e.from}>${e.to}`} d={`M${x1},${y1} C${mid},${y1} ${mid},${y2} ${x2},${y2}`} fill="none" stroke={on && active ? "var(--accent)" : "var(--line)"} strokeWidth={on && active ? 2 : 1} opacity={on ? 1 : 0.25} />;
            })}
          </svg>
          {LINEAGE_COLUMNS.map((kind, c) => <p key={kind} className="absolute text-micro font-semibold uppercase tracking-wider text-muted" style={{ left: c * (CARD_W + COL_GAP), top: 6 }}>{LINEAGE_LABELS[kind]} · {cols[c].length}</p>)}
          {lineage.nodes.map((n: LineageNode) => {
            const p = pos.get(n.id)!;
            const isSel = selection?.id === n.id;
            return (
              <button key={n.id} type="button" onClick={() => onSelect({ kind: n.kind, id: n.id, label: n.label })} aria-pressed={isSel} title={`${n.label} — ${n.detail}`}
                className={`absolute overflow-hidden border bg-surface p-2 text-left transition-opacity hover:bg-surface-2 focus-visible:outline-2 focus-visible:outline-accent ${isSel ? "border-ink" : isUnsafe(n.status) ? "border-danger" : "border-line"} ${lit(n.id) ? "" : "opacity-30"}`}
                style={{ left: p.x, top: p.y, width: CARD_W, height: CARD_H }}>
                <span className="flex items-center justify-between gap-1"><span className="truncate text-caption font-medium text-ink">{n.label}</span><span className={`shrink-0 text-micro ${isUnsafe(n.status) ? "text-danger" : "text-muted"}`}>{n.status.toLowerCase()}</span></span>
                <span className="mt-0.5 block truncate text-micro text-muted">{n.detail}</span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ---- Agent Memory ----------------------------------------------------------------------------------------------------------------------

export function MemoryView({ data, selection, onSelect }: ViewProps) {
  const snap = data.snap;
  if (data.errors.memory) return <Empty><p role="alert" className="text-danger">{data.errors.memory}</p></Empty>;
  if (!snap) return <Empty><p role="status">Reading agent memory…</p></Empty>;
  if (!snap.memories.length) return <Empty><p className="text-body font-semibold text-ink">Agent memory is empty</p><p>Nothing is shown until an agent has stored something. Record the GreenChain decision to create evidence-backed memory.</p><RecordButton data={data} /></Empty>;
  return (
    <div className="size-full overflow-y-auto p-4">
      <ul className="space-y-2">
        {snap.memories.map((m) => (
          <li key={m.id}>
            <button type="button" onClick={() => onSelect({ kind: "memory", id: m.id, label: m.summary })} aria-pressed={selection?.id === m.id}
              className={`w-full border bg-surface p-3 text-left text-caption hover:bg-surface-2 focus-visible:outline-2 focus-visible:outline-accent ${selection?.id === m.id ? "border-ink" : isUnsafe(m.status) ? "border-danger" : "border-line"}`}>
              <span className="flex flex-wrap items-center justify-between gap-2"><span className="font-medium text-ink">{m.summary}</span><StatusBadge tone={toneOf(m.status)}>{m.status.toLowerCase()}</StatusBadge></span>
              <span className="mt-1 block text-micro text-muted">{m.memory_kind.toLowerCase()} · {m.agent_id} · recorded {when(m.recorded_at)} · last verified {when(m.last_verified_at)}</span>
              <span className="mt-0.5 block text-micro text-muted">{m.claims.length} claim(s) · {m.sources.length} source reference(s) · {m.independent_sources} independent · {m.verification_status.toLowerCase()} · {m.verification_status === "UNKNOWN" ? "unrated" : `confidence ${m.confidence.toFixed(2)}`}</span>
              {m.blocked_reason && <span className="mt-1 block text-micro text-danger">Blocked: {m.blocked_reason}</span>}
            </button>
          </li>
        ))}
      </ul>
      {data.handoffs.length > 0 && (
        <section className="mt-5" aria-label="Agent handoffs">
          <h3 className="text-body font-semibold">Recalled by other agents</h3>
          <ul className="mt-2 space-y-1 text-micro text-muted">{data.handoffs.slice(0, 8).map((h) => <li key={`${h.memory_id}-${h.recall_session}`}>{h.recalled_by} recalled a memory by {h.produced_by} at {when(h.at)} — {h.usable ? "usable" : "blocked as " + h.memory_status.toLowerCase()}</li>)}</ul>
        </section>
      )}
    </div>
  );
}

// ---- Workflow --------------------------------------------------------------------------------------------------------------------------

const DATASETS = [["EMBER", "Ember grid intensity"], ["USEEIO", "USEEIO supply-chain factors"], ["GLEC", "GLEC transport factors"], ["NDGAIN", "ND-GAIN climate risk"]] as const;
const COUNTRIES = ["PT", "DE", "MX", "VN", "CN"];
type StepState = "done" | "ready" | "blocked" | "model";

export function WorkflowView({ data, onSelect, onOpenView }: ViewProps & { onOpenView: (v: "lineage" | "graph" | "memory") => void }) {
  const { snap, lineage, scenario } = data;
  const [form, setForm] = useState({ dataset: "EMBER", country: "PT", factor: 3 });
  const [preview, setPreview] = useState<GcPreview | null>(null);
  const [revised, setRevised] = useState<GcRevised | null>(null);
  const [impact, setImpact] = useState<ImpactPreview | null>(null);
  const [impactSource, setImpactSource] = useState("");
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const scenarioId = useMemo(() => {
    const ids = (snap?.decisions ?? []).map((d) => scenarioOf(d.id)).filter((x): x is string => Boolean(x));
    return ids[ids.length - 1] ?? null;
  }, [snap]);
  const decisions = (snap?.decisions ?? []).filter((d) => scenarioId && d.id.startsWith(`gc:${scenarioId}:`));
  const live = decisions.find((d) => !isUnsafe(d.status)) ?? decisions[decisions.length - 1];
  const liveAction = (snap?.actions ?? []).find((a) => live && a.eligibility.decision_id === live.id);
  const stale = (snap?.decisions ?? []).filter((d) => isUnsafe(d.status));
  const hasMemory = Boolean(snap?.memories.length);

  async function run<T>(key: string, fn: () => Promise<T>): Promise<T | null> {
    setBusy(key); setError(null);
    try { return await fn(); } catch (e) { setError(message(e)); return null; } finally { setBusy(null); }
  }
  const body = () => ({ scenario_id: scenarioId!, dataset: form.dataset, country: form.country, factor: form.factor, label: "Reference data revision (counterfactual)" });
  const steps: { n: number; title: string; state: StepState; detail: string; action?: React.ReactNode }[] = [
    { n: 1, title: "Supplier intelligence", state: scenario ? "done" : "blocked", detail: scenario ? `${scenario.manufacturers.length} suppliers scored from modelled intensities. Candidates are illustrative.` : data.errors.supply ?? "Loading GreenChain…" },
    { n: 2, title: "Cybersecurity correlation", state: "model", detail: "Select a supplier on the globe or graph, then open Cyber Risk in the inspector to trace what depends on it. Model-only: no live security feed is connected." },
    { n: 3, title: "Agent memory", state: hasMemory ? "done" : "ready", detail: hasMemory ? `${snap!.memories.length} memor${snap!.memories.length === 1 ? "y" : "ies"} with their evidence in FalkorDB.` : "Nothing remembered yet.", action: hasMemory ? <Button variant="ghost" onClick={() => onOpenView("memory")}>Open memory</Button> : <RecordButton data={data} /> },
    { n: 4, title: "Risk propagation", state: hasMemory ? "ready" : "blocked", detail: "Which memories, decisions and actions would go stale if a source were superseded. Writes nothing.", action: hasMemory && snap && (
      <span className="flex flex-wrap items-center gap-2">
        <select aria-label="Source to supersede" value={impactSource} onChange={(e) => { setImpactSource(e.target.value); setImpact(null); }} className="min-h-9 border border-line bg-canvas px-2 text-caption">
          <option value="">Choose a source…</option>{snap.sources.map((s) => <option key={s.id} value={s.id}>{s.title || s.id}</option>)}
        </select>
        <Button variant="ghost" disabled={!impactSource || busy === "impact"} onClick={async () => { const r = await run("impact", () => memoryImpactPreview(impactSource)); if (r) setImpact(r); }}>Preview impact</Button>
      </span>) },
    { n: 5, title: "Evidence lineage", state: lineage?.nodes.length ? "done" : "blocked", detail: lineage?.nodes.length ? `${lineage.sourceCount} sources → ${lineage.originCount} origins (${lineage.hashedCount} hashed).` : "Needs recorded evidence.", action: lineage?.nodes.length ? <Button variant="ghost" onClick={() => onOpenView("lineage")}>Open lineage</Button> : undefined },
    { n: 6, title: "Evidence drift", state: scenarioId ? "ready" : "blocked", detail: "A reference dataset is revised for one country; the cascade and the re-ranking that follow are computed by the backend.", action: scenarioId && (
      <span className="flex flex-wrap items-center gap-2">
        <select aria-label="Dataset" value={form.dataset} onChange={(e) => setForm({ ...form, dataset: e.target.value })} className="min-h-9 border border-line bg-canvas px-2 text-caption">{DATASETS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
        <select aria-label="Country" value={form.country} onChange={(e) => setForm({ ...form, country: e.target.value })} className="min-h-9 border border-line bg-canvas px-2 text-caption">{COUNTRIES.map((c) => <option key={c}>{c}</option>)}</select>
        <label className="flex items-center gap-1 text-caption">×<input aria-label="Factor" type="number" min={0.1} step={0.5} value={form.factor} onChange={(e) => setForm({ ...form, factor: Number(e.target.value) })} className="h-9 w-16 border border-line bg-canvas px-2" /></label>
        <Button variant="ghost" disabled={busy !== null} onClick={async () => { const r = await run("preview", () => memoryPreviewRevision(body())); if (r) { setPreview(r); setRevised(null); } }}>Preview</Button>
        <Button variant="primary" disabled={busy !== null} onClick={async () => { const r = await run("revise", () => memoryRevise(body())); if (r) { setRevised(r); setPreview(null); await data.refreshMemory(); } }}>Apply revision</Button>
      </span>) },
    { n: 7, title: "Decision governance", state: stale.length ? "blocked" : decisions.length ? "done" : "blocked", detail: stale.length ? `${stale.length} decision(s) no longer stand on current evidence and cannot carry an approval.` : decisions.length ? "Every decision stands on current evidence." : "No decision recorded." },
    { n: 8, title: "Human review", state: liveAction?.eligibility.eligible ? "ready" : "blocked", detail: liveAction ? (liveAction.eligibility.eligible ? `“${liveAction.summary}” may be approved at its current revision.` : `“${liveAction.summary}” is blocked: ${liveAction.eligibility.reasons[0] ?? "not eligible"}.`) : "No action awaiting review.", action: liveAction && (
      <Button variant="primary" disabled={busy !== null} onClick={async () => { const r = await run("approve", () => memoryApprove(liveAction.id, "Approved in the AIDTRACE workspace")); if (r) { setNote(`Approved by ${r.reviewer} against graph revision ${r.graph_revision.slice(0, 12)}.`); await data.refreshMemory(); } }}>Approve current revision</Button>) },
  ];
  const badge: Record<StepState, [Tone, string]> = { done: ["verified", "done"], ready: ["caution", "ready"], blocked: ["danger", "blocked"], model: ["neutral", "model-only"] };
  return (
    <div className="size-full overflow-y-auto p-4" data-testid="aidtrace-workflow">
      <ol className="space-y-2">
        {steps.map((s) => (
          <li key={s.n} className="border border-line bg-surface p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-caption font-semibold text-ink"><span className="mr-2 font-mono text-muted">{String(s.n).padStart(2, "0")}</span>{s.title}</span>
              <StatusBadge tone={badge[s.state][0]}>{badge[s.state][1]}</StatusBadge>
            </div>
            <p className="mt-1 text-micro leading-relaxed text-muted">{s.detail}</p>
            {s.action && <div className="mt-2">{s.action}</div>}
          </li>
        ))}
      </ol>
      {error && <p role="alert" className="mt-3 border-l-2 border-danger bg-surface p-3 text-caption text-danger">{error}</p>}
      {note && <p role="status" className="mt-3 border-l-2 border-line bg-surface p-3 text-caption">{note}</p>}
      {impact && (
        <section className="mt-3 border border-line bg-surface p-3 text-caption" aria-label="Impact preview">
          <h3 className="font-semibold">{impact.would_mark_stale.length} record(s) would go stale</h3>
          <ul className="mt-1 space-y-0.5 text-micro text-muted">{impact.would_mark_stale.map((x) => <li key={x.id}><button type="button" className="text-left underline-offset-2 hover:underline" onClick={() => onSelect({ kind: "memory", id: x.id, label: x.label })}>{x.label}</button> — depth {x.depth}, via {x.via.join(" → ") || "direct"}</li>)}</ul>
        </section>
      )}
      {preview && (
        <section className="mt-3 border border-line bg-surface p-3 text-caption" aria-label="Revision preview">
          <h3 className="font-semibold">Preview (nothing written)</h3>
          <p className="mt-1">{preview.recommendation_changes ? <>Recommendation changes from <strong>{plain(preview.top_before)}</strong> to <strong>{plain(preview.top_after)}</strong>.</> : <>Recommendation stays <strong>{plain(preview.top_after)}</strong>.</>}</p>
          <p className="mt-1 text-micro text-muted">{preview.ranking.filter((r) => r.rank_before !== r.rank_after).length} supplier rank(s) move.</p>
        </section>
      )}
      {revised && (
        <section className="mt-3 border border-line bg-surface p-3 text-caption" aria-label="Revision result">
          <h3 className="font-semibold">{revised.duplicate ? "This revision was already applied" : `${revised.cascade.invalidated.length} record(s) invalidated`}</h3>
          <p className="mt-1">{revised.recommendation_changed ? <>The recommendation changed from <strong>{plain(revised.top_before)}</strong> to <strong>{plain(revised.top_after)}</strong>. The earlier approval no longer applies.</> : <>The recommendation stays <strong>{plain(revised.top_after)}</strong>, but approvals bound to the old revision are void.</>}</p>
          <ul className="mt-1 space-y-0.5 text-micro text-muted">{revised.cascade.invalidated.slice(0, 8).map((c) => <li key={c.id}>{c.label}: {c.before.toLowerCase()} → {c.after.toLowerCase()}</li>)}</ul>
          {revised.new_proposal && <p className="mt-2 text-micro">A new proposal is awaiting human review.</p>}
        </section>
      )}
    </div>
  );
}
