"use client";

// Agent Operations: the four agent runtimes AIDTRACE hosts, side by side. Status, tools and recent runs are read from each runtime now;
// the interface matrix says plainly which shared capability each one provides natively, only through AIDTRACE, or not at all.
import { useCallback, useEffect, useState } from "react";
import { Button, StatusBadge } from "@/components/ui";
import { agentInvoke, agentRuns, agentRuntimes, memoryHandoffs, type AgentRun, type AgentRuntimes, type CapabilityState, type Handoff } from "@/lib/lab-api";

const TONE: Record<CapabilityState, "verified" | "caution" | "danger"> = { OPERATIONAL: "verified", LIMITED: "caution", UNAVAILABLE: "danger" };
const CELL: Record<string, { text: string; cls: string }> = {
  native: { text: "native", cls: "text-verified" }, via_kairos: { text: "via AIDTRACE", cls: "text-caution" }, none: { text: "not provided", cls: "text-muted" },
};
const label = (s: string) => s.replace(/_/g, " ");

export function AgentOpsWorkspace() {
  const [data, setData] = useState<AgentRuntimes | null>(null);
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [handoffs, setHandoffs] = useState<Handoff[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [tool, setTool] = useState("greenchain.score_suppliers");
  const [args, setArgs] = useState({ query: "waiting period pre-existing disease", domain: "health_insurance", transport_mode: "sea", agent_id: "agent:operator", fact_key: "" });
  const [result, setResult] = useState<{ tool: string; result: Record<string, unknown>; read_only: boolean } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [r, u, h] = await Promise.all([agentRuntimes(), agentRuns(30), memoryHandoffs().catch(() => ({ handoffs: [] as Handoff[] }))]);
      setData(r); setRuns(u.runs); setHandoffs(h.handoffs); setError(null);
    } catch (e) { setError(e instanceof Error ? e.message : "Agent runtimes could not be read."); }
  }, []);
  useEffect(() => { const t = window.setTimeout(() => void load(), 0); return () => window.clearTimeout(t); }, [load]);

  const invokable = (data?.runtimes ?? []).flatMap((r) => r.tools.filter((t) => t.invokable).map((t) => ({ key: `${r.id}.${t.name}`, runtime: r, tool: t })));
  async function invoke() {
    const [runtime, name] = tool.split(".");
    const payload: Record<string, unknown> = name === "search_corpus" ? { query: args.query, domain: args.domain } : name === "score_suppliers" ? { transport_mode: args.transport_mode } : { agent_id: args.agent_id, fact_key: args.fact_key || undefined };
    setBusy(true); setError(null);
    try { const r = await agentInvoke(runtime, name, payload); setResult({ tool, result: r.result, read_only: r.read_only }); await load(); }
    catch (e) { setError(e instanceof Error ? e.message : "The tool call failed."); } finally { setBusy(false); }
  }

  return (
    <section className="space-y-5" aria-labelledby="agents-heading">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="agents-heading" className="text-title font-semibold">Agent operations</h2>
          <p className="mt-1 max-w-3xl text-caption leading-relaxed text-muted">Four agent runtimes run inside AIDTRACE, each in its own framework. This is one view over them: what is connected right now, what tools each exposes, what they ran, and which shared capabilities each really provides.</p>
        </div>
        <Button variant="ghost" onClick={() => void load()}>Refresh</Button>
      </div>
      {error && <p role="alert" className="border-l-2 border-danger bg-surface p-3 text-caption text-danger">{error}</p>}
      {!data && !error && <p role="status" className="text-caption text-muted">Probing runtimes…</p>}

      {data && (<>
        <div className="grid gap-4 md:grid-cols-2">{data.runtimes.map((r) => (
          <article key={r.id} className="space-y-2 border border-line bg-surface p-4 text-caption">
            <div className="flex items-start justify-between gap-2"><div><h3 className="text-body font-semibold">{r.name}</h3><p className="text-micro text-muted">{r.framework} · {r.origin}</p></div>
              <StatusBadge tone={TONE[r.status.state]}>{r.status.state.toLowerCase()}</StatusBadge></div>
            <p>{r.status.detail}</p>
            <ul className="flex flex-wrap gap-1">{r.tools.map((t) => <li key={t.name} title={t.description} className="border border-line px-2 py-0.5 text-micro">{t.name}{t.read_only ? "" : " ✎"}{t.invokable ? " ▸" : ""}</li>)}</ul>
            {r.limits.length > 0 && <ul className="list-disc space-y-0.5 pl-5 text-micro text-muted">{r.limits.map((l) => <li key={l}>{l}</li>)}</ul>}
          </article>))}</div>
        <p className="text-micro text-muted">✎ changes state (graph or worker) · ▸ can be run from the panel below.</p>

        <div className="overflow-x-auto border border-line bg-surface">
          <table className="w-full text-left text-caption">
            <caption className="p-3 text-left text-body font-semibold">Shared interface support</caption>
            <thead className="bg-surface-2 text-muted"><tr><th scope="col" className="p-2 font-semibold">Interface</th>{data.matrix.runtimes.map((r) => <th key={r.id} scope="col" className="p-2 font-semibold">{r.name}</th>)}</tr></thead>
            <tbody>{data.matrix.interfaces.map((i) => (
              <tr key={i} className="border-t border-line"><th scope="row" className="p-2 font-medium">{label(i)}</th>
                {data.matrix.runtimes.map((r) => { const c = CELL[r.support[i]] ?? CELL.none; return <td key={r.id} className={`p-2 ${c.cls}`}>{c.text}</td>; })}</tr>))}</tbody>
          </table>
        </div>

        <div className="grid gap-4 xl:grid-cols-2">
          <div className="space-y-3 border border-line bg-surface p-4">
            <h3 className="text-body font-semibold">Run a tool through the shared interface</h3>
            <div className="flex flex-wrap gap-2">
              <select aria-label="Tool" className="min-h-11 border border-line bg-surface px-2 text-caption" value={tool} onChange={(e) => setTool(e.target.value)}>
                {invokable.map((t) => <option key={t.key} value={t.key}>{t.runtime.name}: {label(t.tool.name)}</option>)}</select>
              <Button variant="primary" disabled={busy || invokable.length === 0} onClick={() => void invoke()}>{busy ? "Running…" : "Run"}</Button>
            </div>
            {tool.endsWith("search_corpus") && <div className="flex flex-wrap gap-2"><input aria-label="Domain pack" className="min-h-11 border border-line bg-surface px-2 text-caption" value={args.domain} onChange={(e) => setArgs({ ...args, domain: e.target.value })} />
              <input aria-label="Query" className="min-h-11 min-w-0 flex-1 border border-line bg-surface px-2 text-caption" value={args.query} onChange={(e) => setArgs({ ...args, query: e.target.value })} /></div>}
            {tool.endsWith("score_suppliers") && <select aria-label="Transport mode" className="min-h-11 border border-line bg-surface px-2 text-caption" value={args.transport_mode} onChange={(e) => setArgs({ ...args, transport_mode: e.target.value })}>{["sea", "air", "rail", "road"].map((m) => <option key={m}>{m}</option>)}</select>}
            {tool.endsWith("recall") && <div className="flex flex-wrap gap-2"><input aria-label="Agent id" className="min-h-11 border border-line bg-surface px-2 text-caption" value={args.agent_id} onChange={(e) => setArgs({ ...args, agent_id: e.target.value })} />
              <input aria-label="Fact key" placeholder="fact key (optional)" className="min-h-11 min-w-0 flex-1 border border-line bg-surface px-2 text-caption" value={args.fact_key} onChange={(e) => setArgs({ ...args, fact_key: e.target.value })} /></div>}
            {result && <div aria-live="polite" className="space-y-1 text-caption"><p className="text-micro text-muted">{result.tool} · {result.read_only ? "read-only" : "records which memory influenced the agent"}</p>
              <pre className="max-h-64 overflow-auto whitespace-pre-wrap border border-line bg-surface-2 p-2 font-mono text-micro">{JSON.stringify(result.result, null, 2).slice(0, 3000)}</pre></div>}
          </div>
          <div className="space-y-3 border border-line bg-surface p-4">
            <h3 className="text-body font-semibold">Recent runs across runtimes</h3>
            {runs.length === 0 ? <p className="text-caption text-muted">Nothing has run yet. Create a ResolveAI case, record a GreenChain decision or start a fraud investigation.</p> :
              <ul className="space-y-1 text-caption">{runs.map((r) => <li key={`${r.system}-${r.run_id}`} className="border-b border-line pb-1"><span className="font-medium">{r.system}</span> · {label(r.kind)} · <span className="text-muted">{r.status ?? "recorded"}</span><span className="block text-micro text-muted">{r.at?.slice(0, 19).replace("T", " ")} · {r.summary}</span></li>)}</ul>}
            <h4 className="pt-2 text-caption font-semibold">Handoffs</h4>
            {handoffs.length === 0 ? <p className="text-caption text-muted">No agent has recalled another agent&apos;s memory yet.</p> :
              <ul className="space-y-1 text-caption">{handoffs.map((h) => <li key={h.recall_session + h.memory_id}>{h.produced_by} → {h.recalled_by} <StatusBadge tone={h.usable ? "verified" : "danger"}>{h.usable ? "usable" : "stale"}</StatusBadge></li>)}</ul>}
          </div>
        </div>
      </>)}
    </section>
  );
}
