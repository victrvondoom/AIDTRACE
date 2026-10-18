"use client";

// Extension bodies that are native to the workspace rather than hosted legacy pages. Each reads the shared AIDTRACE context, so it opens already focused on
// whatever the user selected, and each takes its numbers from existing backend endpoints. A value that is unknown shows as "—", never as 0.
import { useEffect, useMemo, useState } from "react";
import { Bar, BarChart, Cell, CartesianGrid, Tooltip, XAxis, YAxis } from "recharts";
import { AXIS, ChartCard, GRID, TOOLTIP } from "@/components/charts";
import { GraphViews, type GraphMarks } from "@/components/graph-views";
import { Button, MetricCard, StatusBadge } from "@/components/ui";
import { AttentionList } from "@/app/(app)/overview/_components/attention-list";
import type { Fetched } from "@/lib/api";
import { getComplianceDashboard, getEvents, getPendingConflicts, getPendingQuarantine, getSlaReport } from "@/lib/api";
import type { LabGraph } from "@/lib/graph-layout";
import { decisionState } from "@/lib/aidtrace-lineage";
import { analyzeLab, memoryApprove } from "@/lib/lab-api";
import type { ComplianceDashboard, OperationalEvent, SlaReport } from "@/lib/types";
import { useFetch } from "@/lib/use-fetch";
import { latestScenarioId } from "../automation";
import { supplierAnchors } from "../data";
import { LineageView, TimelineView } from "../views";
import { deriveSupplierContext, useAidtrace } from "./context";

const plain = (n: string) => n.replace("Illustrative ", "");
const dash = (n: number | null | undefined) => (n === null || n === undefined ? "—" : String(n));
const message = (e: unknown) => (e instanceof Error ? e.message : "The request failed.");

/** One line saying what the extension is focused on, so it is obvious the context carried over. */
export function ContextBar() {
  const ctx = useAidtrace();
  const { selection, recommended, data } = ctx;
  const sc = deriveSupplierContext(ctx);
  return (
    <p data-testid="aidtrace-context-bar" className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-line bg-surface px-4 py-2 text-micro text-muted">
      <span className="font-medium uppercase tracking-wider">Context</span>
      {sc.name ? <span className="text-ink">{plain(sc.name)} <span className="text-muted">{sc.selected ? "selected on the globe" : "recommended supplier (nothing selected)"}</span></span> : <span>No supplier loaded</span>}
      {selection && selection.kind !== "supplier" && <span>· {selection.kind}: <span className="text-ink">{plain(selection.label)}</span></span>}
      {!data.scenario && recommended === null && <span>· supply scenario unavailable</span>}
    </p>
  );
}

// ---- Risk Analytics --------------------------------------------------------------------------------------------------------------------

const DAY_MS = 86_400_000;
interface RiskInputs { conflicts: number | null; quarantine: number | null; sla: SlaReport | null; compliance: ComplianceDashboard | null; events: OperationalEvent[]; unavailable: string[] }

async function fetchRiskInputs(): Promise<Fetched<RiskInputs>> {
  const results = await Promise.allSettled([getPendingConflicts(), getPendingQuarantine(), getSlaReport(), getComplianceDashboard(), getEvents({ limit: 200 })]);
  const unavailable: string[] = [];
  const names = ["Open conflicts", "Quarantine queue", "SLA report", "Compliance gaps", "Events"];
  const pick = <T,>(i: number): T | null => { const r = results[i]; if (r.status === "fulfilled") return r.value.data as T; unavailable.push(names[i]); return null; };
  const conflicts = pick<{ total: number }>(0), quarantine = pick<{ total: number }>(1), sla = pick<SlaReport>(2), compliance = pick<ComplianceDashboard>(3), events = pick<{ items: OperationalEvent[] }>(4);
  if (unavailable.length === results.length) throw new Error(`Risk services unavailable: ${unavailable.join(", ")}`);
  return { data: { conflicts: conflicts?.total ?? null, quarantine: quarantine?.total ?? null, sla, compliance, events: events?.items ?? [], unavailable }, source: "live" };
}

/** Graph-only mode: no request to the plant stores, so a page that cannot reach them shows no error block. */
async function skipRiskInputs(): Promise<Fetched<RiskInputs>> {
  return { data: { conflicts: null, quarantine: null, sla: null, compliance: null, events: [], unavailable: [] }, source: "live" };
}

function eventTrend(events: OperationalEvent[]) {
  const times = events.map((e) => Date.parse(e.occurred_at)).filter((t) => !Number.isNaN(t));
  if (!times.length) return null;
  const end = Math.max(...times);
  const buckets = Array.from({ length: 14 }, (_, i) => ({ day: new Date(end - (13 - i) * DAY_MS).toLocaleDateString(undefined, { month: "short", day: "numeric" }), count: 0 }));
  for (const t of times) { const i = 13 - Math.floor((end - t) / DAY_MS); if (i >= 0 && i < 14) buckets[i].count += 1; }
  return buckets;
}

/** `graphOnly` leaves out the governance queues, which live in the plant stores rather than the FalkorDB graph. */
export function RiskAnalytics({ graphOnly = false }: { graphOnly?: boolean }) {
  const ctx = useAidtrace();
  const sc = deriveSupplierContext(ctx);
  const state = useFetch(graphOnly ? skipRiskInputs : fetchRiskInputs, [], 60000);
  const loading = state.status === "loading";
  const d = state.status === "live" ? state.data : null;
  const makers = ctx.data.scenario?.manufacturers ?? [];
  const env = makers.map((m) => ({ id: m.id, name: plain(m.name), eco: Math.round(m.ecoScore), transport: Number(m.transportEmissionsTco2e.toFixed(2)), selected: m.id === sc.id }));
  const trend = d ? eventTrend(d.events) : null;
  const overdue = d?.sla ? d.sla.overdue_conflicts_total + d.sla.overdue_quarantine_total : null;
  const critical = d?.compliance?.total_gaps.critical ?? null;
  const cards: [string, number | null, string][] = [
    ["Connected records", sc.dependents, "depend on this supplier (run Investigate Risk)"], ["Stale memories", sc.staleMemories, "about this supplier"], ["Blocked decisions", sc.blockedDecisions, "cannot be approved"],
    ["Pending reviews", sc.pendingReviews, "awaiting a person"], ["Unverified sources", sc.unhashedSources, `of ${dash(sc.sources)} carry no content hash`],
  ];
  return (
    <div className="space-y-4 p-4" data-testid="aidtrace-risk-analytics">
      <section aria-label="Supplier risk context">
        <h3 className="text-body font-semibold text-ink">{sc.name ? plain(sc.name) : "Supplier"}{sc.maker && <span className="ml-2 text-caption font-normal text-muted">{sc.maker.location.country} · eco score {sc.maker.ecoScore.toFixed(0)} · {sc.maker.manufacturingEmissionsTco2e.q50.toFixed(0)} tCO2e manufacturing</span>}</h3>
        <ul className="mt-2 grid grid-cols-2 gap-2 md:grid-cols-5">
          {cards.map(([label, value, sub]) => (
            <li key={label} className="border border-line bg-surface p-3"><p className="text-micro uppercase tracking-wide text-muted">{label}</p><p className="mt-1 text-title font-semibold tabular-nums text-ink">{dash(value)}</p><p className="mt-0.5 text-micro text-muted">{sub}</p></li>
          ))}
        </ul>
        {sc.memories.length === 0 && <p className="mt-2 text-micro text-muted">The graph holds no memory about this supplier yet, so these figures are unknown rather than zero. Run Investigate Risk to record it.</p>}
      </section>

      {!graphOnly && <section aria-label="Evidence governance queues">
        <h3 className="text-body font-semibold text-ink">Evidence governance queues</h3>
        {state.status === "error" && <p role="alert" className="mt-2 border-l-2 border-danger pl-2 text-caption text-danger">{state.error.message} <Button variant="ghost" onClick={state.retry}>Retry</Button></p>}
        {d?.unavailable.length ? <p role="status" className="mt-2 text-micro text-muted">Unavailable: {d.unavailable.join(", ")}. Those values stay blank until the service responds.</p> : null}
        <div className="mt-2 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <MetricCard label="Open conflicts" value={d?.conflicts} sub="awaiting resolution" tone="caution" href="/governance/conflicts" loading={loading} />
          <MetricCard label="Quarantine backlog" value={d?.quarantine} sub="held evidence" tone="info" href="/governance/quarantine" loading={loading} />
          <MetricCard label="Overdue SLA items" value={overdue} sub="past deadline" tone="danger" href="/governance/sla" loading={loading} />
          <MetricCard label="Critical gaps" value={critical} sub="compliance findings (plant scope)" tone={critical === 0 ? "verified" : "danger"} href="/compliance" loading={loading} />
        </div>
      </section>}

      {d && !graphOnly && <AttentionList sla={d.sla} compliance={d.compliance} loading={false} />}

      <div className="grid gap-4 xl:grid-cols-2">
        <ChartCard title="Environmental score by supplier" sub="Lower is better. The selected supplier is highlighted." height={200} loading={!ctx.data.scenario && !ctx.data.errors.supply} empty={makers.length === 0 && "No suppliers loaded."}>
          <BarChart data={env} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
            <CartesianGrid {...GRID} /><XAxis dataKey="name" {...AXIS} interval={0} /><YAxis {...AXIS} width={32} /><Tooltip {...TOOLTIP} />
            <Bar dataKey="eco" name="Eco score">{env.map((e) => <Cell key={e.id} fill={e.selected ? "var(--accent)" : "var(--muted)"} />)}</Bar>
          </BarChart>
        </ChartCard>
        <ChartCard title="Sea-transport emissions by supplier (tCO2e)" sub="Modelled; changes with the transport mode in GreenChain." height={200} loading={!ctx.data.scenario && !ctx.data.errors.supply} empty={makers.length === 0 && "No suppliers loaded."}>
          <BarChart data={env} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
            <CartesianGrid {...GRID} /><XAxis dataKey="name" {...AXIS} interval={0} /><YAxis {...AXIS} width={32} /><Tooltip {...TOOLTIP} />
            <Bar dataKey="transport" name="tCO2e">{env.map((e) => <Cell key={e.id} fill={e.selected ? "var(--accent)" : "var(--muted)"} />)}</Bar>
          </BarChart>
        </ChartCard>
      </div>

      {trend && (
        <ChartCard title="Operational events" sub="Daily volume ending at the newest recorded event" height={160}>
          <BarChart data={trend} margin={{ top: 4, right: 4, left: 0, bottom: 0 }} barCategoryGap="22%">
            <CartesianGrid {...GRID} /><XAxis dataKey="day" {...AXIS} interval="preserveStartEnd" minTickGap={40} /><YAxis {...AXIS} allowDecimals={false} width={32} /><Tooltip {...TOOLTIP} />
            <Bar dataKey="count" name="Events" fill="var(--accent)" />
          </BarChart>
        </ChartCard>
      )}
    </div>
  );
}

// ---- Connected Graph -------------------------------------------------------------------------------------------------------------------

/** Dependency exploration over the persisted FalkorDB graph, focused on the selected supplier, with impact marks from the Graph Lab engine. */
export function ConnectedGraph() {
  const { data, selection, select } = useAidtrace();
  const site = data.site;
  const supplier = selection?.kind === "supplier" ? selection.label : null;
  const anchors = useMemo(() => (supplier ? supplierAnchors(site, supplier) : selection && site?.graph.nodes.some((n) => n.id === selection.id) ? [selection.id] : []), [site, supplier, selection]);
  const key = anchors.join("|");
  const [result, setResult] = useState<{ key: string; marks: GraphMarks; impacted: number } | { key: string; error: string } | null>(null);
  const [impactOnly, setImpactOnly] = useState(false);
  const [hidden, setHidden] = useState<string[]>([]);

  useEffect(() => {
    if (!anchors.length) return;
    let live = true;
    const run = (direction: "reverse" | "forward") => analyzeLab("blast_radius", { site_graph: true }, { changed: anchors, direction, max_depth: 8 });
    Promise.all([run("reverse"), run("forward")]).then(([a, b]) => {
      if (!live) return;
      const nodes = { ...a.result.node_marks, ...b.result.node_marks };
      setResult({ key, marks: { node_marks: nodes, edge_marks: { ...a.result.edge_marks, ...b.result.edge_marks } }, impacted: Object.keys(nodes).filter((id) => !anchors.includes(id)).length });
    }).catch((e: unknown) => { if (live) setResult({ key, error: message(e) }); });
    return () => { live = false; };
  }, [key, anchors]);

  if (!site) return <p role="status" className="p-6 text-caption text-muted">{data.errors.memory ? `The FalkorDB graph could not be read: ${data.errors.memory}` : "Reading the FalkorDB graph…"}</p>;
  if (site.empty) return <p className="p-6 text-caption text-muted">Nothing is persisted in FalkorDB yet. Choose Investigate Risk in the workspace to record the supplier decision.</p>;

  const current = result && result.key === key ? result : null;
  const marks = current && "marks" in current ? current.marks : undefined;
  const types = [...new Set(site.graph.nodes.map((n) => n.type))].sort();
  const visibleTypes = new Set(types.filter((t) => !hidden.includes(t)));
  const marked = new Set(Object.keys(marks?.node_marks ?? {}));
  const keep = (id: string, type: string) => visibleTypes.has(type) && (!impactOnly || !anchors.length || marked.has(id) || anchors.includes(id));
  const graph: LabGraph = { nodes: site.graph.nodes.filter((n) => keep(n.id, n.type)), edges: [] };
  const ids = new Set(graph.nodes.map((n) => n.id));
  graph.edges = site.graph.edges.filter((e) => ids.has(e.source) && ids.has(e.target));
  const toggle = (t: string) => setHidden((h) => (h.includes(t) ? h.filter((x) => x !== t) : [...h, t]));
  return (
    <div className="space-y-3 p-4" data-testid="aidtrace-connected-graph">
      <div className="flex flex-wrap items-center gap-2 text-micro text-muted">
        <span>{graph.nodes.length} of {site.graph.nodes.length} nodes · {graph.edges.length} edges, read from FalkorDB.</span>
        {anchors.length > 0 && <span>{current && "error" in current ? <span role="alert" className="text-danger">Impact analysis failed: {current.error}</span> : current ? `${current.impacted} record(s) in the impact of ${supplier ? plain(supplier) : "the selection"}.` : "Tracing impact…"}</span>}
        {!anchors.length && <span>Select a supplier on the globe to focus the graph on its dependencies.</span>}
      </div>
      <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Filters">
        {anchors.length > 0 && <Button aria-pressed={impactOnly} variant={impactOnly ? "primary" : "ghost"} onClick={() => setImpactOnly((v) => !v)}>Impact only</Button>}
        {types.map((t) => <Button key={t} aria-pressed={visibleTypes.has(t)} variant={visibleTypes.has(t) ? "primary" : "ghost"} onClick={() => toggle(t)}>{t}</Button>)}
      </div>
      <GraphViews graph={graph} marks={marks} selected={anchors[0] ?? selection?.id ?? null} onSelect={(id) => { const n = site.graph.nodes.find((x) => x.id === id); if (n) select({ kind: "node", id: n.id, label: n.label }); }} />
    </div>
  );
}

// ---- Decision validity -----------------------------------------------------------------------------------------------------------------

/** The decisions that matter for the current context, each with its state from backend fields and the approval guard intact. */
export function DecisionValidity() {
  const ctx = useAidtrace();
  const { data, evidence, select } = ctx;
  const sc = deriveSupplierContext(ctx);
  const snap = data.snap;
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [working, setWorking] = useState<string | null>(null);
  if (!snap) return <p role="status" className="p-4 text-caption text-muted">{data.errors.memory ?? "Reading decisions…"}</p>;
  const latest = latestScenarioId(snap.decisions);
  const decisions = sc.selected && sc.decisions.length ? sc.decisions : snap.decisions.filter((d) => latest && d.id.startsWith(`gc:${latest}:`));
  const actionFor = (id: string) => snap.actions.find((a) => a.eligibility.decision_id === id);
  async function approve(actionId: string) {
    setWorking(actionId); setError(null); setNote(null);
    try { const r = await memoryApprove(actionId, "Approved in the AIDTRACE workspace"); setNote(`Approved by ${r.reviewer} against graph revision ${r.graph_revision.slice(0, 12)}.`); await data.refreshMemory(); }
    catch (e) { setError(message(e)); } finally { setWorking(null); }
  }
  return (
    <section aria-label="Decision validity" className="space-y-2 border-b border-line p-4" data-testid="aidtrace-decision-validity">
      <h3 className="text-body font-semibold text-ink">Decision validity <span className="text-caption font-normal text-muted">{sc.selected ? `for ${plain(sc.name ?? "")}` : "latest scenario"}</span></h3>
      {evidence && <p className="border-l-2 border-line pl-2 text-caption">{evidence.alreadyApplied ? "The synthetic evidence update was already applied." : evidence.recommendationChanged ? `Evidence Drift: recommendation changed ${plain(evidence.topBefore ?? "")} → ${plain(evidence.topAfter ?? "")}; ${evidence.invalidated.length} record(s) invalidated.` : `Evidence Drift: ${plain(evidence.topAfter ?? "")} still recommended.`}</p>}
      {decisions.length === 0 && <p className="text-caption text-muted">No decision is recorded for this context. Choose Investigate Risk.</p>}
      <ul className="grid gap-2 lg:grid-cols-2">
        {decisions.map((d) => {
          const action = actionFor(d.id); const st = decisionState(d, action);
          return (
            <li key={d.id} className="border border-line bg-surface p-3 text-caption">
              <div className="flex items-start justify-between gap-2"><span className="font-medium text-ink">{d.summary}</span><StatusBadge tone={st.tone}>{st.label}</StatusBadge></div>
              {st.reason && <p className="mt-0.5 text-micro text-muted">{st.reason}</p>}
              <div className="mt-2 flex flex-wrap gap-1.5">
                <Button variant="ghost" onClick={() => select({ kind: "decision", id: d.id, label: d.summary })}>Select in workspace</Button>
                {action && <Button variant="primary" disabled={working !== null || !action.eligibility.eligible || action.eligibility.approval_current} onClick={() => void approve(action.id)}>{!action.eligibility.eligible ? "Approval blocked" : action.eligibility.approval_current ? "Approved" : "Approve"}</Button>}
              </div>
            </li>
          );
        })}
      </ul>
      {error && <p role="alert" className="border-l-2 border-danger pl-2 text-caption text-danger">{error}</p>}
      {note && <p role="status" className="border-l-2 border-line pl-2 text-caption">{note}</p>}
    </section>
  );
}

// ---- Provenance ------------------------------------------------------------------------------------------------------------------------

export function Provenance() {
  const { data, selection, select, runs } = useAidtrace();
  return (
    <div className="flex h-[78vh] min-h-[480px] flex-col" data-testid="aidtrace-provenance">
      <div className="min-h-0 flex-[3] border-b border-line"><LineageView data={data} selection={selection} onSelect={select} /></div>
      <div className="min-h-0 flex-[2]"><TimelineView data={data} runs={runs} onSelect={select} /></div>
    </div>
  );
}

// ---- Evidence for the current context --------------------------------------------------------------------------------------------------

export function EvidenceForContext() {
  const ctx = useAidtrace();
  const sc = deriveSupplierContext(ctx);
  const { data, openExtension } = ctx;
  const lineage = data.lineage;
  const rows = sc.memories.flatMap((m) => m.sources.map((s) => ({ memory: m, source: s, node: lineage?.nodes.find((n) => n.id === s.id) })));
  if (!sc.name) return null;
  return (
    <section aria-label="Evidence for this supplier" className="border-b border-line p-4" data-testid="aidtrace-evidence-context">
      <h3 className="text-body font-semibold text-ink">Evidence behind {plain(sc.name)}</h3>
      {rows.length === 0 ? <p className="mt-1 text-caption text-muted">The graph holds no recorded evidence for this supplier yet.</p> : (
        <ul className="mt-2 space-y-1 text-caption">
          {rows.map(({ memory, source, node }) => (
            <li key={`${memory.id}-${source.id}`} className="flex flex-wrap items-center gap-2">
              <StatusBadge tone={node?.trust === "Unverified" || node?.trust === "Superseded" || node?.trust === "Disputed" ? "caution" : "verified"}>{node?.trust ?? "Unverified"}</StatusBadge>
              <span className="text-ink">{node?.label ?? source.id}</span>
              {source.document_id && <button type="button" className="text-link underline-offset-2 hover:underline" onClick={() => openExtension("evidence-vault", `/documents/${encodeURIComponent(source.document_id!)}`)}>Open document</button>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// ---- Investigation activity ------------------------------------------------------------------------------------------------------------

/** What happened in this investigation: graph history plus this session's workflow runs, newest first. */
export function ActivityTimeline() {
  const { data, select, runs } = useAidtrace();
  return <div className="h-[70vh] min-h-[360px]" data-testid="aidtrace-activity"><TimelineView data={data} runs={runs} onSelect={select} /></div>;
}
