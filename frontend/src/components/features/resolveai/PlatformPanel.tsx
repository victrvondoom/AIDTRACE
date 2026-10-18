"use client";

import { useEffect, useState } from "react";
import { Button, StatusBadge } from "@/components/ui";
import {
  platformCases, platformCreateCase, platformRunCase, platformStatus,
  type PlatformCase, type PlatformRun, type PlatformStatus,
} from "@/lib/lab-api";

const EMPTY = { domain: "health_insurance", title: "", institution_name: "", summary: "" };

/** ResolveAI multi-agent platform (RESOLVE-AI-main) behind the AIDTRACE gateway. Shows exactly what the private worker
 *  returns; when the worker is not connected it says so and offers no simulated output. */
export function PlatformPanel() {
  const [status, setStatus] = useState<PlatformStatus | null>(null);
  const [cases, setCases] = useState<PlatformCase[]>([]);
  const [form, setForm] = useState(EMPTY);
  const [result, setResult] = useState<PlatformRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const s = await platformStatus();
        if (!live) return;
        setStatus(s);
        if (s.connected) setCases((await platformCases()).cases);
      } catch (e) { if (live) setError(e instanceof Error ? e.message : "The platform gateway is unavailable."); }
    })();
    return () => { live = false; };
  }, []);

  async function create() {
    setBusy(true); setError(null);
    try { await platformCreateCase(form); setForm(EMPTY); setCases((await platformCases()).cases); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not create the case."); }
    finally { setBusy(false); }
  }
  async function run(id: string) {
    setBusy(true); setError(null); setResult(null);
    try { setResult(await platformRunCase(id)); } catch (e) { setError(e instanceof Error ? e.message : "The agent run failed."); }
    finally { setBusy(false); }
  }

  const connected = status?.connected === true;
  const input = "mt-1 w-full border border-line bg-surface px-2 min-h-11";
  return (
    <section className="space-y-3 border-t border-line pt-6" aria-labelledby="platform-heading">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 id="platform-heading" className="text-title font-semibold">ResolveAI agent platform</h2>
          <p className="mt-1 max-w-3xl text-caption leading-relaxed text-muted">Multi-agent case investigation with retrieval and eight domain packs, run by the migrated RESOLVE-AI-main worker. It authenticates through your AIDTRACE session and keeps cases separate per site.</p>
        </div>
        <StatusBadge tone={connected ? "verified" : "caution"}>{status ? (connected ? "worker connected" : "not connected") : "checking"}</StatusBadge>
      </div>
      {error && <p role="alert" className="border-l-2 border-danger bg-surface p-3 text-caption text-danger">{error}</p>}
      {status && !connected && (
        <div className="border-l-2 border-caution bg-surface p-4 text-caption">
          <p className="font-medium">The private ResolveAI worker is not connected, so no agent runs are available.</p>
          <p className="mt-1 text-muted">{status.message}</p>
          <p className="mt-1 text-muted">{status.setup} It needs Supabase, Qdrant, Neo4j, Redis and a model key (Gemini or NVIDIA), none of which are configured on this machine.</p>
        </div>
      )}
      {connected && (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <div className="space-y-3 border border-line bg-surface p-4">
            <h3 className="text-body font-semibold">New case</h3>
            <label className="block text-caption">Domain pack
              <select className={input} value={form.domain} onChange={(e) => setForm({ ...form, domain: e.target.value })}>
                {(status?.domains ?? []).map((d) => <option key={d.id} value={d.id} disabled={!d.active}>{d.label}{d.active ? "" : " (not active)"}</option>)}
              </select></label>
            <label className="block text-caption">Title<input className={input} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></label>
            <label className="block text-caption">Institution<input className={input} value={form.institution_name} onChange={(e) => setForm({ ...form, institution_name: e.target.value })} /></label>
            <label className="block text-caption">What happened<textarea className={`${input} h-28`} value={form.summary} onChange={(e) => setForm({ ...form, summary: e.target.value })} /></label>
            <Button variant="primary" disabled={busy || form.title.length < 4 || form.summary.length < 10} onClick={() => void create()}>Create case</Button>
          </div>
          <div className="space-y-3 border border-line bg-surface p-4">
            <h3 className="text-body font-semibold">Your cases</h3>
            {cases.length === 0 && <p className="text-caption text-muted">No cases yet.</p>}
            <ul className="space-y-2">{cases.map((c) => (
              <li key={c.id} className="flex items-center justify-between gap-2 border-b border-line pb-2 text-caption">
                <span><strong>{c.title}</strong><span className="block text-micro text-muted">{c.domain} · {c.institution_name} · {c.status}</span></span>
                <Button variant="ghost" disabled={busy} onClick={() => void run(c.id)}>Run agents</Button>
              </li>
            ))}</ul>
          </div>
        </div>
      )}
      {result && (
        <div className="space-y-3 border border-line bg-surface p-4 text-caption">
          <h3 className="text-body font-semibold">Agent result · {result.status} <span className="font-normal text-muted">({result.llm_call_count ?? 0} model calls)</span></h3>
          {result.strategy && <p><strong>Strategy.</strong> {result.strategy}</p>}
          {result.evidence_summary && <p><strong>Evidence.</strong> {result.evidence_summary}</p>}
          {result.final_report && <pre className="max-h-64 overflow-auto whitespace-pre-wrap border border-line bg-surface-2 p-3 font-mono text-micro">{result.final_report}</pre>}
          <p className="text-micro text-muted">{result.agent_trace?.length ?? 0} agent steps and {result.citations?.length ?? 0} citations recorded. Drafts are for human review; nothing is submitted.</p>
        </div>
      )}
    </section>
  );
}
