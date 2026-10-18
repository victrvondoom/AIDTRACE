"use client";

// Right-hand contextual inspector. It shows only what the current selection (supplier, graph node, evidence, memory, decision or action) has in
// the graph, one tab at a time, in collapsed cards.
import { Fragment, useMemo, useState } from "react";
import { Button, StatusBadge } from "@/components/ui";
import { chainOf, isUnsafe, type LineageNode } from "@/lib/aidtrace-lineage";
import { memoryGreenchainReport } from "@/lib/lab-api";
import { propagate, type AidtraceData, type Propagation, type Selection } from "./data";
import { toneOf } from "./views";

export const INSPECTOR_TABS = ["Overview", "Evidence", "Lineage", "Cyber Risk", "Memory", "Decisions", "Reports"] as const;
export type InspectorTab = (typeof INSPECTOR_TABS)[number];

const plain = (name: string) => name.replace("Illustrative ", "");
const when = (iso: string | undefined) => (iso ? iso.slice(0, 16).replace("T", " ") : "—");
const message = (e: unknown) => (e instanceof Error ? e.message : "The request failed.");

function Card({ title, badge, children, open }: { title: string; badge?: React.ReactNode; children: React.ReactNode; open?: boolean }) {
  return (
    <details open={open} className="border border-line bg-surface">
      <summary className="flex cursor-pointer items-center justify-between gap-2 p-3 text-caption font-medium text-ink">{title}{badge}</summary>
      <div className="border-t border-line p-3 text-caption">{children}</div>
    </details>
  );
}
const Hint = ({ children }: { children: React.ReactNode }) => <p className="p-3 text-caption leading-relaxed text-muted">{children}</p>;

interface Props { data: AidtraceData; selection: Selection; onSelect: (s: Selection) => void; tab: InspectorTab; onTab: (t: InspectorTab) => void }

export function Inspector({ data, selection, onSelect, tab, onTab }: Props) {
  const { scenario, demo, snap, lineage } = data;
  const supplier = selection?.kind === "supplier" ? scenario?.manufacturers.find((m) => m.id === selection.id) : undefined;
  const graphNode = useMemo(() => {
    if (!demo || !selection) return undefined;
    if (selection.kind === "node") return demo.graph.nodes.find((n) => n.id === selection.id);
    if (supplier) return demo.graph.nodes.find((n) => n.type === "Supplier" && n.label === supplier.name);
    return undefined;
  }, [demo, selection, supplier]);
  const lineageNode: LineageNode | undefined = selection ? lineage?.nodes.find((n) => n.id === selection.id) : undefined;
  const chain = lineage && lineageNode ? chainOf(lineage, lineageNode.id) : null;
  const byId = useMemo(() => new Map((lineage?.nodes ?? []).map((n) => [n.id, n])), [lineage]);
  const needle = supplier ? plain(supplier.name).toLowerCase() : null;
  const relatedMemories = (snap?.memories ?? []).filter((m) => (lineageNode?.kind === "memory" ? m.id === lineageNode.id : needle ? m.summary.toLowerCase().includes(needle) : false));

  const [prop, setProp] = useState<Propagation | null>(null);
  const [propBusy, setPropBusy] = useState(false);
  const [propFailure, setPropFailure] = useState<{ id: string; message: string } | null>(null);
  const [report, setReport] = useState<string | null>(null);
  const [reportError, setReportError] = useState<string | null>(null);
  const graphNodeId = graphNode?.id;
  // Results belong to the node they were traced for; selecting another node simply stops showing them.
  const shownProp = prop?.changed === graphNodeId ? prop : null;
  const propError = propFailure && propFailure.id === graphNodeId ? propFailure.message : null;

  async function trace() {
    if (!demo || !graphNode) return;
    setPropBusy(true); setPropFailure(null);
    try { setProp(await propagate(demo.graph, graphNode.id)); } catch (e) { setPropFailure({ id: graphNode.id, message: message(e) }); } finally { setPropBusy(false); }
  }
  const scenarioId = useMemo(() => {
    const ids = (snap?.decisions ?? []).map((d) => /^gc:([^:]+):/.exec(d.id)?.[1]).filter((x): x is string => Boolean(x));
    return ids[ids.length - 1] ?? null;
  }, [snap]);
  async function makeReport() {
    if (!scenarioId) return;
    setReportError(null);
    try { setReport((await memoryGreenchainReport(scenarioId)).markdown); } catch (e) { setReportError(message(e)); }
  }

  const link = (id: string) => {
    const n = byId.get(id);
    return n ? <button type="button" key={id} onClick={() => onSelect({ kind: n.kind, id: n.id, label: n.label })} className="block w-full truncate text-left underline-offset-2 hover:underline">{n.kind} · {n.label} <span className={isUnsafe(n.status) ? "text-danger" : "text-muted"}>({n.status.toLowerCase()})</span></button> : null;
  };

  let body: React.ReactNode;
  if (tab === "Overview") {
    body = supplier ? (
      <div className="space-y-2">
        <Card open title={plain(supplier.name)} badge={supplier.isCurrent ? <StatusBadge tone="neutral">incumbent</StatusBadge> : undefined}>
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
            <dt className="text-muted">Country</dt><dd>{supplier.location.country} ({supplier.location.countryCode})</dd>
            <dt className="text-muted">Eco score</dt><dd>{supplier.ecoScore.toFixed(0)} <span className="text-muted">(lower is better)</span></dd>
            <dt className="text-muted">Manufacturing</dt><dd className="font-mono text-micro">{supplier.manufacturingEmissionsTco2e.q10.toFixed(0)} – {supplier.manufacturingEmissionsTco2e.q50.toFixed(0)} – {supplier.manufacturingEmissionsTco2e.q90.toFixed(0)} tCO2e</dd>
            <dt className="text-muted">Transport</dt><dd>{supplier.transportEmissionsTco2e.toFixed(2)} tCO2e</dd>
            <dt className="text-muted">Certifications</dt><dd>{supplier.certifications.join(", ") || "none"} <span className="text-muted">(claimed, unverified)</span></dd>
          </dl>
        </Card>
        <p className="text-micro text-muted">Illustrative candidate. Position is country-level.</p>
      </div>
    ) : graphNode ? (
      <Card open title={graphNode.label} badge={<StatusBadge tone="neutral">{graphNode.type}</StatusBadge>}>
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">{Object.entries(graphNode.props).slice(0, 10).map(([k, v]) => <Fragment key={k}><dt className="text-muted">{k}</dt><dd className="break-words">{String(v)}</dd></Fragment>)}</dl>
      </Card>
    ) : lineageNode ? (
      <Card open title={lineageNode.label} badge={<StatusBadge tone={toneOf(lineageNode.status)}>{lineageNode.status.toLowerCase()}</StatusBadge>}>
        <p className="text-muted">{lineageNode.kind} · {lineageNode.detail}</p>
        <p className="mt-2 text-micro text-muted">{chain ? `${chain.upstream.size} record(s) upstream · ${chain.downstream.size} downstream` : ""}</p>
      </Card>
    ) : (
      <Hint>Select a supplier on the globe, a node in the graph, or a record in the lineage. This panel then shows what the graph holds about it.
        {snap && <> {snap.memories.length} memor{snap.memories.length === 1 ? "y" : "ies"}, {snap.decisions.length} decision(s), {snap.decisions.filter((d) => isUnsafe(d.status)).length} stale.</>}</Hint>
    );
  } else if (tab === "Evidence") {
    const sources = chain ? [...chain.upstream, ...(lineageNode?.kind === "source" ? [lineageNode.id] : [])].map((id) => byId.get(id)).filter((n): n is LineageNode => n?.kind === "source")
      : relatedMemories.flatMap((m) => m.sources.map((s) => byId.get(s.id))).filter((n): n is LineageNode => Boolean(n));
    const origins = new Set(sources.map((s) => s.origin ?? s.id));
    body = !selection ? <Hint>Select something to see the evidence it rests on.</Hint> : sources.length ? (
      <div className="space-y-2">
        <p className="text-micro text-muted"><strong className="text-ink">{sources.length} source{sources.length === 1 ? "" : "s"} → {origins.size} origin{origins.size === 1 ? "" : "s"}.</strong> Copies with an identical content hash count once; sources without a hash are assumed distinct.</p>
        {sources.map((s) => <Card key={s.id} title={s.label} badge={<StatusBadge tone={toneOf(s.status)}>{s.status.toLowerCase()}</StatusBadge>}><p className="text-muted">{s.detail}</p><p className="mt-1 break-all font-mono text-micro text-muted">{s.origin ? `content ${s.origin.slice(0, 16)}…` : "no content hash recorded"}</p></Card>)}
      </div>
    ) : <Hint>No sources are linked to this selection in the graph. A supplier has evidence only after its decision is recorded to memory.</Hint>;
  } else if (tab === "Lineage") {
    body = !lineageNode ? <Hint>Pick a source, claim, memory, decision or action in the Lineage view to inspect its chain.{supplier && relatedMemories.length > 0 ? " This supplier appears in agent memory; open one below." : ""}{relatedMemories.map((m) => <button key={m.id} type="button" className="mt-2 block text-left underline" onClick={() => onSelect({ kind: "memory", id: m.id, label: m.summary })}>{m.summary}</button>)}</Hint> : (
      <div className="space-y-2">
        <Card open title={`Rests on (${chain!.upstream.size})`}><div className="space-y-1">{[...chain!.upstream].map(link)}{chain!.upstream.size === 0 && <span className="text-muted">Nothing: this is an origin.</span>}</div></Card>
        <Card open title={`Supports (${chain!.downstream.size})`}><div className="space-y-1">{[...chain!.downstream].map(link)}{chain!.downstream.size === 0 && <span className="text-muted">Nothing depends on this.</span>}</div></Card>
        {[...chain!.downstream].some((id) => { const n = byId.get(id); return n && (n.kind === "action" || n.kind === "decision") && isUnsafe(n.status); }) && <p role="status" className="border-l-2 border-danger bg-surface p-2 text-micro text-danger">A dependent decision or action is stale or blocked.</p>}
      </div>
    );
  } else if (tab === "Cyber Risk") {
    body = !graphNode ? <Hint>Select a supplier or a graph node to trace what depends on it.</Hint> : (
      <div className="space-y-2">
        <p className="text-micro leading-relaxed text-muted">Traces dependency reach through the supplier graph. It is a model of exposure: no live security feed is connected, so it does not show an observed compromise.</p>
        <Button variant="primary" disabled={propBusy} onClick={() => void trace()}>{propBusy ? "Tracing…" : `Trace ${plain(graphNode.label)}`}</Button>
        {propError && <p role="alert" className="text-danger">{propError}</p>}
        {shownProp && <>
          <Card open title={`Depend on this (${shownProp.dependents.length})`}>{shownProp.dependents.length ? <ul className="space-y-0.5">{shownProp.dependents.map((x) => <li key={x.id}>{x.label} <span className="text-muted">{x.type} · {x.mark}</span></li>)}</ul> : <span className="text-muted">Nothing depends on it.</span>}</Card>
          <Card open title={`This depends on (${shownProp.dependencies.length})`}>{shownProp.dependencies.length ? <ul className="space-y-0.5">{shownProp.dependencies.map((x) => <li key={x.id}>{x.label} <span className="text-muted">{x.type} · {x.mark}</span></li>)}</ul> : <span className="text-muted">No upstream dependencies.</span>}</Card>
        </>}
      </div>
    );
  } else if (tab === "Memory") {
    body = !relatedMemories.length ? <Hint>{selection ? "No agent memory mentions this selection." : "Select a supplier or a memory."} Memories come from the FalkorDB agent-memory graph.</Hint> : (
      <div className="space-y-2">{relatedMemories.map((m) => (
        <Card key={m.id} open title={m.summary} badge={<StatusBadge tone={toneOf(m.status)}>{m.status.toLowerCase()}</StatusBadge>}>
          <p className="text-muted">{m.agent_id} · recorded {when(m.recorded_at)} · verified {when(m.last_verified_at)}</p>
          <p className="mt-1 text-muted">{m.independent_sources} independent source(s) · {m.verification_status.toLowerCase()} · {m.verification_status === "UNKNOWN" ? "unrated" : `confidence ${m.confidence.toFixed(2)}`}</p>
          {m.blocked_reason && <p className="mt-1 text-danger">Blocked: {m.blocked_reason}</p>}
          <ul className="mt-2 space-y-0.5 font-mono text-micro text-muted">{m.claims.map((c) => <li key={c.id}>{c.fact_key} = {String(c.fact_value)} [{c.status.toLowerCase()}]</li>)}</ul>
        </Card>))}</div>
    );
  } else if (tab === "Decisions") {
    body = !snap?.decisions.length ? <Hint>No decisions are recorded yet. Record one from the Workflow view.</Hint> : (
      <div className="space-y-2">{snap.decisions.map((d) => {
        const action = snap.actions.find((a) => a.eligibility.decision_id === d.id);
        return (
          <Card key={d.id} open={selection?.id === d.id} title={d.summary} badge={<StatusBadge tone={toneOf(d.status)}>{d.status.toLowerCase()}</StatusBadge>}>
            <p className="text-muted">Revision {d.revision_n} · rests on {d.dependency_ids.length} record(s)</p>
            {action && <p className={`mt-1 ${action.eligibility.eligible ? "" : "text-danger"}`}>{action.summary}: {action.eligibility.eligible ? "may be approved" : `blocked — ${action.eligibility.reasons[0] ?? "not eligible"}`}</p>}
            <Button className="mt-2" variant="ghost" onClick={() => onSelect({ kind: "decision", id: d.id, label: d.summary })}>Show in lineage</Button>
          </Card>);
      })}</div>
    );
  } else {
    body = (
      <div className="space-y-2">
        <p className="text-micro leading-relaxed text-muted">A procurement memo written only from what is in the graph: decisions, revisions and approvals.</p>
        <Button variant="primary" disabled={!scenarioId} onClick={() => void makeReport()}>Generate memo</Button>
        {!scenarioId && <p className="text-micro text-muted">Record a decision first.</p>}
        {reportError && <p role="alert" className="text-danger">{reportError}</p>}
        {report && <pre className="max-h-[50vh] overflow-auto whitespace-pre-wrap border border-line bg-surface p-3 text-micro leading-relaxed">{report}</pre>}
      </div>
    );
  }

  return (
    <div className="flex size-full min-h-0 flex-col">
      <div role="tablist" aria-label="Inspector" className="flex shrink-0 gap-0.5 overflow-x-auto border-b border-line py-2 pl-2 pr-9">
        {INSPECTOR_TABS.map((t) => (
          <button key={t} role="tab" type="button" aria-selected={tab === t} onClick={() => onTab(t)}
            className={`shrink-0 border-b-2 px-2 py-2 text-caption ${tab === t ? "border-accent font-semibold text-ink" : "border-transparent text-muted hover:text-ink"}`}>{t}</button>
        ))}
      </div>
      {selection && <p className="truncate border-b border-line px-3 py-1.5 text-micro text-muted" title={selection.label}>{selection.kind}: {plain(selection.label)}</p>}
      <div role="tabpanel" className="min-h-0 flex-1 space-y-2 overflow-y-auto p-3">{body}</div>
    </div>
  );
}
