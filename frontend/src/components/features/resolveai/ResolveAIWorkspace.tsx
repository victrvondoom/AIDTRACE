"use client";

// Resolve investigations, native to the AIDTRACE hub, powered by FALKOR DB. Every number and sentence here comes from the private RESOLVE
// worker through /resolveai/platform/*. When the worker has no model provider, the UI says so on every surface that would
// otherwise have shown generated text, and never renders the worker's offline placeholders as analysis.
import { useCallback, useEffect, useMemo, useState } from "react";
import { GraphViews } from "@/components/graph-views";
import { Button, FilterTabs, StatusBadge } from "@/components/ui";
import type { LabGraph } from "@/lib/graph-layout";
import {
  platformCaseGraph, platformCases, platformCreateCase, platformInvestigate, platformReport, platformRunCase, platformSearch, platformStatus,
  platformSummary, platformTrail, memoryRememberCase,
  type PlatformCase, type PlatformCaseGraph, type PlatformInvestigation, type PlatformReport, type PlatformRun, type PlatformSearchHit,
  type PlatformStatus, type PlatformSummary,
} from "@/lib/lab-api";
import { buildCaseReport, isOfflineFallback } from "@/lib/resolveai-report";

const EMPTY = { domain: "health_insurance", title: "", institution_name: "", summary: "" };
type CaseTab = "evidence" | "agents" | "graph" | "history" | "report";
const label = (s: string) => s.replace(/_/g, " ");
const input = "mt-1 w-full border border-line bg-surface px-2 min-h-11 text-caption";

function toLabGraph(g: PlatformCaseGraph): LabGraph {
  return {
    nodes: g.nodes.map((n) => ({ id: n.id, label: n.label, type: n.kind, props: {} })),
    edges: g.edges.map((e) => ({ source: e.source, target: e.target, rel: "RELATES_TO", weight: 1, certainty: "definite" as const, at: null, until: null, disabled: false })),
  };
}

function ConfidenceBar({ value }: { value: number }) {
  return <span className="inline-block h-1.5 w-20 bg-surface-2 align-middle" role="img" aria-label={`confidence ${(value * 100).toFixed(0)} percent`}>
    <span className="block h-full bg-accent" style={{ width: `${Math.round(Math.min(1, Math.max(0, value)) * 100)}%` }} /></span>;
}

export function ResolveAIWorkspace() {
  const [status, setStatus] = useState<PlatformStatus | null>(null);
  const [cases, setCases] = useState<PlatformCase[]>([]);
  const [summary, setSummary] = useState<PlatformSummary | null>(null);
  const [form, setForm] = useState(EMPTY);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [tab, setTab] = useState<CaseTab>("evidence");
  const [mode, setMode] = useState<"cases" | "search">("cases");
  const [investigations, setInvestigations] = useState<Record<string, PlatformInvestigation>>({});
  const [runs, setRuns] = useState<Record<string, PlatformRun>>({});
  const [graph, setGraph] = useState<PlatformCaseGraph | null>(null);
  const [trail, setTrail] = useState<{ index: number; token: string; node_id: string }[]>([]);
  const [report, setReport] = useState<PlatformReport | null>(null);
  const [query, setQuery] = useState("");
  const [searchDomain, setSearchDomain] = useState("health_insurance");
  const [hits, setHits] = useState<PlatformSearchHit[] | null>(null);
  const [remembered, setRemembered] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [c, s] = await Promise.all([platformCases(), platformSummary().catch(() => null)]);
    setCases(c.cases); setSummary(s);
  }, []);

  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const s = await platformStatus();
        if (!live) return;
        setStatus(s);
        if (s.connected) await refresh();
      } catch (e) { if (live) setError(e instanceof Error ? e.message : "The Resolve gateway is unavailable."); }
    })();
    return () => { live = false; };
  }, [refresh]);

  const selected = useMemo(() => cases.find((c) => c.id === selectedId) ?? null, [cases, selectedId]);
  const investigation = selectedId ? investigations[selectedId] ?? null : null;
  const run = selectedId ? runs[selectedId] ?? null : null;
  const connected = status?.connected === true;
  const runtime = status?.runtime ?? null;
  const modelOn = runtime ? runtime.model_provider !== "disabled" && runtime.model_provider !== "missing_key" : false;

  async function guarded<T>(key: string, fn: () => Promise<T>): Promise<T | null> {
    setBusy(key); setError(null);
    try { return await fn(); } catch (e) { setError(e instanceof Error ? e.message : "The request failed."); return null; } finally { setBusy(null); }
  }

  async function create() {
    const made = await guarded("create", () => platformCreateCase(form));
    if (!made) return;
    setForm(EMPTY); await refresh(); setSelectedId(made.id); setTab("evidence"); setMode("cases");
  }
  async function investigate() {
    if (!selectedId) return;
    const r = await guarded("investigate", () => platformInvestigate(selectedId, modelOn));
    if (r) { setInvestigations((m) => ({ ...m, [selectedId]: r })); setGraph(null); setReport(null); await refresh(); }
  }
  async function remember() {
    if (!selectedId) return;
    const r = await guarded("remember", () => memoryRememberCase(selectedId));
    if (r) setRemembered((m) => ({ ...m, [selectedId]: r.remembered ? `Stored as ${r.memory_id} (${r.claims?.length ?? 0} claims, ${r.independent_sources} independent sources). Other agents can now recall it from Agent Memory.` : (r.reason ?? "Nothing was stored.") }));
  }
  async function runAgents() {
    if (!selectedId) return;
    const r = await guarded("agents", () => platformRunCase(selectedId));
    if (r) { setRuns((m) => ({ ...m, [selectedId]: r })); setReport(null); await refresh(); }
  }
  async function openTab(next: CaseTab) {
    setTab(next);
    if (!selectedId) return;
    if (next === "graph" && !graph) {
      const [g, t] = await Promise.all([guarded("graph", () => platformCaseGraph(selectedId)), platformTrail(selectedId).catch(() => null)]);
      if (g) setGraph(g);
      setTrail(t?.steps ?? []);
    }
    if ((next === "history" || next === "report") && !report) {
      const r = await guarded("report", () => platformReport(selectedId));
      if (r) setReport(r);
    }
  }
  async function search() {
    const r = await guarded("search", () => platformSearch(searchDomain, query));
    if (r) setHits(r.hits);
  }
  function download() {
    if (!selected) return;
    const md = buildCaseReport(selected, investigation, run);
    const url = URL.createObjectURL(new Blob([md], { type: "text/markdown" }));
    const a = document.createElement("a");
    a.href = url; a.download = `kairos-case-${selected.id.slice(0, 8)}.md`; a.click();
    URL.revokeObjectURL(url);
  }

  const offlineRun = run ? isOfflineFallback(run.research_summary) : false;
  return (
    <section className="space-y-4" aria-labelledby="resolve-heading">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="resolve-heading" className="text-title font-semibold">Resolve investigations (FALKOR DB)</h2>
          <p className="mt-1 max-w-3xl text-caption leading-relaxed text-muted">Open a case, retrieve and score the regulations and policy wording that bear on it, inspect the evidence and the agent steps, and export a report. Powered by FALKOR DB and the private Resolve worker through your AIDTRACE session.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <StatusBadge tone={connected ? "verified" : status ? "danger" : "neutral"}>{status ? (connected ? "worker connected" : "worker not connected") : "checking"}</StatusBadge>
          {runtime && <StatusBadge tone={modelOn ? "verified" : "caution"}>{modelOn ? `model: ${runtime.model_provider_name}` : "no model provider: evidence mode"}</StatusBadge>}
          {runtime?.indexed_points != null && <StatusBadge tone="neutral">{runtime.indexed_points.toLocaleString()} indexed passages · {runtime.collections} domain packs</StatusBadge>}
        </div>
      </div>
      {error && <p role="alert" className="border-l-2 border-danger bg-surface p-3 text-caption text-danger">{error}</p>}
      {status && !connected && (
        <div className="border-l-2 border-caution bg-surface p-4 text-caption">
          <p className="font-medium">The private Resolve worker is not connected, so no investigations can run.</p>
          <p className="mt-1 text-muted">{status.message} {status.setup}</p>
        </div>
      )}
      {connected && (
        <>
          {summary && <p className="text-micro text-muted">{summary.totals.cases} case(s) · {summary.totals.domains_engaged} domain(s) engaged{runtime ? ` · cases stored ${runtime.case_store === "local" ? "locally on the worker (no Supabase configured)" : "in Supabase"}` : ""}</p>}
          <div className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
            <div className="space-y-4">
              <div className="space-y-3 border border-line bg-surface p-4">
                <h3 className="text-body font-semibold">New investigation</h3>
                <label className="block text-caption">Domain pack
                  <select className={input} value={form.domain} onChange={(e) => setForm({ ...form, domain: e.target.value })}>
                    {(status?.domains ?? []).map((d) => <option key={d.id} value={d.id} disabled={!d.active}>{label(d.id)}{d.active ? "" : " (not active)"}</option>)}
                  </select></label>
                <label className="block text-caption">Title<input className={input} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></label>
                <label className="block text-caption">Institution<input className={input} value={form.institution_name} onChange={(e) => setForm({ ...form, institution_name: e.target.value })} /></label>
                <label className="block text-caption">What happened<textarea className={`${input} h-28`} value={form.summary} onChange={(e) => setForm({ ...form, summary: e.target.value })} /></label>
                <Button variant="primary" disabled={busy !== null || form.title.length < 4 || form.institution_name.length < 2 || form.summary.length < 10} onClick={() => void create()}>Create case</Button>
              </div>
              <div className="border border-line bg-surface p-4">
                <h3 className="text-body font-semibold">Cases</h3>
                {cases.length === 0 && <p className="mt-2 text-caption text-muted">No cases yet. Create one above.</p>}
                <ul className="mt-2 space-y-1">{cases.map((c) => (
                  <li key={c.id}><button type="button" aria-current={c.id === selectedId ? "true" : undefined}
                    onClick={() => { setSelectedId(c.id); setMode("cases"); setGraph(null); setReport(null); setTab("evidence"); }}
                    className={`min-h-11 w-full border px-3 py-2 text-left text-caption ${c.id === selectedId ? "border-ink bg-surface-2" : "border-line hover:bg-surface-2"}`}>
                    <strong>{c.title}</strong><span className="block text-micro text-muted">{label(c.domain)} · {c.institution_name} · {c.status}</span></button></li>
                ))}</ul>
              </div>
            </div>

            <div className="min-w-0 space-y-3">
              <FilterTabs tabs={[{ key: "cases", label: "Case workspace" }, { key: "search", label: "Knowledge search" }]} active={mode} onChange={(k) => setMode(k as "cases" | "search")} />
              {mode === "search" && (
                <div className="space-y-3 border border-line bg-surface p-4">
                  <p className="text-caption text-muted">Search the indexed regulations, policy wordings and FAQs for one domain pack. Results are passages from the corpus, ranked by vector similarity.</p>
                  <div className="flex flex-wrap gap-2">
                    <select aria-label="Domain pack" className="min-h-11 border border-line bg-surface px-2 text-caption" value={searchDomain} onChange={(e) => setSearchDomain(e.target.value)}>
                      {(status?.domains ?? []).filter((d) => d.active).map((d) => <option key={d.id} value={d.id}>{label(d.id)}</option>)}</select>
                    <input aria-label="Search query" className="min-h-11 min-w-0 flex-1 border border-line bg-surface px-2 text-caption" value={query} placeholder="e.g. waiting period for pre-existing disease"
                      onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && query.length >= 3) void search(); }} />
                    <Button variant="primary" disabled={busy !== null || query.length < 3} onClick={() => void search()}>Search</Button>
                  </div>
                  {hits && hits.length === 0 && <p className="text-caption text-muted">No passages matched.</p>}
                  <ul className="space-y-2">{hits?.map((h) => (
                    <li key={h.id} className="border border-line p-3 text-caption"><p className="font-medium">{String(h.metadata.title ?? h.metadata.filename ?? h.id)} <span className="font-normal text-muted">· {String(h.metadata.authority ?? "authority unknown")} · score {h.score.toFixed(3)}</span></p>
                      <p className="mt-1 line-clamp-4 text-muted">{h.text}</p></li>
                  ))}</ul>
                </div>
              )}
              {mode === "cases" && !selected && <p className="border border-line bg-surface p-6 text-caption text-muted">Select a case, or create one, to investigate it.</p>}
              {mode === "cases" && selected && (
                <div className="space-y-3">
                  <div className="border border-line bg-surface p-4">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div><h3 className="text-body font-semibold">{selected.title}</h3><p className="text-micro text-muted">{label(selected.domain)} · {selected.institution_name} · {selected.status}</p></div>
                      <div className="flex flex-wrap gap-2">
                        <Button variant="primary" disabled={busy !== null} onClick={() => void investigate()}>{busy === "investigate" ? "Investigating…" : investigation ? "Re-run evidence investigation" : "Run evidence investigation"}</Button>
                        <Button variant="ghost" disabled={busy !== null} onClick={() => void runAgents()}>{busy === "agents" ? "Running agents…" : "Run full agent workflow"}</Button>
                      </div>
                    </div>
                    <p className="mt-2 text-caption text-muted">{selected.summary}</p>
                  </div>
                  <FilterTabs tabs={[{ key: "evidence", label: "Evidence" }, { key: "agents", label: "Agents" }, { key: "graph", label: "Graph & trail" }, { key: "history", label: "History" }, { key: "report", label: "Report" }]}
                    active={tab} onChange={(k) => void openTab(k as CaseTab)} />

                  {tab === "evidence" && (!investigation ? <p className="border border-line bg-surface p-4 text-caption text-muted">Run the evidence investigation to route the case, search the indexed corpus and score what it finds.</p> : (
                    <div className="space-y-3">
                      <div className="flex flex-wrap gap-2 text-micro">
                        {investigation.routing.map((r) => <StatusBadge key={r.domain} tone="info">{label(r.domain)} {r.confidence != null ? `· router ${r.confidence}` : ""}</StatusBadge>)}
                        {investigation.retrieval.map((r) => <StatusBadge key={r.domain} tone="neutral">{r.hits_considered} candidates from {r.indexed_points.toLocaleString()} passages</StatusBadge>)}
                        <StatusBadge tone={investigation.llm_used ? "verified" : "caution"}>{investigation.llm_used ? "model synthesis ran" : "no model text generated"}</StatusBadge>
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        <Button variant="ghost" disabled={busy !== null || investigation.evidence.length === 0} onClick={() => void remember()}>{busy === "remember" ? "Storing…" : "Remember in agent memory"}</Button>
                        {selectedId && remembered[selectedId] && <p role="status" className="text-micro text-muted">{remembered[selectedId]}</p>}
                      </div>
                      {investigation.synthesis.status !== "COMPLETED" && <p className="border-l-2 border-caution bg-surface p-3 text-caption text-muted">{investigation.synthesis.reason}</p>}
                      {investigation.synthesis.status === "COMPLETED" && <div className="border border-line bg-surface p-4 text-caption"><p className="font-semibold">Model synthesis</p><p className="mt-1 whitespace-pre-wrap">{investigation.synthesis.research_summary}</p><p className="mt-2 whitespace-pre-wrap">{investigation.synthesis.strategy}</p></div>}
                      {investigation.evidence.length === 0 && <p className="text-caption text-muted">No indexed material matched this case.</p>}
                      <ol className="space-y-2">{investigation.evidence.map((e, i) => (
                        <li key={`${e.chunk_id}-${i}`} className="border border-line bg-surface p-3 text-caption">
                          <div className="flex flex-wrap items-center justify-between gap-2"><p className="font-medium">{i + 1}. {e.title}</p>
                            <p className="text-micro text-muted"><ConfidenceBar value={e.confidence} /> confidence {e.confidence.toFixed(2)}</p></div>
                          <p className="text-micro text-muted">{e.authority} · {e.section ? label(e.section) : "uncategorised"} · {label(e.domain)}{e.vector_score != null ? ` · vector ${e.vector_score.toFixed(2)} · lexical ${e.lexical_score?.toFixed(2)}` : ""}</p>
                          <p className="mt-2 line-clamp-5 whitespace-pre-wrap leading-relaxed">{e.retrieved_chunk}</p>
                          {e.url && <p className="mt-1 break-all text-micro"><a className="underline" href={e.url} target="_blank" rel="noreferrer noopener">source</a></p>}
                          <details className="mt-1 text-micro text-muted"><summary className="cursor-pointer">Score breakdown</summary>
                            <p className="mt-1 font-mono">{Object.entries(e.evidence_scores).map(([k, v]) => `${k}=${v}`).join("  ")}</p></details>
                        </li>))}</ol>
                      <ul className="list-disc space-y-1 pl-5 text-micro text-muted">{investigation.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
                    </div>))}

                  {tab === "agents" && (!run ? <p className="border border-line bg-surface p-4 text-caption text-muted">The full workflow runs Resolve&apos;s research, evidence, FALKOR DB graph, strategy, negotiation, review and report agents. It needs a model provider to write anything.</p> : (
                    <div className="space-y-3 border border-line bg-surface p-4 text-caption">
                      {offlineRun && <p role="status" className="border-l-2 border-caution bg-surface-2 p-3"><strong>These agents had no model provider, so they produced placeholders, not analysis.</strong> The workflow itself executed ({run.agent_trace?.length ?? 0} recorded steps), but no strategy, review or drafts exist. Use the Evidence tab for the retrieved material.</p>}
                      <p className="text-micro text-muted">Status {run.status} · {run.llm_call_count ?? 0} model call(s) counted</p>
                      {!offlineRun && <>{run.strategy && <p><strong>Strategy.</strong> {run.strategy}</p>}{run.evidence_summary && <p><strong>Evidence.</strong> {run.evidence_summary}</p>}
                        {run.final_report && <pre className="max-h-64 overflow-auto whitespace-pre-wrap border border-line bg-surface-2 p-3 font-mono text-micro">{run.final_report}</pre>}</>}
                      <ol className="flex flex-wrap gap-1 text-micro">{(run.agent_trace ?? []).map((t, i) => <li key={`${t}-${i}`} className="border border-line px-2 py-0.5 font-mono">{String(t)}</li>)}</ol>
                    </div>))}

                  {tab === "graph" && (
                    <div className="space-y-3">
                      {!graph ? <p className="text-caption text-muted">{busy === "graph" ? "Loading…" : "No graph yet."}</p> : <GraphViews graph={toLabGraph(graph)} />}
                      {trail.length > 0 && <ol className="flex flex-wrap gap-1 text-micro" aria-label="Reasoning trail">{trail.map((s) => <li key={s.index} className="border border-line px-2 py-0.5 font-mono">{s.index + 1}. {s.token} <span className="text-muted">→ {s.node_id}</span></li>)}</ol>}
                    </div>)}

                  {tab === "history" && (
                    <div className="grid gap-3 border border-line bg-surface p-4 text-caption md:grid-cols-2">
                      <div><h4 className="font-semibold">Agent runs</h4>{(report?.agent_runs ?? []).length === 0 ? <p className="mt-1 text-muted">None yet.</p> :
                        <ul className="mt-1 space-y-1">{report!.agent_runs.map((r) => <li key={r.id} className="border-b border-line pb-1">{r.workflow_name} <span className="text-muted">· {r.status}</span></li>)}</ul>}</div>
                      <div><h4 className="font-semibold">Timeline</h4>{(report?.events ?? []).length === 0 ? <p className="mt-1 text-muted">No events.</p> :
                        <ul className="mt-1 space-y-1">{report!.events.map((e, i) => <li key={e.id ?? i} className="border-b border-line pb-1">{e.title ?? e.event_type} <span className="text-muted">· {e.actor} · {e.created_at?.slice(0, 19).replace("T", " ")}</span></li>)}</ul>}</div>
                    </div>)}

                  {tab === "report" && (
                    <div className="space-y-3 border border-line bg-surface p-4">
                      <div className="flex flex-wrap items-center justify-between gap-2"><p className="text-caption text-muted">Built only from what ran in this session and the worker&apos;s stored runs. Anything that did not run is stated as not run.</p>
                        <Button variant="primary" onClick={download}>Download Markdown</Button></div>
                      <pre className="max-h-96 overflow-auto whitespace-pre-wrap border border-line bg-surface-2 p-3 font-mono text-micro">{buildCaseReport(selected, investigation, run)}</pre>
                    </div>)}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </section>
  );
}
