"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { GraphViews } from "@/components/graph-views";
import { Button, StatusBadge } from "@/components/ui";
import type { LabGraph } from "@/lib/graph-layout";
import {
  fraudActions, fraudApprove, fraudFlagged, fraudHealth, fraudReject, fraudRing, fraudRun, fraudSeed, fraudStart,
  type FraudAction, type FraudEvent, type FraudHealth, type FraudRun,
} from "@/lib/lab-api";

const ACTION_TONE: Record<string, "verified" | "danger" | "caution" | "neutral"> = { EXECUTED: "verified", REJECTED: "neutral", INVALIDATED: "danger", PROPOSED: "caution" };

function eventLine(e: FraudEvent): string {
  switch (e.type) {
    case "step": case "reasoning": return e.text ?? "";
    case "tool": return `${e.name}: ${e.summary ?? ""}`;
    case "query": return `${e.cypher?.slice(0, 110) ?? ""}… (${e.rows} rows, ${e.ms} ms)`;
    case "proposal": return `Proposed ${e.action?.type} for ${e.action?.targets.join(", ")}`;
    case "rejected": return `Policy refused: ${e.reason}`;
    case "done": return `Finished (${e.mode} planner)`;
    case "error": return `Error: ${e.message}`;
    default: return e.type;
  }
}

/** Original Track 01 fraud investigation inside AIDTRACE. The agent gathers evidence with graph tools; code (not a
 *  model) decides the freeze set; a human approves, and an approval on changed evidence is refused. Every event
 *  below is a record of real backend execution. */
export function FraudWorkspace() {
  const [health, setHealth] = useState<FraudHealth | null>(null);
  const [run, setRun] = useState<FraudRun | null>(null);
  const [actions, setActions] = useState<FraudAction[]>([]);
  const [flagged, setFlagged] = useState<string[]>([]);
  const [ring, setRing] = useState<{ account: string; graph: LabGraph; members: number } | null>(null);
  const [useLlm, setUseLlm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const loadData = useCallback(async () => {
    const [a, f] = await Promise.all([fraudActions(), fraudFlagged()]);
    setActions(a.actions); setFlagged([...new Set(f.transactions.map((t) => t.account_id))]);
  }, []);

  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const h = await fraudHealth();
        if (!live) return;
        setHealth(h);
        if (h.loaded) await loadData();
      } catch (e) { if (live) setError(e instanceof Error ? e.message : "Fraud service unavailable."); }
    })();
    return () => { live = false; if (timer.current) clearTimeout(timer.current); };
  }, [loadData]);

  async function seed() {
    setBusy(true); setError(null); setMessage(null);
    try { await fraudSeed(); setHealth(await fraudHealth()); await loadData(); setRun(null); setMessage("Synthetic fraud network loaded into this site's graph."); }
    catch (e) { setError(e instanceof Error ? e.message : "Seeding failed."); }
    finally { setBusy(false); }
  }

  function poll(runId: string) {
    timer.current = setTimeout(async () => {
      try {
        const r = await fraudRun(runId);
        setRun(r);
        if (r.status === "running") poll(runId); else { await loadData(); setBusy(false); }
      } catch (e) { setError(e instanceof Error ? e.message : "Lost the run."); setBusy(false); }
    }, 700);
  }
  async function start() {
    setBusy(true); setError(null); setMessage(null); setRun(null);
    try { const { run_id } = await fraudStart(useLlm); poll(run_id); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not start."); setBusy(false); }
  }

  async function decide(a: FraudAction, approve: boolean) {
    setError(null); setMessage(null);
    try {
      if (approve) { const r = await fraudApprove(a.action_id); setMessage(`Approved. Froze ${r.frozen_accounts.join(", ")} (synthetic graph only). Receipt ${r.receipt.slice(0, 12)}…`); }
      else { await fraudReject(a.action_id); setMessage("Rejected."); }
      await loadData();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Refused.");
      await loadData();
    }
  }
  async function showRing(account: string) {
    setError(null);
    try { const r = await fraudRing(account); setRing({ account, graph: r.graph, members: r.members.length }); } catch (e) { setError(e instanceof Error ? e.message : "Ring lookup failed."); }
  }

  const proposals = run?.proposals ?? [];
  const open = actions.filter((a) => a.status === "PROPOSED");

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-title font-semibold">Fraud investigation · agent operations</h2>
          <p className="mt-1 max-w-3xl text-caption leading-relaxed text-muted">An agent follows flagged transactions through shared devices and cards. Shared IP addresses alone are weak evidence and never justify action. The freeze set is derived by policy code from the graph, a person approves, and an approval is refused if the evidence changed after the proposal. Synthetic data only; nothing leaves the graph.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <StatusBadge tone={health?.falkordb ? "verified" : "danger"}>{health?.falkordb ? "FalkorDB connected" : "FalkorDB unavailable"}</StatusBadge>
          <StatusBadge tone="neutral">LLM planner: {health?.llm_available ? "configured" : "not configured (deterministic)"}</StatusBadge>
        </div>
      </div>
      {error && <p role="alert" className="border-l-2 border-danger bg-surface p-3 text-caption text-danger">{error}</p>}
      {message && <p role="status" className="border-l-2 border-verified bg-surface p-3 text-caption">{message}</p>}

      <div className="flex flex-wrap items-center gap-2 border border-line bg-surface p-3">
        <Button disabled={busy || !health?.falkordb} onClick={() => void seed()}>{health?.loaded ? "Reload synthetic network" : "Load synthetic network"}</Button>
        <Button variant="primary" disabled={busy || !health?.loaded} onClick={() => void start()}>{busy && run?.status === "running" ? "Investigating…" : "Start investigation"}</Button>
        {health?.llm_available && <label className="flex items-center gap-2 text-caption"><input type="checkbox" checked={useLlm} onChange={(e) => setUseLlm(e.target.checked)} />Use the Claude planner</label>}
        {!health?.loaded && health?.falkordb && <span className="text-caption text-muted">Load the synthetic network first.</span>}
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <section className="border border-line bg-surface p-4" aria-label="Agent execution trace">
          <h3 className="text-body font-semibold">Agent execution {run && <span className="font-normal text-muted">· {run.mode} planner · {run.status}</span>}</h3>
          {!run && <p className="mt-2 text-caption text-muted">No run yet. Starting one records every step, tool call and graph query below.</p>}
          <ol className="mt-2 max-h-[420px] space-y-1 overflow-auto text-caption" aria-live="polite">
            {(run?.events ?? []).map((e) => (
              <li key={e.seq} className={`border-l-2 pl-2 ${e.type === "error" || e.type === "rejected" ? "border-danger" : e.type === "proposal" ? "border-caution" : e.type === "query" ? "border-line" : "border-info"}`}>
                <span className="font-mono text-micro text-muted">{e.type}</span> {eventLine(e)}
              </li>
            ))}
          </ol>
        </section>

        <section className="space-y-4" aria-label="Proposals and actions">
          <div className="border border-line bg-surface p-4">
            <h3 className="text-body font-semibold">Proposed actions awaiting a human</h3>
            {open.length === 0 && <p className="mt-2 text-caption text-muted">None. {proposals.length > 0 ? "Everything from this run has been decided." : "Run an investigation to generate proposals."}</p>}
            <ul className="mt-2 space-y-3">{open.map((a) => (
              <li key={a.action_id} className="border border-line p-3 text-caption">
                <div className="flex items-center justify-between gap-2"><span className="font-mono text-micro">{a.action_id}</span><StatusBadge tone={ACTION_TONE[a.status] ?? "neutral"}>{a.status}</StatusBadge></div>
                <p className="mt-1">Freeze <strong>{a.targets.length} accounts</strong>: {a.targets.join(", ")}</p>
                <p className="mt-1 text-micro text-muted">{a.rule}</p>
                <div className="mt-2 flex gap-2"><Button variant="primary" onClick={() => void decide(a, true)}>Approve (synthetic)</Button><Button variant="ghost" onClick={() => void decide(a, false)}>Reject</Button><Button variant="ghost" onClick={() => void showRing(a.targets[0])}>Show ring</Button></div>
              </li>
            ))}</ul>
          </div>
          <div className="border border-line bg-surface p-4">
            <h3 className="text-body font-semibold">Decided</h3>
            <ul className="mt-2 space-y-1 text-caption">{actions.filter((a) => a.status !== "PROPOSED").map((a) => (
              <li key={a.action_id}><span className="font-mono text-micro">{a.action_id}</span> <StatusBadge tone={ACTION_TONE[a.status] ?? "neutral"}>{a.status}</StatusBadge> <span className="text-muted">{a.targets.join(", ")}</span>{a.receipt && <span className="block font-mono text-micro text-muted">receipt {a.receipt.slice(0, 16)}…</span>}</li>
            ))}</ul>
            {actions.every((a) => a.status === "PROPOSED") && <p className="mt-1 text-caption text-muted">Nothing decided yet.</p>}
          </div>
          <div className="border border-line bg-surface p-4">
            <h3 className="text-body font-semibold">Inspect an account&apos;s ring</h3>
            <ul className="mt-2 flex flex-wrap gap-2">{flagged.map((id) => <li key={id}><Button variant="ghost" onClick={() => void showRing(id)}>{id}</Button></li>)}</ul>
            {flagged.length === 0 && <p className="mt-1 text-caption text-muted">Load the network to list flagged accounts.</p>}
          </div>
        </section>
      </div>
      {ring && (
        <div>
          <p className="mb-2 text-caption text-muted">Evidence paths from <strong>{ring.account}</strong>: {ring.members} account(s) linked by shared device or card.</p>
          <GraphViews graph={ring.graph} />
        </div>
      )}
    </div>
  );
}
