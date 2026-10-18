"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { GraphViews } from "@/components/graph-views";
import { Button, StatusBadge } from "@/components/ui";
import type { LabGraph } from "@/lib/graph-layout";
import {
  consumerActions, consumerAnalyze, consumerApprove, consumerDropEdge, consumerGraph, consumerHealth, consumerIntake, consumerLoad,
  consumerSetEvidence, consumerSetSource, consumerState,
  type ConsumerAction, type ConsumerAnalysis, type ConsumerIntake, type ConsumerState,
} from "@/lib/lab-api";

const SAMPLE =
  "My flight was cancelled. The airline refunded part of the ticket, my travel insurer rejected the claim, " +
  "and I am still being charged for the hotel, which was non-refundable. (Synthetic case.)";
const VERDICT_TONE = { VERIFIED: "verified", REJECTED: "danger", INSUFFICIENT_EVIDENCE: "caution" } as const;
const EMPTY: LabGraph = { nodes: [], edges: [] };

/** Resolve consumer-remedy investigation, native to AIDTRACE: shared session, tenant-scoped FalkorDB graph,
 *  verdicts computed by the graph (never by a language model), approvals bound to the reviewed revision. */
export function ConsumerWorkspace() {
  const [analysis, setAnalysis] = useState<ConsumerAnalysis | null>(null);
  const [stored, setStored] = useState<ConsumerState | null>(null);
  const [graph, setGraph] = useState<LabGraph>(EMPTY);
  const [actions, setActions] = useState<ConsumerAction[]>([]);
  const [complaint, setComplaint] = useState(SAMPLE);
  const [parsed, setParsed] = useState<ConsumerIntake | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [approval, setApproval] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [s, g, a, acts] = await Promise.all([consumerState(), consumerGraph(), consumerAnalyze(), consumerActions()]);
    setStored(s); setGraph(g.graph); setAnalysis(a); setActions(acts.actions);
    if (a.status !== "OK") setError(a.message ?? `Analysis returned ${a.status}`);
  }, []);

  const run = useCallback(async (work: () => Promise<unknown>) => {
    setBusy(true); setError(null); setApproval(null);
    try { await work(); await refresh(); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }, [refresh]);

  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const health = await consumerHealth();
        if (!health.falkordb) throw new Error(`FalkorDB is not reachable${health.message ? `: ${health.message}` : ""}. No decision can be made without the graph.`);
        if (!health.case_loaded) await consumerLoad();
        if (live) await refresh();
      } catch (e) { if (live) setError(e instanceof Error ? e.message : String(e)); }
      finally { if (live) setBusy(false); }
    })();
    return () => { live = false; };
  }, [refresh]);

  async function parseComplaint() {
    setError(null);
    try { setParsed(await consumerIntake(complaint)); } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }
  async function approve() {
    if (!analysis?.draft || !analysis.revision) return;
    try {
      await consumerApprove(analysis.draft.action_id, analysis.revision);
      setApproval(`Approved locally at revision ${analysis.revision}. Nothing was submitted externally.`);
      setActions((await consumerActions()).actions);
    } catch (e) { setError(`Approval refused: ${e instanceof Error ? e.message : e}`); }
  }

  const marks = useMemo(() => {
    const nodeMarks: Record<string, string> = {};
    for (const v of analysis?.verdicts ?? []) {
      nodeMarks[`Strategy:${v.strategy_id}`] = v.verdict === "VERIFIED" ? "proceed" : v.verdict === "REJECTED" ? "hold" : "insufficient_evidence";
    }
    return { node_marks: nodeMarks };
  }, [analysis]);
  const plan = analysis?.plan;
  const summary = !plan ? "" : plan.status === "NO_VERIFIED_STRATEGY"
    ? `No strategy is verified yet. The most useful missing item is ${plan.next_evidence?.label ?? "unknown"}.`
    : plan.status === "NEEDS_USER_DECISION" ? `A draft is ready for review: ${plan.draft_strategy_id}. Other verified options conflict, so you choose.`
    : `A draft is ready for review: ${plan.draft_strategy_id}.`;
  const reviewed = actions.filter((a) => a.status === "INVALIDATED" || a.status === "APPROVED_LOCAL");

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-title font-semibold">Resolve · cross-domain remedy investigation on FALKOR DB</h2>
          <p className="mt-1 max-w-3xl text-caption leading-relaxed text-muted">One complaint, several institutions. The graph decides, not the language model. Approvals are bound to the evidence revision they reviewed; nothing is submitted externally.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <StatusBadge tone={analysis?.status === "OK" ? "verified" : "caution"}>{analysis?.status === "OK" ? `revision ${analysis.revision}` : analysis?.status ?? "loading"}</StatusBadge>
          {analysis?.independent_check && <StatusBadge tone={analysis.independent_check.agrees ? "verified" : "danger"}>independent Cypher check {analysis.independent_check.agrees ? "agrees" : "disagrees"}</StatusBadge>}
        </div>
      </div>
      {error && <p role="alert" className="border-l-2 border-danger bg-surface p-3 text-caption text-danger">{error}</p>}

      <div className="grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)_340px]">
        <section className="space-y-4" aria-label="Intake and evidence">
          <div className="border border-line bg-surface p-4">
            <h3 className="text-body font-semibold">Complaint intake</h3>
            <label className="sr-only" htmlFor="complaint">Complaint</label>
            <textarea id="complaint" className="mt-2 h-32 w-full border border-line bg-surface p-2 text-caption" value={complaint} onChange={(e) => setComplaint(e.target.value)} />
            <div className="mt-2 flex flex-wrap gap-2">
              <Button variant="primary" onClick={() => void parseComplaint()}>Parse complaint</Button>
              <Button variant="ghost" disabled={busy} onClick={() => void run(async () => {})}>Re-run analysis</Button>
              <Button variant="ghost" disabled={busy} onClick={() => void run(consumerLoad)}>Reload synthetic case</Button>
            </div>
            {parsed && (
              <dl className="mt-3 space-y-1 text-caption">
                <div className="flex justify-between gap-3"><dt className="text-muted">Status</dt><dd className="font-medium">{parsed.status}</dd></div>
                <div className="flex justify-between gap-3"><dt className="text-muted">Domains</dt><dd className="text-right font-medium">{parsed.domains.join(", ") || "—"}</dd></div>
                {parsed.missing.length > 0 && <div><dt className="text-muted">Missing</dt><dd className="font-medium">{parsed.missing.join("; ")}</dd></div>}
                {parsed.ignored_instructions.length > 0 && <div><dt className="text-muted">Ignored instructions in the text</dt><dd className="font-medium">{parsed.ignored_instructions.join("; ")}</dd></div>}
              </dl>
            )}
          </div>
          <div className="border border-line bg-surface p-4">
            <h3 className="text-body font-semibold">Evidence on file</h3>
            <ul className="mt-2 space-y-2">{(stored?.evidence ?? []).map((e) => (
              <li key={e.id} className="flex items-center justify-between gap-2 border-b border-line pb-2 text-caption">
                <span><span className="font-mono text-micro">{e.id}</span><br /><span className="text-muted">{e.type}{e.amount ? ` · ${e.amount.toFixed(2)}` : ""} · {e.status.toLowerCase()}</span></span>
                <Button variant="ghost" disabled={busy} onClick={() => void run(() => consumerSetEvidence(e.id, e.status === "PRESENT" ? "MISSING" : "PRESENT"))}>{e.status === "PRESENT" ? "Remove" : "Attach"}</Button>
              </li>
            ))}</ul>
            <h3 className="mt-4 text-body font-semibold">Sources</h3>
            <ul className="mt-2 space-y-2">{(stored?.sources ?? []).map((s) => (
              <li key={s.id} className="flex items-center justify-between gap-2 border-b border-line pb-2 text-caption">
                <span><span className="font-mono text-micro">{s.id}</span><br /><span className="text-muted">{s.title} · {s.verified ? "verified" : "not verified"}</span></span>
                <Button variant="ghost" disabled={busy} onClick={() => void run(() => consumerSetSource(s.id, !s.verified))}>{s.verified ? "Unverify" : "Verify"}</Button>
              </li>
            ))}</ul>
            <Button className="mt-3 w-full" variant="ghost" disabled={busy}
              onClick={() => void run(() => consumerDropEdge({ src_label: "Evidence", src_id: "EVD-3", rel: "REFUNDS", dst_label: "Evidence", dst_id: "EVD-1" }))}>Simulate data error: drop refund link</Button>
          </div>
        </section>

        <section className="min-w-0 space-y-4" aria-label="Graph and findings">
          {graph.nodes.length > 0 && <GraphViews graph={graph} marks={marks} selected={selected} onSelect={setSelected} />}
          <div className="border border-line bg-surface p-4">
            <h3 className="text-body font-semibold">Cross-domain findings</h3>
            {analysis?.cross_domain ? (
              <ul className="mt-2 space-y-1 text-caption">
                {analysis.cross_domain.shared_evidence.map((s) => <li key={s.evidence_id}>{s.evidence_id} {s.type} ({s.status}) is needed by {s.domains.join(" and ")}</li>)}
                {analysis.cross_domain.dependencies.map((d) => <li key={d.condition}>{d.condition} depends on {d.depends_on}; affects {d.strategies.join(", ")}</li>)}
                {analysis.cross_domain.conflicts.map((c) => <li key={c.event} className="text-danger">{c.strategies.join(" and ")} both claim recovery for {c.event}</li>)}
              </ul>
            ) : <p className="mt-2 text-caption text-muted">Run the analysis to see cross-domain findings.</p>}
          </div>
          <div className="border border-line bg-surface p-4">
            <h3 className="text-body font-semibold">Agent trace</h3>
            <ol className="mt-2 max-h-64 space-y-1 overflow-auto text-caption">{(analysis?.trace ?? []).map((t, i) => <li key={i}><strong>{t.agent}</strong> · {t.event}: <span className="text-muted">{t.detail}</span></li>)}</ol>
          </div>
        </section>

        <section className="space-y-4" aria-label="Plan and review">
          <div className="border border-line bg-surface p-4">
            <h3 className="text-body font-semibold">Plan</h3>
            {plan && <p className="mt-2 border-l-2 border-line pl-3 text-caption"><strong>{plan.status.replace(/_/g, " ")}</strong><br />{summary}</p>}
            <ul className="mt-3 space-y-2">{analysis?.verdicts?.map((v) => (
              <li key={v.strategy_id} className="border border-line p-3 text-caption">
                <div className="flex items-center justify-between gap-2"><span className="font-mono text-micro">{v.strategy_id}</span><StatusBadge tone={VERDICT_TONE[v.verdict]}>{v.verdict.replace(/_/g, " ")}</StatusBadge></div>
                <p className="mt-1"><strong>{v.title}</strong> · {v.domains.join(", ")}</p>
                {v.blocked_by && <p className="text-danger">blocked by {v.blocked_by}</p>}
                {v.reasons.map((r, i) => <p key={i} className="text-muted">• {r}</p>)}
                <details className="mt-1"><summary className="cursor-pointer text-micro">Provenance paths</summary>{v.conditions.flatMap((c) => c.paths.map((p, i) => <p key={`${c.id}${i}`} className="break-all font-mono text-micro text-muted">{p}</p>))}</details>
              </li>
            ))}</ul>
          </div>
          <div className="border border-line bg-surface p-4">
            <h3 className="text-body font-semibold">Missing evidence, ranked</h3>
            {(analysis?.evidence_gaps ?? []).length === 0 && <p className="mt-2 text-caption text-muted">Nothing outstanding.</p>}
            <ul className="mt-2 space-y-2 text-caption">{(analysis?.evidence_gaps ?? []).map((g) => (
              <li key={g.item_id}><strong>{g.item_id}</strong> {g.label}: changes {g.changes.length} verdict(s){g.verified_gain > 0 && ` · would verify ${g.verified_gain}`}
                {g.changes.map((c) => <span key={c.strategy_id} className="block text-micro text-muted">{c.strategy_id}: {c.from} → {c.to}</span>)}</li>
            ))}</ul>
          </div>
          <div className="border border-line bg-surface p-4">
            <h3 className="text-body font-semibold">Draft for human review</h3>
            {reviewed.map((a) => (
              <p key={a.action_id} className="mt-2 text-caption"><span className="font-mono text-micro">{a.action_id}</span> <StatusBadge tone={a.status === "APPROVED_LOCAL" ? "verified" : "danger"}>{a.status}</StatusBadge>
                <span className="block text-micro text-muted">{a.status === "INVALIDATED" ? "Evidence changed after this approval, so it no longer applies. Re-run the analysis." : `Approved locally by ${a.approved_by} at revision ${a.approved_revision}. Not submitted.`}</span></p>
            ))}
            {analysis?.draft ? (
              <div className="mt-3">
                <pre className="max-h-56 overflow-auto whitespace-pre-wrap border border-line bg-surface-2 p-3 font-mono text-micro">{analysis.draft.body}</pre>
                <Button className="mt-2 w-full" variant="primary" disabled={busy || !!approval} onClick={() => void approve()}>I reviewed this: approve locally</Button>
                {approval && <p role="status" className="mt-2 text-micro text-muted">{approval}</p>}
                <p className="mt-2 text-micro text-muted">Approval is recorded under your signed-in identity. External submission is disabled.</p>
              </div>
            ) : <p className="mt-2 text-caption text-muted">No draft. One is created only from a VERIFIED strategy once its evidence is on file.</p>}
          </div>
        </section>
      </div>
    </div>
  );
}
