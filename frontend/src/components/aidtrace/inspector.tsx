"use client";

// Right-hand contextual inspector: three sections (Risk, Evidence, Decision), one open at a time. Every label is derived from backend data; when nothing is
// selected it says so instead of filling the panel with explanation.
import { Fragment, useMemo, useState } from "react";
import { Button, StatusBadge } from "@/components/ui";
import { chainOf, decisionState, isUnsafe, type LineageNode } from "@/lib/aidtrace-lineage";
import { memoryApprove, memoryGreenchainReport } from "@/lib/lab-api";
import type { AidtraceData, Selection } from "./data";
import type { EvidenceResult, InvestigationResult } from "./automation";
import { latestScenarioId } from "./automation";

export type Section = "risk" | "evidence" | "decision";
const plain = (name: string) => name.replace("Illustrative ", "");
const when = (iso: string | undefined) => (iso ? iso.slice(0, 16).replace("T", " ") : "—");
const message = (e: unknown) => (e instanceof Error ? e.message : "The request failed.");

function Fold({ title, count, children, open }: { title: string; count?: number; children: React.ReactNode; open?: boolean }) {
  return (
    <details open={open} className="border-t border-line first:border-t-0">
      <summary className="flex cursor-pointer items-center justify-between py-1.5 text-micro font-medium uppercase tracking-wide text-muted">{title}{count !== undefined && <span>{count}</span>}</summary>
      <div className="pb-2 text-caption">{children}</div>
    </details>
  );
}

function Panel({ id, title, open, onOpen, summary, children }: { id: Section; title: string; open: boolean; onOpen: (s: Section) => void; summary?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section aria-label={title} className="border-b border-line">
      <h2>
        <button type="button" aria-expanded={open} onClick={() => onOpen(id)} className="flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left text-body font-semibold text-ink hover:bg-surface-2">
          <span>{title}</span><span className="flex items-center gap-2 text-micro font-normal text-muted">{summary}<span aria-hidden="true">{open ? "−" : "+"}</span></span>
        </button>
      </h2>
      {open && <div className="space-y-2 px-3 pb-3 text-caption">{children}</div>}
    </section>
  );
}

interface Props {
  data: AidtraceData; selection: Selection; onSelect: (s: Selection) => void;
  open: Section; onOpen: (s: Section) => void;
  investigation: InvestigationResult | null; evidence: EvidenceResult | null;
  onInvestigate: () => void; busy: boolean;
}

export function Inspector({ data, selection, onSelect, open, onOpen, investigation, evidence, onInvestigate, busy }: Props) {
  const { scenario, snap, lineage, site, demo } = data;
  const supplier = selection?.kind === "supplier" ? scenario?.manufacturers.find((m) => m.id === selection.id) : undefined;
  const lineageNode: LineageNode | undefined = selection ? lineage?.nodes.find((n) => n.id === selection.id) : undefined;
  const allNodes = site?.graph.nodes ?? demo?.graph.nodes ?? [];
  const allEdges = site?.graph.edges ?? demo?.graph.edges ?? [];
  const graphNode = selection?.kind === "node" ? allNodes.find((n) => n.id === selection.id) : undefined;
  const nodeMap = useMemo(() => new Map(allNodes.map((n) => [n.id, n])), [allNodes]);
  const outgoingEdges = useMemo(() => (graphNode ? allEdges.filter((e) => e.source === graphNode.id) : []), [graphNode, allEdges]);
  const incomingEdges = useMemo(() => (graphNode ? allEdges.filter((e) => e.target === graphNode.id) : []), [graphNode, allEdges]);

  const chain = lineage && lineageNode ? chainOf(lineage, lineageNode.id) : null;
  const byId = useMemo(() => new Map((lineage?.nodes ?? []).map((n) => [n.id, n])), [lineage]);
  const needle = supplier ? plain(supplier.name).toLowerCase() : null;
  const memories = (snap?.memories ?? []).filter((m) => (lineageNode?.kind === "memory" ? m.id === lineageNode.id : needle ? m.summary.toLowerCase().includes(needle) : false));
  const mine = investigation && supplier && investigation.supplierId === supplier.id ? investigation : null;

  const decisions = snap?.decisions ?? [];
  const latest = snap ? latestScenarioId(snap.decisions) : null;
  const current = decisions.filter((d) => latest && d.id.startsWith(`gc:${latest}:`));
  const earlier = decisions.filter((d) => !current.includes(d));
  const actionFor = (id: string) => snap?.actions.find((a) => a.eligibility.decision_id === id);
  const staleCount = decisions.filter((d) => isUnsafe(d.status)).length;
  const reviewCount = current.filter((d) => { const s = decisionState(d, actionFor(d.id)); return s.label === "Needs review" || s.label === "Re-evaluated"; }).length;

  // Short, data-derived headline labels.
  const chips: { text: string; tone: "danger" | "caution" | "verified" }[] = [];
  if (graphNode) {
    chips.push({ text: `FalkorDB · ${graphNode.type}`, tone: "verified" });
    const st = String(graphNode.props?.status ?? graphNode.props?.verification_status ?? "");
    if (st) chips.push({ text: st, tone: isUnsafe(st) ? "danger" : "verified" });
  }
  if (evidence && !evidence.alreadyApplied) chips.push({ text: "Evidence changed.", tone: "caution" });
  if (staleCount) chips.push({ text: `${staleCount} decision${staleCount === 1 ? "" : "s"} affected.`, tone: "danger" });
  if (memories.some((m) => isUnsafe(m.status)) || (!selection && snap?.memories.some((m) => isUnsafe(m.status)))) chips.push({ text: "Memory stale.", tone: "danger" });
  if (evidence?.recommendationChanged && evidence.topAfter) chips.push({ text: `Alternative available: ${plain(evidence.topAfter)}.`, tone: "verified" });
  if (reviewCount) chips.push({ text: "Review required.", tone: "caution" });

  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [working, setWorking] = useState<string | null>(null);
  const [report, setReport] = useState<string | null>(null);

  async function approve(actionId: string) {
    setWorking(actionId); setError(null); setNote(null);
    try {
      const r = await memoryApprove(actionId, "Approved in the AIDTRACE workspace");
      setNote(`Approved by ${r.reviewer} against graph revision ${r.graph_revision.slice(0, 12)}.`);
      await data.refreshMemory();
    } catch (e) { setError(message(e)); } finally { setWorking(null); }
  }
  async function makeReport() {
    if (!latest) return;
    setError(null);
    try { setReport((await memoryGreenchainReport(latest)).markdown); } catch (e) { setError(message(e)); }
  }
  const link = (id: string) => {
    const n = byId.get(id);
    return n ? <button type="button" key={id} onClick={() => onSelect({ kind: n.kind, id: n.id, label: n.label })} className="block w-full truncate text-left underline-offset-2 hover:underline">{n.kind} · {n.label} <span className={isUnsafe(n.status) ? "text-danger" : "text-muted"}>({n.status.toLowerCase()})</span></button> : null;
  };

  return (
    <div className="flex size-full min-h-0 flex-col" data-testid="aidtrace-inspector">
      <div className="border-b border-line px-3 py-2.5 pr-10">
        <p className="truncate text-body font-semibold text-ink" title={selection?.label}>{selection ? plain(selection.label) : "Nothing selected"}</p>
        {!selection && <p className="mt-0.5 text-micro text-muted">Select a supplier or connection to inspect its evidence and impact.</p>}
        {chips.length > 0 && <ul className="mt-1.5 flex flex-wrap gap-1.5" aria-label="Status">{chips.map((c) => <li key={c.text}><StatusBadge tone={c.tone}>{c.text}</StatusBadge></li>)}</ul>}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <Panel id="risk" title="Risk" open={open === "risk"} onOpen={onOpen} summary={mine ? `${mine.dependents.length} dependants` : graphNode ? `${graphNode.type}` : undefined}>
          {supplier ? (
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
              <dt className="text-muted">Country</dt><dd>{supplier.location.country}{supplier.isCurrent ? " · incumbent" : ""}</dd>
              <dt className="text-muted">Eco score</dt><dd>{supplier.ecoScore.toFixed(0)} <span className="text-muted">lower is better</span></dd>
              <dt className="text-muted">Manufacturing</dt><dd className="font-mono text-micro">{supplier.manufacturingEmissionsTco2e.q10.toFixed(0)}–{supplier.manufacturingEmissionsTco2e.q50.toFixed(0)}–{supplier.manufacturingEmissionsTco2e.q90.toFixed(0)} tCO2e</dd>
              <dt className="text-muted">Certifications</dt><dd>{supplier.certifications.join(", ") || "none"} <span className="text-muted">claimed</span></dd>
            </dl>
          ) : lineageNode ? (
            <p className="text-muted">{lineageNode.kind} · {lineageNode.detail}</p>
          ) : graphNode ? (
            <div className="space-y-2">
              <div className="rounded border border-line bg-surface p-2">
                <div className="flex items-center justify-between gap-1 mb-1">
                  <span className="font-mono text-[10px] text-muted truncate max-w-[170px]" title={graphNode.id}>{graphNode.id}</span>
                  <StatusBadge tone="info">{graphNode.type}</StatusBadge>
                </div>
                <p className="font-medium text-ink text-caption">{graphNode.label}</p>
              </div>
              <Fold open title="FalkorDB Node Attributes">
                <dl className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-1 text-micro">
                  {Object.entries(graphNode.props ?? {}).map(([k, v]) => (
                    <Fragment key={k}>
                      <dt className="font-mono text-muted">{k}</dt>
                      <dd className="font-mono text-ink truncate" title={String(v)}>{String(v)}</dd>
                    </Fragment>
                  ))}
                  {!Object.keys(graphNode.props ?? {}).length && (
                    <p className="text-muted">No additional attributes.</p>
                  )}
                </dl>
              </Fold>
            </div>
          ) : null}
          {mine ? (
            <>
              <ul className="list-disc space-y-0.5 pl-4">{mine.findings.map((f) => <li key={f}>{f}</li>)}</ul>
              <Fold title="Connected records" count={mine.dependents.length + mine.dependencies.length}>
                <p className="mb-1 text-micro text-muted">Traversed over the {mine.traversal}.</p>
                {mine.dependents.length > 0 && <><p className="font-medium">Depend on it</p><ul className="mb-1 space-y-0.5">{mine.dependents.slice(0, 12).map((x) => <li key={x.id}>{x.label} <span className="text-muted">{x.type}</span></li>)}</ul></>}
                {mine.dependencies.length > 0 && <><p className="font-medium">It depends on</p><ul className="space-y-0.5">{mine.dependencies.slice(0, 12).map((x) => <li key={x.id}>{x.label} <span className="text-muted">{x.type}</span></li>)}</ul></>}
              </Fold>
              {mine.alternative && <Fold title="Alternative"><p>{plain(mine.alternative.name)} — eco score {mine.alternative.ecoScore.toFixed(0)}.{mine.whatIf && <> Without {plain(mine.supplierName)}, the top choice {mine.whatIf.recommendation_changes ? `becomes ${plain(mine.whatIf.top_after ?? "another supplier")}` : `stays ${plain(mine.whatIf.top_after ?? "unchanged")}`}.</>}</p></Fold>}
              <Fold title="Uncertainty" count={mine.uncertainty.length}><ul className="list-disc space-y-0.5 pl-4 text-muted">{mine.uncertainty.map((u) => <li key={u}>{u}</li>)}</ul></Fold>
            </>
          ) : supplier ? (
            <Button variant="primary" disabled={busy} onClick={onInvestigate}>Investigate {plain(supplier.name)}</Button>
          ) : !lineageNode && !graphNode ? <p className="text-muted">No investigation yet.</p> : null}
        </Panel>

        <Panel id="evidence" title="Evidence" open={open === "evidence"} onOpen={onOpen} summary={lineage ? `${lineage.sourceCount} sources` : undefined}>
          {chain ? (
            <>
              <Fold open title="Rests on" count={chain.upstream.size}><div className="space-y-0.5">{[...chain.upstream].map(link)}{chain.upstream.size === 0 && <span className="text-muted">Nothing: this is an origin.</span>}</div></Fold>
              <Fold open title="Supports" count={chain.downstream.size}><div className="space-y-0.5">{[...chain.downstream].map(link)}{chain.downstream.size === 0 && <span className="text-muted">Nothing depends on this.</span>}</div></Fold>
            </>
          ) : graphNode ? (
            <div className="space-y-2">
              <Fold open title="FalkorDB OpenCypher">
                <div className="rounded border border-line bg-surface p-2">
                  <p className="text-[10px] uppercase tracking-wider text-muted font-medium mb-1">Generated Query</p>
                  <pre className="font-mono text-[11px] text-accent overflow-x-auto whitespace-pre-wrap leading-tight bg-canvas p-1.5 rounded">
{`MATCH (n:${graphNode.type} {id: "${graphNode.id}"})-[r]-(target)\nRETURN n, type(r), target`}
                  </pre>
                </div>
              </Fold>
              <Fold open title="Connected GraphBLAS Links" count={incomingEdges.length + outgoingEdges.length}>
                {outgoingEdges.length > 0 && (
                  <div className="mb-2">
                    <p className="text-micro font-medium text-muted uppercase tracking-wider mb-1">Outgoing ({outgoingEdges.length})</p>
                    <ul className="space-y-1">
                      {outgoingEdges.map((e, idx) => {
                        const target = nodeMap.get(e.target);
                        return (
                          <li key={idx}>
                            <button
                              type="button"
                              onClick={() => onSelect({ kind: "node", id: e.target, label: target?.label ?? e.target })}
                              className="flex w-full items-center justify-between gap-1 text-left rounded p-1 hover:bg-surface-2 transition-colors border border-line/60"
                            >
                              <span className="font-mono text-[10px] text-accent">-[{e.rel}]-&gt;</span>
                              <span className="truncate text-micro text-ink font-medium">{target?.label ?? e.target}</span>
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                )}
                {incomingEdges.length > 0 && (
                  <div>
                    <p className="text-micro font-medium text-muted uppercase tracking-wider mb-1">Incoming ({incomingEdges.length})</p>
                    <ul className="space-y-1">
                      {incomingEdges.map((e, idx) => {
                        const src = nodeMap.get(e.source);
                        return (
                          <li key={idx}>
                            <button
                              type="button"
                              onClick={() => onSelect({ kind: "node", id: e.source, label: src?.label ?? e.source })}
                              className="flex w-full items-center justify-between gap-1 text-left rounded p-1 hover:bg-surface-2 transition-colors border border-line/60"
                            >
                              <span className="truncate text-micro text-ink font-medium">{src?.label ?? e.source}</span>
                              <span className="font-mono text-[10px] text-muted">&lt;-[{e.rel}]-</span>
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                )}
                {!incomingEdges.length && !outgoingEdges.length && (
                  <p className="text-muted text-micro">No connected edges on this node.</p>
                )}
              </Fold>
            </div>
          ) : memories.length ? null : <p className="text-muted">{selection ? "No evidence is linked to this selection in the graph yet." : "Evidence appears here for the selected supplier or record."}</p>}
          {memories.map((m) => (
            <Fold key={m.id} open title={`Memory · ${m.status.toLowerCase()}`}>
              <p>{m.summary}</p>
              <p className="mt-0.5 text-micro text-muted">{m.agent_id} · recorded {when(m.recorded_at)} · {m.independent_sources} independent · {m.verification_status === "UNKNOWN" ? "unrated" : `${m.verification_status.toLowerCase()}, confidence ${m.confidence.toFixed(2)}`}</p>
              {m.blocked_reason && <p className="mt-0.5 text-danger">Blocked: {m.blocked_reason}</p>}
              <ul className="mt-1 space-y-0.5">{m.sources.map((s) => { const n = byId.get(s.id); return <li key={s.id} className="text-micro text-muted">{n?.trust ?? "Unverified"} · {n?.label ?? s.id}</li>; })}</ul>
            </Fold>
          ))}
        </Panel>

        <Panel id="decision" title="Decision" open={open === "decision"} onOpen={onOpen} summary={reviewCount ? `${reviewCount} to review` : staleCount ? `${staleCount} stale` : undefined}>
          {!decisions.length && <p className="text-muted">No decision is recorded yet. Choose Investigate Risk.</p>}
          {evidence && (
            <p className="border-l-2 border-line pl-2">{evidence.alreadyApplied ? "This evidence update was already applied." : evidence.recommendationChanged ? `Re-evaluated: ${plain(evidence.topBefore ?? "")} → ${plain(evidence.topAfter ?? "")}.` : `Re-evaluated: still ${plain(evidence.topAfter ?? "")}.`} {evidence.invalidated.length > 0 && `${evidence.invalidated.length} record(s) invalidated.`}</p>
          )}
          {current.map((d) => {
            const action = actionFor(d.id);
            const st = decisionState(d, action);
            return (
              <div key={d.id} className="border border-line p-2">
                <div className="flex items-start justify-between gap-2"><span className="font-medium">{d.summary}</span><StatusBadge tone={st.tone}>{st.label}</StatusBadge></div>
                {st.reason && <p className="mt-0.5 text-micro text-muted">{st.reason}</p>}
                {action && <p className="mt-1 text-micro">{action.summary}</p>}
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  <Button variant="ghost" onClick={() => onSelect({ kind: "decision", id: d.id, label: d.summary })}>Trace evidence</Button>
                  {action && <Button variant="primary" disabled={working !== null || !action.eligibility.eligible || action.eligibility.approval_current} onClick={() => void approve(action.id)} title={action.eligibility.eligible ? undefined : action.eligibility.reasons[0]}>{!action.eligibility.eligible ? "Approval blocked" : action.eligibility.approval_current ? "Approved" : "Approve"}</Button>}
                </div>
              </div>
            );
          })}
          {earlier.length > 0 && (
            <Fold title="Earlier decisions" count={earlier.length}>
              <ul className="space-y-1">{earlier.map((d) => { const st = decisionState(d, actionFor(d.id)); return <li key={d.id} className="flex items-start justify-between gap-2"><button type="button" onClick={() => onSelect({ kind: "decision", id: d.id, label: d.summary })} className="text-left underline-offset-2 hover:underline">{d.summary}</button><StatusBadge tone={st.tone}>{st.label}</StatusBadge></li>; })}</ul>
            </Fold>
          )}
          {error && <p role="alert" className="border-l-2 border-danger pl-2 text-danger">{error}</p>}
          {note && <p role="status" className="border-l-2 border-line pl-2">{note}</p>}
          {latest && <Fold title="Report"><Button variant="ghost" onClick={() => void makeReport()}>Generate memo</Button>{report && <pre className="mt-2 max-h-60 overflow-auto whitespace-pre-wrap border border-line bg-surface p-2 text-micro leading-relaxed">{report}</pre>}</Fold>}
        </Panel>
      </div>
      {snap && <p className="truncate border-t border-line px-3 py-1.5 text-micro text-muted">FalkorDB · {snap.memories.length} memories · {decisions.length} decisions · {snap.approvals.length} approvals</p>}
    </div>
  );
}
