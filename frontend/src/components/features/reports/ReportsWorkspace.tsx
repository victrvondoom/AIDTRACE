"use client";

// Reports, built only from what the integrated runtimes actually produced: ResolveAI case reports, GreenChain procurement memos and
// approval receipts. Each report states what ran and what did not; exports are the same text the preview shows.
import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, FilterTabs, StatusBadge } from "@/components/ui";
import {
  memoryGreenchainReport, memorySnapshot, platformCases, platformReport, platformStatus,
  type MemorySnapshot, type PlatformCase, type PlatformInvestigation, type PlatformReport,
} from "@/lib/lab-api";
import { buildCaseReport } from "@/lib/resolveai-report";

type Tab = "cases" | "procurement" | "receipts";

function download(name: string, text: string, type = "text/markdown") {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url; a.download = name; a.click();
  URL.revokeObjectURL(url);
}
const csv = (rows: string[][]) => rows.map((r) => r.map((c) => `"${String(c ?? "").replace(/"/g, '""')}"`).join(",")).join("\n");

export function ReportsWorkspace() {
  const [tab, setTab] = useState<Tab>("cases");
  const [cases, setCases] = useState<PlatformCase[]>([]);
  const [workerUp, setWorkerUp] = useState<boolean | null>(null);
  const [snap, setSnap] = useState<MemorySnapshot | null>(null);
  const [text, setText] = useState<{ title: string; body: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [s, st] = await Promise.all([memorySnapshot().catch((e: unknown) => { setError(e instanceof Error ? e.message : "Agent memory could not be read."); return null; }),
      platformStatus().catch(() => null)]);
    setSnap(s); setWorkerUp(st?.connected === true);
    if (st?.connected) setCases((await platformCases().catch(() => ({ cases: [] as PlatformCase[] }))).cases);
  }, []);
  useEffect(() => { const t = window.setTimeout(() => void load(), 0); return () => window.clearTimeout(t); }, [load]);

  const scenarios = useMemo(() => [...new Set((snap?.decisions ?? []).map((d) => /^gc:([^:]+):/.exec(d.id)?.[1]).filter((x): x is string => Boolean(x)))], [snap]);

  async function caseReport(c: PlatformCase) {
    setBusy(true); setError(null);
    try {
      const r: PlatformReport = await platformReport(c.id);
      const run = [...r.agent_runs].reverse().find((x) => x.workflow_name === "kairos_evidence_investigation");
      const investigation = (run?.output ?? null) as PlatformInvestigation | null;
      const extra = r.events.length ? `\n## Decision history\n\n${r.events.map((e) => `- ${(e.created_at ?? "").slice(0, 19).replace("T", " ")} · ${e.title ?? e.event_type}${e.actor ? ` (${e.actor})` : ""}`).join("\n")}\n` : "";
      setText({ title: `kairos-case-${c.id.slice(0, 8)}.md`, body: buildCaseReport(c, investigation, null) + extra });
    } catch (e) { setError(e instanceof Error ? e.message : "The report could not be built."); } finally { setBusy(false); }
  }
  async function memo(sid: string) {
    setBusy(true); setError(null);
    try { const r = await memoryGreenchainReport(sid); setText({ title: `greenchain-memo-${sid}.md`, body: r.markdown }); }
    catch (e) { setError(e instanceof Error ? e.message : "The memo could not be built."); } finally { setBusy(false); }
  }

  const receipts = snap?.approvals ?? [];
  const receiptsCsv = csv([["approval", "decision", "revision", "graph_revision", "status", "approved_by", "approved_at"], ...receipts.map((a) => [a.id, a.decision_id, a.revision_id, a.graph_revision, a.approval_status, a.approved_by, a.approved_at])]);
  return (
    <section className="space-y-4" aria-labelledby="reports-heading">
      <div>
        <h2 id="reports-heading" className="text-title font-semibold">Reports and evidence</h2>
        <p className="mt-1 max-w-3xl text-caption leading-relaxed text-muted">Reports are written only from what ran. Each says which stages executed, which did not, and which numbers are modelled or counterfactual. Download them as the same text you preview.</p>
      </div>
      {error && <p role="alert" className="border-l-2 border-danger bg-surface p-3 text-caption text-danger">{error}</p>}
      <FilterTabs tabs={[{ key: "cases", label: "Case reports", count: cases.length }, { key: "procurement", label: "Procurement memos", count: scenarios.length }, { key: "receipts", label: "Approval receipts", count: receipts.length }]} active={tab} onChange={(k) => { setTab(k as Tab); setText(null); }} />

      <div className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
        <div className="space-y-2 border border-line bg-surface p-4">
          {tab === "cases" && (workerUp === false ? <p className="text-caption text-muted">The ResolveAI worker is not connected, so there are no case reports.</p> :
            cases.length === 0 ? <p className="text-caption text-muted">No cases yet. Create one in ResolveAI and run its evidence investigation.</p> :
              <ul className="space-y-1">{cases.map((c) => <li key={c.id}><Button variant="ghost" className="w-full justify-start" disabled={busy} onClick={() => void caseReport(c)}>{c.title}</Button></li>)}</ul>)}
          {tab === "procurement" && (scenarios.length === 0 ? <p className="text-caption text-muted">No GreenChain decision is recorded. Record one in Agent Memory.</p> :
            <ul className="space-y-1">{scenarios.map((s) => <li key={s}><Button variant="ghost" className="w-full justify-start" disabled={busy} onClick={() => void memo(s)}>Scenario {s}</Button></li>)}</ul>)}
          {tab === "receipts" && <><p className="text-caption text-muted">Every human approval on record, including ones voided because the evidence changed.</p>
            <Button variant="primary" disabled={receipts.length === 0} onClick={() => download("kairos-approval-receipts.csv", receiptsCsv, "text/csv")}>Download CSV</Button></>}
        </div>

        <div className="min-w-0 space-y-3">
          {tab !== "receipts" && !text && <p className="border border-line bg-surface p-6 text-caption text-muted">Choose a report on the left to preview it.</p>}
          {tab !== "receipts" && text && (
            <div className="space-y-2 border border-line bg-surface p-4">
              <div className="flex flex-wrap items-center justify-between gap-2"><p className="font-mono text-micro text-muted">{text.title}</p>
                <div className="flex gap-2"><Button variant="ghost" onClick={() => void navigator.clipboard?.writeText(text.body)}>Copy</Button><Button variant="primary" onClick={() => download(text.title, text.body)}>Download Markdown</Button></div></div>
              <pre className="max-h-[560px] overflow-auto whitespace-pre-wrap border border-line bg-surface-2 p-3 font-mono text-micro">{text.body}</pre>
            </div>)}
          {tab === "receipts" && (receipts.length === 0 ? <p className="border border-line bg-surface p-6 text-caption text-muted">No approval has been recorded yet.</p> : (
            <div className="overflow-x-auto border border-line bg-surface"><table className="w-full text-left text-caption">
              <caption className="sr-only">Approval receipts</caption>
              <thead className="bg-surface-2 text-muted"><tr>{["Status", "Approved by", "When", "Decision", "Revision hash"].map((h) => <th key={h} scope="col" className="p-2 font-semibold">{h}</th>)}</tr></thead>
              <tbody>{[...receipts].sort((a, b) => b.approved_at.localeCompare(a.approved_at)).map((a) => (
                <tr key={a.id} className="border-t border-line"><td className="p-2"><StatusBadge tone={a.approval_status === "VALID" ? "verified" : "danger"}>{a.approval_status.toLowerCase()}</StatusBadge></td>
                  <td className="p-2">{a.approved_by}</td><td className="p-2">{a.approved_at.slice(0, 19).replace("T", " ")}</td><td className="p-2 font-mono text-micro">{a.decision_id}</td><td className="p-2 font-mono text-micro">{a.graph_revision.slice(0, 12)}…</td></tr>))}</tbody>
            </table></div>))}
        </div>
      </div>
    </section>
  );
}
