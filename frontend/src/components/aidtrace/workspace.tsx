"use client";

// AIDTRACE workspace: one page, three panels. Left = investigation and agent control, centre = Globe / Graph / Lineage / Workflow / Agent Memory,
// right = contextual inspector. Every other capability opens as an in-page extension in the centre; the address bar never changes.
import { useCallback, useEffect, useState } from "react";
import { Boundary, FEATURES } from "@/features/feature-host";
import { Button, StatusBadge } from "@/components/ui";
import { isUnsafe } from "@/lib/aidtrace-lineage";
import { askAgent, SUGGESTED_QUESTIONS, useAidtraceData, type AgentAnswer, type AidtraceData, type Selection, type ViewId } from "./data";
import { Inspector, type InspectorTab } from "./inspector";
import { GlobeView, GraphView, LineageView, MemoryView, WorkflowView } from "./views";

const VIEWS: { id: ViewId; label: string }[] = [
  { id: "globe", label: "Globe" }, { id: "graph", label: "Graph" }, { id: "lineage", label: "Lineage" }, { id: "workflow", label: "Workflow" }, { id: "memory", label: "Agent Memory" },
];
const KEY_VIEW = "aidtrace.hub.view";
const KEY_EXT = "aidtrace.hub.extension";
const EXTENSIONS = FEATURES.filter((f) => f.id !== "overview");

function stored(key: string): string | null { try { return window.sessionStorage.getItem(key); } catch { return null; } }
function store(key: string, value: string | null) { try { if (value === null) window.sessionStorage.removeItem(key); else window.sessionStorage.setItem(key, value); } catch { /* storage blocked */ } }

function LeftPanel({ data, selection, onSelect, onView, onTab, extension, onExtension }: {
  data: AidtraceData; selection: Selection; onSelect: (s: Selection) => void; onView: (v: ViewId) => void; onTab: (t: InspectorTab) => void; extension: string | null; onExtension: (id: string | null) => void;
}) {
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<AgentAnswer[]>([]);
  const { demo, health, snap, lineage, errors } = data;
  const stale = (snap?.decisions ?? []).filter((d) => isUnsafe(d.status)).length;

  async function ask(text: string) {
    const q = text.trim();
    if (!q || busy) return;
    setBusy(true); setQuestion("");
    const answer = await askAgent(q, { demo: data.demo, scenario: data.scenario, snap: data.snap, selected: selection });
    setHistory((h) => [answer, ...h].slice(0, 12));
    setBusy(false);
  }
  function show(a: AgentAnswer) {
    if (!a.select) return;
    onSelect(a.select);
    if (a.select.kind === "memory") { onView("memory"); onTab("Memory"); } else if (a.select.kind === "node") { onView("graph"); onTab("Cyber Risk"); } else { onView("globe"); onTab("Overview"); }
  }

  const steps: [string, boolean | null][] = [
    ["Supplier data", errors.supply ? false : demo ? true : null], ["Agent memory", errors.memory ? false : snap ? snap.memories.length > 0 : null],
    ["Evidence lineage", lineage ? lineage.nodes.length > 0 : null], ["Decisions current", snap ? snap.decisions.length > 0 && stale === 0 : null],
  ];
  return (
    <div className="flex size-full min-h-0 flex-col overflow-y-auto">
      <header className="border-b border-line px-4 py-3 pr-10">
        <h1 className="text-body font-semibold tracking-wide text-ink">AIDTRACE</h1>
        <p className="mt-0.5 text-micro text-muted">Connected supply chain &amp; cyber risk intelligence</p>
      </header>
      <section aria-label="Active investigation" className="border-b border-line px-4 py-3">
        <p className="text-micro font-medium uppercase tracking-wider text-muted">Investigation</p>
        <p className="mt-1 text-caption text-ink">{demo ? `${demo.product} → ${demo.destination}` : errors.supply ? "GreenChain unavailable" : "Loading…"}</p>
        <p className="mt-0.5 text-micro text-muted">Illustrative suppliers; synthetic incidents.</p>
      </section>
      <section aria-label="Ask the agent" className="border-b border-line px-4 py-3">
        <form onSubmit={(e) => { e.preventDefault(); void ask(question); }}>
          <label htmlFor="aidtrace-ask" className="text-micro font-medium uppercase tracking-wider text-muted">Ask the agent</label>
          <div className="mt-1 flex gap-1.5">
            <input id="aidtrace-ask" value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Ask about suppliers, risk or decisions" autoComplete="off"
              className="h-10 min-w-0 flex-1 border border-line bg-canvas px-3 text-caption text-ink placeholder:text-muted focus-visible:outline-2 focus-visible:outline-accent" />
            <Button type="submit" variant="primary" disabled={busy || !question.trim()} aria-label="Send question">{busy ? "…" : "Ask"}</Button>
          </div>
        </form>
        <ul className="mt-2 space-y-1">{SUGGESTED_QUESTIONS.map((q) => <li key={q}><button type="button" disabled={busy} onClick={() => void ask(q)} className="w-full border border-line bg-surface px-2 py-1.5 text-left text-micro leading-snug text-ink hover:bg-surface-2 disabled:opacity-60">{q}</button></li>)}</ul>
        <p className="mt-1.5 text-micro text-muted">Answers come from the graph engines, not a language model.</p>
        {history.length > 0 && <ol className="mt-3 space-y-2" aria-label="Investigation history">{history.map((a) => (
          <li key={a.at + a.question} className={`border-l-2 bg-surface p-2.5 text-caption ${a.ok ? "border-accent" : "border-line"}`}>
            <p className="text-micro text-muted">{a.question}</p>
            <p className="mt-1 text-ink">{a.text}</p>
            {a.lines.length > 0 && <ul className="mt-1 max-h-40 space-y-0.5 overflow-y-auto text-micro text-muted">{a.lines.map((l, i) => <li key={i}>{l}</li>)}</ul>}
            <p className="mt-1 text-micro text-muted">{a.route} · {a.at.slice(11, 19)} UTC</p>
            {a.select && <Button className="mt-1" variant="ghost" onClick={() => show(a)}>Show in workspace</Button>}
          </li>))}</ol>}
      </section>
      <section aria-label="Evidence source" className="border-b border-line px-4 py-3">
        <label htmlFor="aidtrace-source" className="text-micro font-medium uppercase tracking-wider text-muted">Evidence source</label>
        <select id="aidtrace-source" value={selection?.kind === "source" ? selection.id : ""} disabled={!snap?.sources.length}
          onChange={(e) => { const s = snap?.sources.find((x) => x.id === e.target.value); if (s) { onSelect({ kind: "source", id: s.id, label: s.title || s.id }); onView("lineage"); onTab("Lineage"); } }}
          className="mt-1 h-10 w-full border border-line bg-canvas px-2 text-caption">
          <option value="">{snap?.sources.length ? "Choose a source to trace…" : "No sources recorded yet"}</option>
          {snap?.sources.map((s) => <option key={s.id} value={s.id}>{s.title || s.id}</option>)}
        </select>
      </section>
      <section aria-label="Status" className="border-b border-line px-4 py-3">
        <p className="text-micro font-medium uppercase tracking-wider text-muted">Status</p>
        <ul className="mt-1 space-y-0.5 text-caption">{steps.map(([label, ok]) => <li key={label} className="flex items-center justify-between"><span>{label}</span><span className={`text-micro ${ok === null ? "text-muted" : ok ? "text-ink" : "text-danger"}`}>{ok === null ? "checking" : ok ? "ok" : "needs attention"}</span></li>)}</ul>
        {(errors.supply || errors.memory || stale > 0 || (health && health.live_discovery !== "ENABLED")) && (
          <ul className="mt-2 space-y-1 text-micro" aria-label="Warnings">
            {errors.supply && <li role="alert" className="text-danger">GreenChain: {errors.supply}</li>}
            {errors.memory && <li role="alert" className="text-danger">Agent memory: {errors.memory}</li>}
            {stale > 0 && <li className="text-danger">{stale} decision(s) rest on stale evidence.</li>}
            {health && health.live_discovery !== "ENABLED" && <li className="text-muted">Live supplier discovery is off; candidates are illustrative.</li>}
          </ul>
        )}
      </section>
      <details className="px-4 py-3" open={extension !== null}>
        <summary className="cursor-pointer text-micro font-medium uppercase tracking-wider text-muted">Extensions</summary>
        <ul className="mt-2 space-y-1">{EXTENSIONS.map((f) => (
          <li key={f.id}><button type="button" aria-current={extension === f.id ? "true" : undefined} onClick={() => onExtension(extension === f.id ? null : f.id)}
            className={`flex w-full items-center justify-between border px-2 py-1.5 text-left text-caption ${extension === f.id ? "border-ink bg-surface-2 font-semibold" : "border-line bg-surface hover:bg-surface-2"}`}>
            {f.name}{f.status === "PARTIAL" && <span className="text-micro font-normal text-muted">partial</span>}</button></li>))}</ul>
      </details>
    </div>
  );
}

export function AidtraceWorkspace() {
  const data = useAidtraceData();
  const [view, setView] = useState<ViewId>("globe");
  const [extension, setExtension] = useState<string | null>(null);
  const [selection, setSelection] = useState<Selection>(null);
  const [tab, setTab] = useState<InspectorTab>("Overview");
  const [leftOpen, setLeftOpen] = useState(true);
  const [rightOpen, setRightOpen] = useState(true);

  useEffect(() => {
    const t = window.setTimeout(() => {
      const v = stored(KEY_VIEW); if (VIEWS.some((x) => x.id === v)) setView(v as ViewId);
      const e = stored(KEY_EXT); if (e && EXTENSIONS.some((x) => x.id === e)) setExtension(e);
    }, 0);
    return () => window.clearTimeout(t);
  }, []);

  const changeView = useCallback((v: ViewId) => { setView(v); setExtension(null); store(KEY_VIEW, v); store(KEY_EXT, null); }, []);
  const openExtension = useCallback((id: string | null) => { setExtension(id); store(KEY_EXT, id); }, []);
  const select = useCallback((s: Selection) => {
    setSelection(s);
    if (!s) return;
    setRightOpen(true);
    setTab(s.kind === "supplier" || s.kind === "node" ? "Overview" : s.kind === "memory" ? "Memory" : s.kind === "decision" || s.kind === "action" ? "Decisions" : "Lineage");
  }, []);

  const ext = EXTENSIONS.find((f) => f.id === extension) ?? null;
  const common = { data, selection, onSelect: select };
  const cols = `${leftOpen ? "clamp(260px,22%,340px)" : "40px"} minmax(0,1fr) ${rightOpen ? "clamp(280px,24%,360px)" : "40px"}`;

  function onKey(e: React.KeyboardEvent) {
    const i = VIEWS.findIndex((v) => v.id === view);
    if (e.key === "ArrowRight") changeView(VIEWS[(i + 1) % VIEWS.length].id);
    else if (e.key === "ArrowLeft") changeView(VIEWS[(i + VIEWS.length - 1) % VIEWS.length].id);
    else return;
    e.preventDefault();
  }

  return (
    <div data-testid="aidtrace-workspace" className="grid min-h-dvh grid-cols-1 lg:h-dvh lg:[grid-template-columns:var(--cols)]" style={{ "--cols": cols } as React.CSSProperties}>
      <aside aria-label="Investigation and agent control" className="order-2 min-h-0 border-b border-line bg-surface lg:order-1 lg:border-b-0 lg:border-r">
        {leftOpen ? (
          <div className="relative size-full">
            <button type="button" aria-label="Collapse investigation panel" onClick={() => setLeftOpen(false)} className="absolute right-2 top-3 z-10 hidden size-7 place-items-center text-muted hover:text-ink lg:grid">‹</button>
            <LeftPanel data={data} selection={selection} onSelect={select} onView={changeView} onTab={setTab} extension={extension} onExtension={openExtension} />
          </div>
        ) : <button type="button" aria-label="Expand investigation panel" onClick={() => setLeftOpen(true)} className="hidden size-full place-items-start justify-center pt-3 text-muted hover:text-ink lg:grid">›</button>}
      </aside>

      <section aria-label="Intelligence workspace" className="order-1 flex min-h-[70dvh] min-w-0 flex-col lg:order-2 lg:min-h-0">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-3 py-2">
          <div role="tablist" aria-label="Workspace view" onKeyDown={onKey} className="flex gap-1 overflow-x-auto">
            {VIEWS.map((v) => (
              <button key={v.id} role="tab" type="button" aria-selected={!ext && view === v.id} tabIndex={!ext && view === v.id ? 0 : -1} onClick={() => changeView(v.id)}
                className={`shrink-0 border px-3 py-1.5 text-caption ${!ext && view === v.id ? "border-ink bg-ink text-canvas" : "border-line bg-surface text-ink hover:bg-surface-2"}`}>{v.label}</button>
            ))}
          </div>
          <div className="flex items-center gap-2 text-micro text-muted">
            {data.loading && <span role="status">Loading…</span>}
            {ext && <Button variant="ghost" onClick={() => openExtension(null)}>← Back to workspace</Button>}
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-hidden" role="tabpanel" aria-label={ext ? ext.name : VIEWS.find((v) => v.id === view)?.label}>
          {ext ? (
            <div className="size-full overflow-y-auto p-4">
              <div className="mb-3 flex flex-wrap items-center gap-2"><h2 className="text-title font-semibold">{ext.name}</h2><StatusBadge tone={ext.status === "PARTIAL" ? "caution" : "verified"}>{ext.status === "PARTIAL" ? "partial" : "extension"}</StatusBadge></div>
              <p className="mb-3 max-w-3xl text-caption leading-relaxed text-muted">{ext.summary}</p>
              <Boundary key={ext.id} label={ext.name}>{ext.render(openExtension)}</Boundary>
            </div>
          ) : (
            <Boundary key={view} label={VIEWS.find((v) => v.id === view)?.label ?? "View"}>
              {view === "globe" && <GlobeView {...common} />}
              {view === "graph" && <GraphView {...common} />}
              {view === "lineage" && <LineageView {...common} />}
              {view === "workflow" && <WorkflowView {...common} onOpenView={changeView} />}
              {view === "memory" && <MemoryView {...common} />}
            </Boundary>
          )}
        </div>
      </section>

      <aside aria-label="Contextual inspector" className="order-3 min-h-0 border-t border-line bg-surface lg:border-l lg:border-t-0">
        {rightOpen ? (
          <div className="relative size-full">
            <button type="button" aria-label="Collapse inspector" onClick={() => setRightOpen(false)} className="absolute right-1 top-2 z-10 hidden size-7 place-items-center bg-surface text-muted hover:text-ink lg:grid">›</button>
            <Inspector data={data} selection={selection} onSelect={select} tab={tab} onTab={setTab} />
          </div>
        ) : <button type="button" aria-label="Expand inspector" onClick={() => setRightOpen(true)} className="hidden size-full place-items-start justify-center pt-3 text-muted hover:text-ink lg:grid">‹</button>}
      </aside>
    </div>
  );
}
