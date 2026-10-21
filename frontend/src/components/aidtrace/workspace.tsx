"use client";

// AIDTRACE workspace: one page, three panels. Left = Investigate (one input, three actions), centre = Globe / Graph / Lineage / Timeline, right = Risk /
// Evidence / Decision inspector. The Globe is always the first thing shown. Secondary tools open in the centre and never leave the page.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Boundary } from "@/features/feature-host";
import { useRole } from "@/components/use-role";
import { Button, StatusBadge } from "@/components/ui";
import { isUnsafe } from "@/lib/aidtrace-lineage";
import { investigateRisk, latestScenarioId, updateEvidence, type EvidenceResult, type InvestigationResult, type Stage } from "./automation";
import { askAgent, useAidtraceData, type AgentAnswer, type AidtraceData, type Selection, type ViewId } from "./data";
import { Inspector, type Section } from "./inspector";
import { GlobeView, GraphView, LineageView, TimelineView, type RunLogEntry } from "./views";
import { AidtraceProvider, type AidtraceContextValue } from "./extensions/context";
import { ExtensionLauncher } from "./extensions/launcher";
import { ExtensionPanel } from "./extensions/panel";
import { extensionById, isAvailable } from "./extensions/registry";

const VIEWS: { id: ViewId; label: string }[] = [{ id: "globe", label: "Globe" }, { id: "graph", label: "Graph" }, { id: "lineage", label: "Lineage" }, { id: "timeline", label: "Timeline" }];
const EXAMPLES = ["Which suppliers are exposed?", "What changed since the last review?", "Which decision needs attention?"];
const plain = (name: string) => name.replace("Illustrative ", "");
const dot: Record<Stage["status"], string> = { pending: "bg-line", running: "bg-accent animate-pulse", done: "bg-ink", skipped: "bg-muted", failed: "bg-danger" };

/** The supplier the graph currently recommends, read from the newest decision that is still valid ("Recommend Illustrative Packaging B for …"). */
function recommendedFrom(data: AidtraceData): string | null {
  const latest = data.snap ? latestScenarioId(data.snap.decisions) : null;
  if (!data.snap || !latest) return null;
  const valid = data.snap.decisions.filter((d) => d.id.startsWith(`gc:${latest}:`) && !isUnsafe(d.status));
  const m = /Recommend (Illustrative [A-Za-z0-9 ]+?) for/.exec(valid[valid.length - 1]?.summary ?? "");
  return m ? m[1] : null;
}

interface RunState { kind: "investigate" | "evidence"; stages: Stage[]; error: string | null; running: boolean }

function StoryModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-xs">
      <div className="relative max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-lg border border-line bg-surface p-6 shadow-xl text-ink">
        <button
          type="button"
          onClick={onClose}
          className="absolute right-4 top-4 grid size-7 place-items-center rounded border border-line text-muted hover:text-ink text-sm"
          aria-label="Close"
        >
          ✕
        </button>

        <div className="mb-4 border-b border-line pb-3">
          <div className="flex items-center gap-2">
            <h2 className="text-title font-bold text-ink">AIDTRACE</h2>
            <StatusBadge tone="info">Powered by FalkorDB</StatusBadge>
          </div>
          <p className="mt-1.5 text-caption text-muted leading-relaxed">
            An AI-powered supply-chain and industrial risk intelligence platform that detects connected risks,
            remembers the evidence behind decisions, and automatically identifies which decisions need reconsideration when new information arrives.
          </p>
        </div>

        <div className="mb-5 space-y-3">
          <h3 className="text-caption font-semibold uppercase tracking-wider text-muted">The 5-Step Operational Lifecycle</h3>
          <ol className="space-y-2.5 text-caption">
            <li className="flex items-start gap-2.5 rounded border border-line/70 bg-canvas p-2.5">
              <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-accent text-[11px] font-bold text-on-accent">1</span>
              <div>
                <p className="font-semibold text-ink">Global Supply Chain on CesiumJS 3D Earth</p>
                <p className="text-micro text-muted">Visualizes global suppliers, shipping corridors, and downstream industrial facilities with real terrain.</p>
              </div>
            </li>
            <li className="flex items-start gap-2.5 rounded border border-line/70 bg-canvas p-2.5">
              <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-accent text-[11px] font-bold text-on-accent">2</span>
              <div>
                <p className="font-semibold text-ink">Connected Risk & Cyber Exposure Detection</p>
                <p className="text-micro text-muted">Monitors technology dependencies, grid carbon intensity, and logistical chokepoints across the extended supply tier.</p>
              </div>
            </li>
            <li className="flex items-start gap-2.5 rounded border border-line/70 bg-canvas p-2.5">
              <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-accent text-[11px] font-bold text-on-accent">3</span>
              <div>
                <p className="font-semibold text-ink">FalkorDB Evidence Lineage & Persistent Memory</p>
                <p className="text-micro text-muted">Tracks past assessments, traverses GraphBLAS sparse matrices, and discovers every purchasing decision resting on affected evidence.</p>
              </div>
            </li>
            <li className="flex items-start gap-2.5 rounded border border-line/70 bg-canvas p-2.5">
              <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-accent text-[11px] font-bold text-on-accent">4</span>
              <div>
                <p className="font-semibold text-ink">Evidence Governance & Decision Gate</p>
                <p className="text-micro text-muted">Automatically halts approvals based on invalidated claims, holds transactions for review, and evaluates pre-qualified alternatives.</p>
              </div>
            </li>
            <li className="flex items-start gap-2.5 rounded border border-line/70 bg-canvas p-2.5">
              <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-accent text-[11px] font-bold text-on-accent">5</span>
              <div>
                <p className="font-semibold text-ink">Actionable Recommendation & Sourcing Pivot</p>
                <p className="text-micro text-muted">The human reviewer reviews what changed, why it matters, and approves a verified replacement with complete audit receipts.</p>
              </div>
            </li>
          </ol>
        </div>

        <div className="border-t border-line pt-3">
          <h3 className="mb-2 text-micro font-semibold uppercase tracking-wider text-muted">Unified Architecture Ecosystem</h3>
          <div className="grid grid-cols-2 gap-2 text-micro">
            <div className="rounded border border-line p-2">
              <span className="font-semibold text-ink">Operations:</span> <span className="text-muted">Governance, compliance, approvals, investigation & audit receipts</span>
            </div>
            <div className="rounded border border-line p-2">
              <span className="font-semibold text-ink">GreenChain:</span> <span className="text-muted">Global suppliers, shipping corridors, emissions & quantile scoring</span>
            </div>
            <div className="rounded border border-line p-2">
              <span className="font-semibold text-ink">CyberFlow & Track 01:</span> <span className="text-muted">Cyber dependencies, circular risk, and fraud containment</span>
            </div>
            <div className="rounded border border-line p-2">
              <span className="font-semibold text-ink">Resolve:</span> <span className="text-muted">Specialist agent investigations, evidence retrieval & case synthesis with FALKOR DB</span>
            </div>
            <div className="rounded border border-line p-2">
              <span className="font-semibold text-ink">FalkorDB:</span> <span className="text-muted">Sparse GraphBLAS matrix memory tying evidence to decisions</span>
            </div>
            <div className="rounded border border-line p-2">
              <span className="font-semibold text-ink">CesiumJS:</span> <span className="text-muted">Photorealistic 3D Earth showcasing facilities, routes & risks</span>
            </div>
          </div>
        </div>

        <div className="mt-4 flex justify-end">
          <Button variant="primary" onClick={onClose}>Explore Workspace</Button>
        </div>
      </div>
    </div>
  );
}

function LeftPanel(props: {
  data: AidtraceData; selection: Selection; onSelect: (s: Selection) => void; run: RunState | null; busy: boolean;
  onInvestigate: () => void; onUpdate: () => void; onReview: () => void; extension: string | null; onOpenExtensions: () => void; onShow: (kind: "memory" | "node" | "supplier" | "source" | "claim" | "decision" | "action") => void;
  onOpenStory: () => void;
}) {
  const { data, selection, run, busy, extension, onOpenStory } = props;
  const { snap } = data;
  const graphConnected = !data.errors.memory && !data.errors.site && Boolean(data.snap && data.site);
  const graphStatus = data.loading ? "Checking graph" : graphConnected ? "FalkorDB connected" : "Graph unavailable";
  const [question, setQuestion] = useState("");
  const [focused, setFocused] = useState(false);
  const [asking, setAsking] = useState(false);
  const [answer, setAnswer] = useState<AgentAnswer | null>(null);
  const answerRequest = useRef<AbortController | null>(null);
  useEffect(() => () => { answerRequest.current?.abort(); answerRequest.current = null; }, []);

  async function ask(text: string) {
    const q = text.trim();
    if (!q || asking) return;
    const controller = new AbortController();
    answerRequest.current = controller;
    setAsking(true); setQuestion(""); setAnswer(null);
    try {
      const fresh = await data.refreshMemory();
      if (answerRequest.current !== controller) return;
      const response = await askAgent(q, { demo: data.demo, scenario: data.scenario, snap: fresh.snap ?? data.snap,
        site: fresh.site ?? data.site, selected: selection }, controller.signal);
      if (answerRequest.current === controller) setAnswer(response);
    } catch (error) {
      if (answerRequest.current === controller && !controller.signal.aborted) {
        setAnswer({ question: q, at: new Date().toISOString(), route: "AIDTRACE site agent", ok: false,
          text: error instanceof Error ? error.message : "The graph question failed. Refresh the graph and try again.", lines: [] });
      }
    } finally {
      if (answerRequest.current === controller) { answerRequest.current = null; setAsking(false); }
    }
  }
  const reviewable = (snap?.decisions.length ?? 0) > 0;
  return (
    <div className="flex size-full min-h-0 flex-col overflow-y-auto">
      <div className="px-4 pb-3 pt-3 pr-10">
        <div className="flex items-center justify-between">
          <h1 className="text-body font-bold text-ink tracking-tight">AIDTRACE</h1>
          <button
            type="button"
            onClick={onOpenStory}
            className="rounded border border-line bg-surface px-1.5 py-0.5 text-[11px] font-medium text-accent hover:border-accent transition-colors"
            title="How AIDTRACE works (The 5-step lifecycle)"
          >
            About
          </button>
        </div>
        <p className="text-[11px] font-medium text-muted">Powered by FalkorDB</p>
        <p className="mt-1 flex items-center gap-1.5 text-micro text-muted">
          <span className={`size-1.5 rounded-full ${graphConnected ? "bg-verified" : data.loading ? "bg-caution animate-pulse" : "bg-danger"}`} aria-hidden="true" />
          <span className={`font-semibold ${graphConnected ? "text-verified" : data.loading ? "text-caution" : "text-danger"}`}>{graphStatus}</span>
          <span>· GraphBLAS OpenCypher</span>
        </p>
      </div>

      <form className="relative px-4 pb-3" onSubmit={(e) => { e.preventDefault(); void ask(question); }}>
        <label htmlFor="aidtrace-ask" className="sr-only">Ask about a supplier, risk, or decision</label>
        <div className="flex gap-1.5">
          <input id="aidtrace-ask" value={question} onChange={(e) => setQuestion(e.target.value)} onFocus={() => setFocused(true)} onBlur={() => window.setTimeout(() => setFocused(false), 150)}
            placeholder="Ask about a supplier, risk, or decision…" autoComplete="off"
            className="h-10 min-w-0 flex-1 border border-line bg-canvas px-3 text-caption text-ink placeholder:text-muted focus-visible:outline-2 focus-visible:outline-accent" />
          <Button type="submit" variant="primary" disabled={asking || !question.trim()} aria-label="Send question">{asking ? "…" : "Ask"}</Button>
          {asking && <Button type="button" variant="ghost" onClick={() => { answerRequest.current?.abort(); answerRequest.current = null; setAsking(false); }}>Stop</Button>}
        </div>
        {focused && !question && (
          <ul className="absolute inset-x-4 top-[calc(100%-0.5rem)] z-10 border border-line bg-surface shadow-sm" aria-label="Examples">
            {EXAMPLES.map((q) => <li key={q}><button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => void ask(q)} className="block w-full px-3 py-2 text-left text-micro text-ink hover:bg-surface-2">{q}</button></li>)}
          </ul>
        )}
      </form>

      <ol className="space-y-1.5 px-4 pb-3" aria-label="Primary actions">
        <li>
          <Button variant="primary" className="h-auto w-full justify-start text-left flex flex-col items-start py-2" disabled={busy || !data.scenario} onClick={props.onInvestigate}>
            <span className="font-semibold text-caption">1 · Investigate Risk</span>
            <span className="text-[11px] opacity-85 font-normal">CesiumJS 3D routes · cyber & ESG reach</span>
          </Button>
        </li>
        <li>
          <Button variant="ghost" className="h-auto w-full justify-start text-left flex flex-col items-start py-2 border border-line" disabled={busy || !data.scenario} onClick={props.onUpdate}>
            <span className="font-semibold text-caption">2 · Update Evidence</span>
            <span className="text-[11px] text-muted font-normal">Propagate grid/cyber drift into FalkorDB</span>
          </Button>
        </li>
        <li>
          <Button variant="ghost" className="h-auto w-full justify-start text-left flex flex-col items-start py-2 border border-line" disabled={!reviewable} onClick={props.onReview}>
            <span className="font-semibold text-caption">3 · Review Decision</span>
            <span className="text-[11px] text-muted font-normal">Hold stale approval · review an alternative</span>
          </Button>
        </li>
      </ol>

      {run && (
        <section aria-label="Progress" className="border-t border-line px-4 py-3">
          <p className="mb-1 text-micro font-medium uppercase tracking-wider text-muted">{run.kind === "investigate" ? "Investigating" : "Updating evidence"}{run.running && " …"}</p>
          <ol className="space-y-1" data-testid="aidtrace-progress">
            {run.stages.map((s) => (
              <li key={s.id} className="flex items-start gap-2 text-micro">
                <span className={`mt-1 size-1.5 shrink-0 rounded-full ${dot[s.status]}`} aria-hidden="true" />
                <span className={s.status === "pending" ? "text-muted" : "text-ink"}>{s.label}{s.detail && <span className="block text-muted">{s.detail}</span>}<span className="sr-only"> ({s.status})</span></span>
              </li>
            ))}
          </ol>
          {run.error && <p role="alert" className="mt-2 border-l-2 border-danger pl-2 text-micro text-danger">{run.error}</p>}
        </section>
      )}

      {answer && (
        <section aria-label="Answer" className={`mx-4 mb-3 border-l-2 bg-surface p-2.5 text-caption ${answer.ok ? "border-accent" : "border-line"}`}>
          <p className="text-micro text-muted">{answer.question}</p>
          <p className="mt-1 text-ink">{answer.text}</p>
          {answer.lines.length > 0 && answer.ok && <ul className="mt-1 max-h-32 space-y-0.5 overflow-y-auto text-micro text-muted">{answer.lines.map((l, i) => <li key={i}>{l}</li>)}</ul>}
          <p className="mt-1 text-micro text-muted">{answer.route}</p>
          {answer.records?.length ? <div className="mt-2 flex flex-wrap gap-1.5">{answer.records.map((record) => <Button key={`${record.kind}-${record.id}`} variant="ghost" className="max-w-full truncate" onClick={() => { props.onSelect(record); props.onShow(record.kind); }}>Inspect {record.label}</Button>)}</div> : answer.select && <Button className="mt-1" variant="ghost" onClick={() => { props.onSelect(answer.select!); props.onShow(answer.select!.kind === "memory" ? "memory" : answer.select!.kind === "node" ? "node" : "supplier"); }}>Show in workspace</Button>}
        </section>
      )}

      <div className="mt-auto space-y-2 border-t border-line px-4 py-3">
        <label htmlFor="aidtrace-source" className="block text-micro font-medium uppercase tracking-wider text-muted">Evidence source</label>
        <select id="aidtrace-source" value={selection?.kind === "source" ? selection.id : ""} disabled={!snap?.sources.length}
          onChange={(e) => { const s = snap?.sources.find((x) => x.id === e.target.value); if (s) { props.onSelect({ kind: "source", id: s.id, label: s.title || s.id }); props.onShow("memory"); } }}
          className="h-9 w-full border border-line bg-canvas px-2 text-caption">
          <option value="">{snap?.sources.length ? "Inspect a source…" : "No sources recorded yet"}</option>
          {snap?.sources.map((s) => <option key={s.id} value={s.id}>{s.title || s.id}</option>)}
        </select>
        <button type="button" onClick={props.onOpenExtensions} aria-haspopup="dialog" data-testid="aidtrace-extensions-button"
          className={`flex w-full items-center justify-between border px-3 py-2 text-left text-caption ${extension ? "border-ink bg-surface-2 font-semibold" : "border-line bg-surface hover:bg-surface-2"}`}>
          <span>Extensions</span><span className="text-micro font-normal text-muted">{extension ? extensionById(extension)?.title : "More tools"}</span>
        </button>
      </div>
    </div>
  );
}

export function AidtraceWorkspace() {
  const data = useAidtraceData();
  const [view, setView] = useState<ViewId>("globe");
  const role = useRole();
  const [extension, setExtension] = useState<{ id: string; path: string | null; nonce: number } | null>(null);
  const [launcherOpen, setLauncherOpen] = useState(false);
  const [storyOpen, setStoryOpen] = useState(false);
  const [selection, setSelection] = useState<Selection>(null);
  const [section, setSection] = useState<Section>("risk");
  const [leftOpen, setLeftOpen] = useState(true);
  const [rightOpen, setRightOpen] = useState(true);
  const [run, setRun] = useState<RunState | null>(null);
  const [investigation, setInvestigation] = useState<InvestigationResult | null>(null);
  const [evidence, setEvidence] = useState<EvidenceResult | null>(null);
  const [runs, setRuns] = useState<RunLogEntry[]>([]);
  const [banner, setBanner] = useState<string | null>(null);
  const [slot, setSlot] = useState<HTMLElement | null>(null);
  const busy = Boolean(run?.running);
  const recommended = evidence?.topAfter ?? recommendedFrom(data);

  useEffect(() => { const t = window.setTimeout(() => setSlot(document.getElementById("aidtrace-topbar-slot")), 0); return () => window.clearTimeout(t); }, []);
  useEffect(() => { if (!banner) return; const t = window.setTimeout(() => setBanner(null), 14000); return () => window.clearTimeout(t); }, [banner]);

  const select = useCallback((s: Selection) => {
    setSelection(s);
    if (!s) return;
    setRightOpen(true);
    setSection(s.kind === "supplier" || s.kind === "node" ? "risk" : s.kind === "decision" || s.kind === "action" ? "decision" : "evidence");
  }, []);
  const changeView = useCallback((v: ViewId) => { setView(v); setExtension(null); }, []);
  /** Open an extension in the centre. Role rules decide who may; the investigation state stays where it is. */
  const openExtension = useCallback((id: string, path?: string) => {
    const ext = extensionById(id);
    if (!ext || !isAvailable(ext, role)) return;
    setLauncherOpen(false);
    setExtension((cur) => ({ id, path: path ?? null, nonce: (cur?.nonce ?? 0) + 1 }));
  }, [role]);
  const closeExtension = useCallback(() => setExtension(null), []);

  async function execute<T>(kind: RunState["kind"], fn: (onStages: (s: Stage[]) => void) => Promise<T>): Promise<T | null> {
    setExtension(null);
    let latest: Stage[] = [];
    setRun({ kind, stages: [], error: null, running: true });
    try {
      const out = await fn((stages) => { latest = stages; setRun({ kind, stages, error: null, running: true }); });
      setRun({ kind, stages: latest, error: null, running: false });
      return out;
    } catch (e) {
      const failed = latest.map((s) => (s.status === "running" ? { ...s, status: "failed" as const } : s));
      setRun({ kind, stages: failed, error: e instanceof Error ? e.message : "The workflow failed.", running: false });
      return null;
    }
  }
  const log = (kind: string, text: string) => setRuns((r) => [{ at: new Date().toISOString(), kind, text }, ...r]);

  async function onInvestigate() {
    // With nothing selected, investigate the supplier the current decision recommends: it is the one the recorded evidence is about.
    const target = selection?.kind === "supplier" ? selection.id : data.scenario?.manufacturers.find((m) => m.name === recommended)?.id ?? null;
    const r = await execute("investigate", (on) => investigateRisk({ data, supplierId: target }, on));
    if (!r) return;
    setInvestigation(r);
    await data.refreshMemory();
    setView((v) => (v === "timeline" ? v : "globe"));
    select({ kind: "supplier", id: r.supplierId, label: r.supplierName });
    setSection("risk");
    setBanner(`${plain(r.supplierName)}: ${r.dependents.length} dependants · ${r.decisions.filter((d) => d.stale).length} stale decision(s)`);
    log("investigation", `Investigated ${plain(r.supplierName)}: ${r.findings[0]}`);
  }
  async function onUpdate() {
    const r = await execute("evidence", (on) => updateEvidence(data, on));
    if (!r) return;
    setEvidence(r);
    setView("globe");
    const affected = data.scenario?.manufacturers.find((m) => m.name === r.topBefore);
    if (affected) setSelection({ kind: "supplier", id: affected.id, label: affected.name });
    setSection("decision"); setRightOpen(true);
    setBanner(r.alreadyApplied ? "This evidence update was already applied." : r.recommendationChanged ? `Recommendation changed: ${plain(r.topBefore ?? "")} → ${plain(r.topAfter ?? "")}` : `Re-evaluated: ${plain(r.topAfter ?? "")} stays recommended`);
    log("evidence update", `${r.revision.dataset} ${r.revision.country} ×${r.revision.factor} (synthetic): ${r.alreadyApplied ? "already applied" : `${r.invalidated.length} record(s) invalidated, recommendation ${r.recommendationChanged ? `${plain(r.topBefore ?? "")} → ${plain(r.topAfter ?? "")}` : "unchanged"}`}`);
  }
  function onReview() { setRightOpen(true); setSection("decision"); }

  const connected = !data.errors.memory && !data.errors.site && Boolean(data.snap && data.site);
  const refreshing = data.refreshing;
  const loading = data.loading;
  const refreshAll = data.refreshAll;
  const ext = extension ? extensionById(extension.id) : null;
  const shared: AidtraceContextValue = { data, selection, select, investigation, evidence, recommended, view, runs, openExtension };
  const common = { data, selection, onSelect: select };
  const cols = `${leftOpen ? "288px" : "40px"} minmax(0,1fr) ${rightOpen ? "312px" : "40px"}`;
  const scenarioName = data.demo ? `${data.demo.product} → ${data.demo.destination}` : "Loading scenario…";

  const topbar = useMemo(() => (
    <>
      <span className="hidden truncate text-caption text-ink xl:inline" title={scenarioName}>{scenarioName}</span>
      <span className={`ml-auto flex items-center gap-1.5 text-micro ${connected ? "text-ink" : "text-danger"}`} role="status"><span className={`size-1.5 rounded-full ${connected ? "bg-verified" : "bg-danger"}`} aria-hidden="true" />{loading ? "Connecting…" : connected ? "Graph current" : "Graph read unavailable"}</span>
      <button type="button" disabled={refreshing} onClick={() => void refreshAll?.()} className="ml-2 text-micro text-muted underline underline-offset-2 disabled:opacity-50">{refreshing ? "Refreshing…" : "Refresh graph"}</button>
    </>
  ), [scenarioName, connected, loading, refreshing, refreshAll]);

  function onKey(e: React.KeyboardEvent) {
    const i = VIEWS.findIndex((v) => v.id === view);
    if (e.key === "ArrowRight") changeView(VIEWS[(i + 1) % VIEWS.length].id);
    else if (e.key === "ArrowLeft") changeView(VIEWS[(i + VIEWS.length - 1) % VIEWS.length].id);
    else return;
    e.preventDefault();
  }

  return (
    <AidtraceProvider value={shared}>
    <div data-testid="aidtrace-workspace" className="grid h-full min-h-dvh grid-cols-1 lg:min-h-0 lg:[grid-template-columns:var(--cols)]" style={{ "--cols": cols } as React.CSSProperties}>
      {slot && createPortal(topbar, slot)}
      <StoryModal open={storyOpen} onClose={() => setStoryOpen(false)} />
      <aside aria-label="Investigate" className="order-2 min-h-0 border-b border-line bg-surface lg:order-1 lg:border-b-0 lg:border-r">
        {leftOpen ? (
          <div className="relative size-full">
            <button type="button" aria-label="Collapse investigate panel" onClick={() => setLeftOpen(false)} className="absolute right-2 top-2.5 z-10 hidden size-7 place-items-center text-muted hover:text-ink lg:grid">‹</button>
            <LeftPanel data={data} selection={selection} onSelect={select} run={run} busy={busy} onInvestigate={() => void onInvestigate()} onUpdate={() => void onUpdate()} onReview={onReview}
              extension={extension?.id ?? null} onOpenExtensions={() => setLauncherOpen(true)} onOpenStory={() => setStoryOpen(true)} onShow={(k) => changeView(k === "supplier" ? "globe" : k === "node" || k === "claim" ? "graph" : "lineage")} />
          </div>
        ) : <button type="button" aria-label="Expand investigate panel" onClick={() => setLeftOpen(true)} className="hidden size-full place-items-start justify-center pt-3 text-muted hover:text-ink lg:grid">›</button>}
      </aside>

      <section aria-label="Intelligence workspace" className="relative order-1 flex min-h-[72dvh] min-w-0 flex-col lg:order-2 lg:min-h-0">
        <div className="flex items-center justify-between gap-2 border-b border-line px-3 py-1.5">
          <div role="tablist" aria-label="Workspace view" onKeyDown={onKey} className="flex gap-1">
            {VIEWS.map((v) => (
              <button key={v.id} role="tab" type="button" aria-selected={!ext && view === v.id} tabIndex={!ext && view === v.id ? 0 : -1} onClick={() => changeView(v.id)}
                className={`border px-3 py-1 text-caption ${!ext && view === v.id ? "border-ink bg-ink text-canvas" : "border-line bg-surface text-ink hover:bg-surface-2"}`}>{v.label}</button>
            ))}
          </div>
          {ext && <span className="text-micro text-muted">Viewing an extension — your investigation is preserved.</span>}
        </div>
        <div className="min-h-0 flex-1 overflow-hidden" role="tabpanel" aria-label={ext ? ext.title : VIEWS.find((v) => v.id === view)?.label}>
          {ext && extension ? (
            <Boundary key={`${ext.id}:${extension.nonce}`} label={ext.title}>
              <ExtensionPanel ext={ext} initialPath={extension.path} onClose={closeExtension} onOpen={openExtension} />
            </Boundary>
          ) : (
            <Boundary key={view} label={VIEWS.find((v) => v.id === view)?.label ?? "View"}>
              {view === "globe" && <GlobeView {...common} recommendedName={recommended} banner={banner} />}
              {view === "graph" && <GraphView {...common} />}
              {view === "lineage" && <LineageView {...common} />}
              {view === "timeline" && <TimelineView data={data} runs={runs} onSelect={select} />}
            </Boundary>
          )}
        </div>
        <ExtensionLauncher open={launcherOpen} role={role} onClose={() => setLauncherOpen(false)} onSelect={(id) => openExtension(id)} />
      </section>

      <aside aria-label="Inspector" className="order-3 min-h-0 border-t border-line bg-surface lg:border-l lg:border-t-0">
        {rightOpen ? (
          <div className="relative size-full">
            <button type="button" aria-label="Collapse inspector" onClick={() => setRightOpen(false)} className="absolute right-1 top-2 z-10 hidden size-7 place-items-center text-muted hover:text-ink lg:grid">›</button>
            <Inspector data={data} selection={selection} onSelect={select} open={section} onOpen={(s) => setSection(s)} investigation={investigation} evidence={evidence} onInvestigate={() => void onInvestigate()} busy={busy} />
          </div>
        ) : <button type="button" aria-label="Expand inspector" onClick={() => setRightOpen(true)} className="hidden size-full place-items-start justify-center pt-3 text-muted hover:text-ink lg:grid">‹</button>}
      </aside>
    </div>
    </AidtraceProvider>
  );
}
