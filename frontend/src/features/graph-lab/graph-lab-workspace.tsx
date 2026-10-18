"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { GraphViews } from "@/components/graph-views";
import { Button, ButtonLink, PageHeader, StatusBadge } from "@/components/ui";
import { runDriftDemo } from "@/lib/api";
import type { LabGraph } from "@/lib/graph-layout";
import {
  analyzeLab, getLabAlgorithms, getLabScenario, getLabScenarios, getSiteGraph,
  type LabAlgorithm, type LabAnalysis, type LabParam, type LabPreset, type LabSource,
} from "@/lib/lab-api";
import { useFetch } from "@/lib/use-fetch";

type SourceKind = "scenario" | "site" | "paste";
const VERDICT_TONE: Record<string, "verified" | "danger" | "caution" | "info"> = {
  PROCEED: "verified", SUPPORTED: "verified", HOLD: "danger", REFUTED: "danger",
  REVIEW: "caution", CONTESTED: "caution", INSUFFICIENT_EVIDENCE: "caution", UNVERIFIED: "caution",
};
const SAMPLE = JSON.stringify({
  nodes: [{ id: "root-cause", label: "Root cause" }, { id: "svc-a" }, { id: "svc-b" }],
  edges: [{ source: "svc-a", target: "root-cause", rel: "DEPENDS_ON" }, { source: "svc-b", target: "svc-a", rel: "DEPENDS_ON", certainty: "maybe" }],
}, null, 2);
const DEFAULT_LEDE = "Ten graph-reasoning engines distilled from the 98 research repositories. Pick a scenario, your site's evidence graph or your own JSON, run an engine, and read the same result as a network, layers, rings, a matrix, a timeline or a table.";

const words = (key: string) => key.replace(/_/g, " ");
function cellText(value: unknown): string {
  if (Array.isArray(value)) return value.map((v) => (typeof v === "object" ? JSON.stringify(v) : String(v))).join(" → ");
  if (value && typeof value === "object") return JSON.stringify(value);
  if (typeof value === "boolean") return value ? "yes" : "no";
  return value === null || value === undefined ? "—" : String(value);
}
function defaults(algo: LabAlgorithm | undefined): Record<string, unknown> {
  return Object.fromEntries((algo?.params ?? []).map((p) => [p.name, p.kind === "nodes" || p.kind === "tags" ? [] : p.default ?? ""]));
}
/** Drop empty values so optional parameters fall back to the engine's own defaults. */
function clean(params: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(params).filter(([, v]) => v !== "" && v !== null && !(Array.isArray(v) && v.length === 0)));
}

interface Props { initialScenario?: string; initialAlgo?: string; title?: string; lede?: string; embedded?: boolean }

export function GraphLabWorkspace({ initialScenario = "plant_evidence", initialAlgo = "blast_radius", title = "Graph Lab", lede = DEFAULT_LEDE, embedded = false }: Props) {
  const algorithms = useFetch(getLabAlgorithms);
  const scenarios = useFetch(getLabScenarios);
  const [kind, setKind] = useState<SourceKind>("scenario");
  const [scenarioId, setScenarioId] = useState(initialScenario);
  const [graph, setGraph] = useState<LabGraph | null>(null);
  const [presets, setPresets] = useState<LabPreset[]>([]);
  const [algoId, setAlgoId] = useState(initialAlgo);
  const [overrides, setOverrides] = useState<Record<string, Record<string, unknown>>>({});
  const [pasteText, setPasteText] = useState(SAMPLE);
  const [analysis, setAnalysis] = useState<LabAnalysis | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [runVersion, setRunVersion] = useState(0);
  const siteRequest = useRef(0);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const algoList = algorithms.status === "live" ? algorithms.data.algorithms : [];
  const algo = algoList.find((a) => a.id === algoId);
  const nodes = graph?.nodes ?? [];
  // Parameters are derived (engine defaults + the user's edits for this engine), never synced by an effect.
  const params = overrides[algoId] ?? defaults(algo);
  const setParam = (name: string, value: unknown) => setOverrides((o) => ({ ...o, [algoId]: { ...(o[algoId] ?? defaults(algo)), [name]: value } }));
  const resetView = () => { setError(null); setNotice(null); setAnalysis(null); setSelected(null); };

  async function loadSite() {
    const request = ++siteRequest.current;
    resetView(); setPresets([]); setGraph(null);
    try {
      const { data } = await getSiteGraph();
      if (request !== siteRequest.current) return;
      setGraph(data.graph);
      setNotice(data.empty ? "The site evidence graph is empty. Seed the synthetic evidence case to give it something to analyse." : data.truncated ? "Showing a bounded part of a larger graph." : null);
    } catch (e) { if (request === siteRequest.current) setError(e instanceof Error ? e.message : "The site graph could not be loaded."); }
  }

  useEffect(() => {
    if (kind !== "scenario") return;
    let current = true;
    getLabScenario(scenarioId)
      .then(({ data }) => { if (current) { setGraph(data.graph); setPresets(data.recommended); } })
      .catch((e: unknown) => { if (current) setError(e instanceof Error ? e.message : "The scenario could not be loaded."); });
    return () => { current = false; };
  }, [kind, scenarioId]);

  const source = useMemo((): LabSource | null => {
    if (kind === "scenario") return { scenario: scenarioId };
    if (kind === "site") return { site_graph: true };
    try { return { graph: JSON.parse(pasteText) as LabGraph }; } catch { return null; }
  }, [kind, scenarioId, pasteText]);

  // A serialized request changes only when inputs change, not when result state renders.
  // Do not call the server (and show its 422) while a required node is still unchosen: wait and say what is needed.
  const missing = (algo?.params ?? []).filter((p) => p.required && (params[p.name] === undefined || params[p.name] === "" || (Array.isArray(params[p.name]) && (params[p.name] as unknown[]).length === 0)));
  const requestJson = algo && source && missing.length === 0 ? JSON.stringify({ algorithm: algoId, source, params: clean(params) }) : null;
  useEffect(() => {
    let current = true;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setAnalysis(null);
      if (!requestJson) {
        setBusy(false);
        if (kind === "paste" && !source) setError("The pasted graph is not valid JSON.");
        return;
      }
      setBusy(true); setError(null);
      const request = JSON.parse(requestJson) as { algorithm: string; source: LabSource; params: Record<string, unknown> };
      try {
        const out = await analyzeLab(request.algorithm, request.source, request.params, controller.signal);
        if (current) { setAnalysis(out); setGraph(out.graph); }
      } catch (e) {
        if (current) setError(e instanceof Error ? e.message : "The analysis failed.");
      } finally {
        if (current) setBusy(false);
      }
    }, 400);
    return () => { current = false; clearTimeout(timer); controller.abort(); };
  }, [requestJson, runVersion, kind, source]);

  useEffect(() => () => { siteRequest.current += 1; }, []);

  useEffect(() => {
    if (kind !== "site") return;
    const refresh = () => { if (!document.hidden && navigator.onLine) setRunVersion((v) => v + 1); };
    const timer = setInterval(refresh, 30000);
    window.addEventListener("focus", refresh);
    window.addEventListener("online", refresh);
    return () => { clearInterval(timer); window.removeEventListener("focus", refresh); window.removeEventListener("online", refresh); };
  }, [kind]);

  function applyPreset(preset: LabPreset) {
    setAlgoId(preset.algorithm); setOverrides((o) => ({ ...o, [preset.algorithm]: preset.params }));
    setRunVersion((v) => v + 1);
  }
  async function seedEvidence() {
    setBusy(true); setError(null);
    try { await runDriftDemo(); await loadSite(); setRunVersion((v) => v + 1); } catch (e) { setError(e instanceof Error ? e.message : "The evidence case could not be seeded."); }
    finally { setBusy(false); }
  }
  function download() {
    if (!analysis) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(analysis, null, 2)], { type: "application/json" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: `graph-lab-${analysis.algorithm}.json` });
    a.click(); URL.revokeObjectURL(url);
  }

  const nodeParams = (algo?.params ?? []).filter((p) => p.kind === "node" || p.kind === "nodes");
  const verdict = analysis && typeof analysis.result.summary.verdict === "string" ? analysis.result.summary.verdict : null;
  const rows = analysis?.result.findings ?? [];
  const columns = rows.length ? Object.keys(rows[0]).slice(0, 6) : [];

  return (
    <div className="mx-auto max-w-[1400px]">
      {embedded
        ? <div><h2 className="text-title font-semibold">{title}</h2><p className="mt-1 max-w-3xl text-caption leading-relaxed text-muted">{lede}</p></div>
        : <PageHeader title={title} lede={lede} actions={<ButtonLink href="/sources">Source Library</ButtonLink>} />}
      <div className="mt-6 grid gap-5 lg:grid-cols-[340px_minmax(0,1fr)]">
        <aside className="space-y-4" aria-label="Analysis controls">
          <section className="border border-line bg-surface p-4">
            <h3 className="text-body font-semibold">1 · Graph</h3>
            <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="Graph source">
              {([["scenario", "Scenario"], ["site", "Site evidence"], ["paste", "Paste JSON"]] as const).map(([k, label]) => (
                <Button key={k} aria-pressed={kind === k} variant={kind === k ? "primary" : "ghost"} onClick={() => { siteRequest.current += 1; setKind(k); setRunVersion((v) => v + 1); resetView(); if (k === "site") void loadSite(); if (k === "paste") { setGraph(null); setPresets([]); } }}>{label}</Button>
              ))}
            </div>
            {kind === "scenario" && (
              <label className="mt-3 block text-caption">Scenario
                <select className="mt-1 min-h-11 w-full border border-line bg-surface px-2" value={scenarioId} onChange={(e) => { setScenarioId(e.target.value); setGraph(null); resetView(); }}>
                  {(scenarios.status === "live" ? scenarios.data.scenarios : [{ id: scenarioId, title: scenarioId, description: "", nodes: 0, edges: 0, recommended: [] }]).map((s) => <option key={s.id} value={s.id}>{s.title}</option>)}
                </select>
                <span className="mt-1 block text-micro text-muted">{scenarios.status === "live" ? scenarios.data.scenarios.find((s) => s.id === scenarioId)?.description : ""}</span>
              </label>
            )}
            {kind === "site" && (
              <div className="mt-3 text-caption text-muted">
                <p>Your site&apos;s persisted evidence graph from FalkorDB (read-only).</p>
                <Button className="mt-2" disabled={busy} onClick={() => void seedEvidence()}>Seed synthetic evidence case</Button>
              </div>
            )}
            {kind === "paste" && (
              <label className="mt-3 block text-caption">Graph JSON (nodes, edges)
                <textarea className="mt-1 h-44 w-full border border-line bg-surface p-2 font-mono text-micro" value={pasteText} spellCheck={false} onChange={(e) => setPasteText(e.target.value)} />
                <span className="text-micro text-muted">Edges read “source depends on / flows to target”. Up to 2,000 nodes and 10,000 edges.</span>
              </label>
            )}
          </section>

          <section className="border border-line bg-surface p-4">
            <h3 className="text-body font-semibold">2 · Engine</h3>
            <label className="mt-3 block text-caption">Engine
              <select className="mt-1 min-h-11 w-full border border-line bg-surface px-2" value={algoId} onChange={(e) => { setAlgoId(e.target.value); setAnalysis(null); }}>
                {algoList.map((a) => <option key={a.id} value={a.id}>{a.title}</option>)}
              </select>
            </label>
            {algo && <p className="mt-2 text-micro leading-relaxed text-muted">{algo.summary}</p>}
            <div className="mt-3 space-y-3">{algo?.params.map((p) => <ParamField key={p.name} param={p} value={params[p.name]} nodes={nodes} onChange={(v) => setParam(p.name, v)} />)}</div>
            <p className="mt-3 text-micro text-muted" role="status">{missing.length > 0 ? `Choose ${missing.map((p) => p.label.toLowerCase()).join(" and ")} to run this engine (click nodes in the graph or use the lists).` : "Results recalculate automatically when you change the graph, engine or parameters."}</p>
            <Button className="mt-4 w-full" variant="primary" disabled={busy || (kind !== "paste" && !graph)} onClick={() => setRunVersion((v) => v + 1)}>{busy ? "Running…" : "Run engine"}</Button>
          </section>

          {presets.length > 0 && (
            <section className="border border-line bg-surface p-4">
              <h3 className="text-body font-semibold">Try this</h3>
              <ul className="mt-3 space-y-2">{presets.map((p, i) => <li key={i}><Button className="w-full justify-start" variant="ghost" disabled={busy} onClick={() => applyPreset(p)}>{algoList.find((a) => a.id === p.algorithm)?.title ?? p.algorithm}{typeof p.params.decision === "string" ? ` · ${p.params.decision}` : ""}</Button></li>)}</ul>
            </section>
          )}
        </aside>

        <div className="min-w-0 space-y-4">
          {[algorithms, scenarios].map((state, index) => state.status === "error" && <p key={index} role="alert">{state.error.message} <Button onClick={state.retry}>Retry</Button></p>)}
          {error && <p role="alert" className="border-l-2 border-danger bg-surface p-3 text-caption text-danger">{error}</p>}
          {notice && <p role="status" className="border-l-2 border-caution bg-surface p-3 text-caption text-muted">{notice}</p>}
          {graph && graph.nodes.length > 0
            ? <GraphViews graph={graph} marks={analysis?.result} selected={selected} onSelect={setSelected} />
            : <div className="border border-dashed border-line p-10 text-center text-caption text-muted">{kind === "paste" ? "Run the engine to render your graph." : "Choose a graph to begin."}</div>}

          {selected && nodeParams.length > 0 && (
            <div className="flex flex-wrap items-center gap-2 border border-line bg-surface p-3 text-caption" aria-label="Assign selected node">
              <span className="text-muted">Use <strong className="text-ink">{selected}</strong> as</span>
              {nodeParams.map((p) => (
                <Button key={p.name} variant="ghost" onClick={() => setParam(p.name, p.kind === "nodes" ? [...new Set([...((params[p.name] as string[] | undefined) ?? []), selected])] : selected)}>{p.label}</Button>
              ))}
            </div>
          )}

          {analysis && (
            <section className="border border-line bg-surface p-5" aria-labelledby={`result-heading-${algoId}`}>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h3 id={`result-heading-${algoId}`} className="text-title font-semibold">{algoList.find((a) => a.id === analysis.algorithm)?.title ?? analysis.algorithm}</h3>
                <div className="flex flex-wrap items-center gap-2">
                  {verdict && <StatusBadge tone={VERDICT_TONE[verdict] ?? "info"}>{verdict.replace(/_/g, " ")}</StatusBadge>}
                  <span className="text-micro text-muted">{analysis.graph_source} · {analysis.elapsed_ms} ms</span>
                  <Button variant="ghost" onClick={download}>Download JSON</Button>
                </div>
              </div>
              <dl className="mt-4 grid gap-x-8 gap-y-2 text-caption sm:grid-cols-2 xl:grid-cols-3">
                {Object.entries(analysis.result.summary).map(([k, v]) => <div key={k} className="flex justify-between gap-3 border-b border-line pb-1"><dt className="capitalize text-muted">{words(k)}</dt><dd className="break-all font-medium">{cellText(v)}</dd></div>)}
              </dl>
              {rows.length > 0 && (
                <div className="mt-4 max-h-80 overflow-auto border border-line">
                  <table className="w-full text-left text-caption">
                    <thead className="sticky top-0 bg-surface-2 text-muted"><tr>{columns.map((c) => <th key={c} scope="col" className="p-2 font-semibold capitalize">{words(c)}</th>)}</tr></thead>
                    <tbody>{rows.slice(0, 60).map((row, i) => {
                      const id = [row.node, row.asset, row.evidence].find((v) => typeof v === "string" && nodes.some((n) => n.id === v)) as string | undefined;
                      return <tr key={i} className={`border-t border-line ${id ? "cursor-pointer hover:bg-surface-2" : ""}`} onClick={() => id && setSelected(id)}>{columns.map((c) => <td key={c} className="p-2 align-top">{cellText(row[c])}</td>)}</tr>;
                    })}</tbody>
                  </table>
                </div>
              )}
              {analysis.result.notes.map((n) => <p key={n} className="mt-3 border-l-2 border-line pl-3 text-micro leading-relaxed text-muted">{n}</p>)}
              <details className="mt-4 text-caption">
                <summary className="cursor-pointer font-medium">Provenance & capability status</summary>
                <p className="mt-2 text-muted">{analysis.provenance.implementation} Status: <strong>{analysis.provenance.status}</strong>. Tests: <span className="font-mono text-micro">{analysis.provenance.tests}</span></p>
                <p className="mt-2 text-muted">READMEs that describe this mechanism (hypotheses, not verified features):</p>
                <ul className="mt-1 flex flex-wrap gap-2">{analysis.provenance.readme_derived_hypothesis_from.map((s) => <li key={s.repo}><Link className="underline" href={`/sources?q=${encodeURIComponent(s.repo.split("/")[1])}`}>{s.repo}</Link></li>)}</ul>
              </details>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}

function ParamField({ param, value, nodes, onChange }: { param: LabParam; value: unknown; nodes: { id: string; label: string }[]; onChange: (v: unknown) => void }) {
  const id = `param-${param.name}`;
  const base = "mt-1 w-full border border-line bg-surface px-2";
  const label = <>{param.label}{param.required && <span className="text-danger"> *</span>}</>;
  if (param.kind === "nodes") {
    const chosen = Array.isArray(value) ? (value as string[]) : [];
    return (
      <label className="block text-caption" htmlFor={id}>{label}
        <select id={id} multiple size={Math.min(6, Math.max(3, nodes.length))} className={base} value={chosen} onChange={(e) => onChange([...e.target.selectedOptions].map((o) => o.value))}>
          {nodes.map((n) => <option key={n.id} value={n.id}>{n.label}</option>)}
        </select>
        <span className="text-micro text-muted">{chosen.length ? `${chosen.length} selected` : "Hold Ctrl/Cmd to pick several, or click nodes in the graph."}</span>
      </label>
    );
  }
  if (param.kind === "node") {
    return (
      <label className="block text-caption" htmlFor={id}>{label}
        <select id={id} className={`${base} min-h-11`} value={String(value ?? "")} onChange={(e) => onChange(e.target.value)}>
          <option value="">Choose…</option>
          {nodes.map((n) => <option key={n.id} value={n.id}>{n.label}</option>)}
        </select>
      </label>
    );
  }
  if (param.kind === "select") {
    return (
      <label className="block text-caption" htmlFor={id}>{label}
        <select id={id} className={`${base} min-h-11`} value={String(value ?? param.default ?? "")} onChange={(e) => onChange(e.target.value)}>
          {param.options.map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      </label>
    );
  }
  if (param.kind === "tags") {
    return (
      <label className="block text-caption" htmlFor={id}>{label}
        <input id={id} className={`${base} min-h-11`} placeholder="comma-separated, e.g. claim, inspection" value={Array.isArray(value) ? (value as string[]).join(", ") : ""}
          onChange={(e) => onChange(e.target.value.split(",").map((s) => s.trim()).filter(Boolean))} />
      </label>
    );
  }
  if (param.kind === "int" || param.kind === "number") {
    return (
      <label className="block text-caption" htmlFor={id}>{label}
        <input id={id} type="number" step={param.kind === "int" ? 1 : 0.05} className={`${base} min-h-11`} value={String(value ?? "")}
          onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))} />
      </label>
    );
  }
  return (
    <label className="block text-caption" htmlFor={id}>{label}
      <input id={id} type="datetime-local" className={`${base} min-h-11`} value={typeof value === "string" ? value.slice(0, 16) : ""}
        onChange={(e) => onChange(e.target.value ? `${e.target.value}:00Z` : "")} />
    </label>
  );
}
