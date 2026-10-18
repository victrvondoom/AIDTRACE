"use client";

// The hub overview: a live 3D capability graph that doubles as the application launcher. Everything shown is read from
// /hub/capabilities (probed now). Three ways in to the same data so nothing depends on WebGL or a pointer: the 3D scene,
// a 2D graph (the fallback when WebGL is missing), and a text table of states and dependencies. A row of real buttons under
// the scene is the keyboard and touch route to every workspace.
import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useState } from "react";
import { GraphViews, type GraphMarks } from "@/components/graph-views";
import { Button, FilterTabs, StatusBadge } from "@/components/ui";
import type { LabGraph } from "@/lib/graph-layout";
import { hubCapabilities, type CapabilityState, type HubCapabilities, type HubCapability } from "@/lib/lab-api";

const Scene = dynamic(() => import("@/components/features/overview/CapabilityGlobe3D").then((m) => m.CapabilityGlobe3D), {
  ssr: false,
  loading: () => <p role="status" className="grid h-full place-items-center text-caption text-muted">Loading 3D graph…</p>,
});

const TONE: Record<CapabilityState, "verified" | "caution" | "danger"> = { OPERATIONAL: "verified", LIMITED: "caution", UNAVAILABLE: "danger" };
const MARK: Record<CapabilityState, string> = { OPERATIONAL: "proceed", LIMITED: "possible", UNAVAILABLE: "blocker" };
const REFRESH_MS = 30000;

function webgl(): boolean {
  try {
    const c = document.createElement("canvas");
    return Boolean(c.getContext("webgl2") ?? c.getContext("webgl"));
  } catch { return false; }
}

function toLabGraph(data: HubCapabilities): { graph: LabGraph; marks: GraphMarks } {
  const edge = (source: string, target: string, rel: string, certainty: "definite" | "maybe") => ({ source, target, rel, weight: 1, certainty, at: null, until: null, disabled: false });
  const caps = data.capabilities;
  return {
    graph: {
      nodes: caps.map((c) => ({ id: c.id, label: c.name, type: c.id === "overview" ? "core" : c.state, props: { state: c.state } })),
      edges: [...caps.filter((c) => c.id !== "overview").map((c) => edge("overview", c.id, "HOSTS", "definite")), ...data.edges.map((e) => edge(e.source, e.target, e.rel, "maybe"))],
    },
    marks: { node_marks: Object.fromEntries(caps.filter((c) => c.id !== "overview").map((c) => [c.id, MARK[c.state]])) },
  };
}

export function Overview3D({ onOpen }: { onOpen: (id: string) => void }) {
  const [data, setData] = useState<HubCapabilities | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<"3d" | "2d" | "text">("3d");
  const [inspected, setInspected] = useState<string | null>(null);
  const [gl, setGl] = useState<boolean | null>(null);

  const load = useCallback(async () => {
    try { setData(await hubCapabilities()); setError(null); } catch (e) { setError(e instanceof Error ? e.message : "Capability status could not be read."); }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => { setGl(webgl()); void load(); }, 0);
    const interval = window.setInterval(() => { if (!document.hidden) void load(); }, REFRESH_MS);
    return () => { window.clearTimeout(timer); window.clearInterval(interval); };
  }, [load]);

  const caps = useMemo(() => data?.capabilities ?? [], [data]);
  const byId = useMemo(() => new Map(caps.map((c) => [c.id, c])), [caps]);
  const focus: HubCapability | null = (inspected ? byId.get(inspected) : null) ?? null;
  const lab = useMemo(() => (data ? toLabGraph(data) : null), [data]);
  const counts = useMemo(() => ({ operational: caps.filter((c) => c.state === "OPERATIONAL").length, limited: caps.filter((c) => c.state === "LIMITED").length, down: caps.filter((c) => c.state === "UNAVAILABLE").length }), [caps]);
  const use3d = view === "3d" && gl === true;
  const related = (id: string) => data ? {
    dependsOn: data.edges.filter((e) => e.target === id).map((e) => byId.get(e.source)?.name).filter(Boolean) as string[],
    feeds: data.edges.filter((e) => e.source === id).map((e) => byId.get(e.target)?.name).filter(Boolean) as string[],
  } : { dependsOn: [], feeds: [] };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-title font-semibold">AIDTRACE intelligence graph</h2>
          <p className="mt-1 max-w-3xl text-caption leading-relaxed text-muted">Each card is a capability, coloured by whether its runtime answered just now. Drag to rotate, scroll to zoom, hover to inspect and click to open it here. Nothing leaves this page.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {data && <><StatusBadge tone="verified">{counts.operational} operational</StatusBadge><StatusBadge tone="caution">{counts.limited} limited</StatusBadge>{counts.down > 0 && <StatusBadge tone="danger">{counts.down} unavailable</StatusBadge>}</>}
          <Button variant="ghost" onClick={() => void load()}>Refresh status</Button>
        </div>
      </div>
      {error && <p role="alert" className="border-l-2 border-danger bg-surface p-3 text-caption text-danger">{error} <Button variant="ghost" onClick={() => void load()}>Retry</Button></p>}

      <FilterTabs tabs={[{ key: "3d", label: "3D graph" }, { key: "2d", label: "2D graph" }, { key: "text", label: "Text" }]} active={view} onChange={(k) => setView(k as "3d" | "2d" | "text")} />
      {view === "3d" && gl === false && <p role="status" className="border-l-2 border-caution bg-surface p-3 text-caption text-muted">WebGL is not available in this browser, so the 2D graph is shown instead. Every capability is still reachable below.</p>}

      {data && lab && (view === "2d" || (view === "3d" && gl === false)) && <GraphViews graph={lab.graph} marks={lab.marks} onSelect={(id) => { if (id !== "overview") onOpen(id); }} />}
      {data && use3d && (
        <div className="relative h-[460px] overflow-hidden border border-line bg-[#070b14] sm:h-[540px]" role="group" aria-label="3D capability graph. The buttons below it are the keyboard-accessible equivalent.">
          <Scene capabilities={caps} edges={data.edges} inspectedId={inspected} onInspect={setInspected} onOpen={(id) => { if (id !== "overview") onOpen(id); }} className="size-full" />
          <p className="pointer-events-none absolute bottom-2 left-3 text-micro text-slate-300">Drag to rotate · scroll to zoom · click a card to open it</p>
        </div>
      )}
      {!data && !error && <p role="status" className="text-caption text-muted">Probing capabilities…</p>}

      {data && view === "text" && (
        <div className="overflow-x-auto border border-line bg-surface">
          <table className="w-full text-left text-caption">
            <caption className="sr-only">Capabilities, their live state and dependencies</caption>
            <thead className="bg-surface-2 text-muted"><tr>{["Capability", "State", "What it does now", "Depends on", "Feeds"].map((h) => <th key={h} scope="col" className="p-3 font-semibold">{h}</th>)}</tr></thead>
            <tbody>{caps.filter((c) => c.id !== "overview").map((c) => { const r = related(c.id); return (
              <tr key={c.id} className="border-t border-line align-top">
                <th scope="row" className="p-3 font-medium"><button type="button" className="underline" onClick={() => onOpen(c.id)}>{c.name}</button></th>
                <td className="p-3"><StatusBadge tone={TONE[c.state]}>{c.state.toLowerCase()}</StatusBadge></td>
                <td className="p-3">{c.detail}{c.limits.map((l) => <span key={l} className="block text-micro text-muted">Limit: {l}</span>)}</td>
                <td className="p-3 text-muted">{r.dependsOn.join(", ") || "none"}</td><td className="p-3 text-muted">{r.feeds.join(", ") || "none"}</td>
              </tr>); })}</tbody>
          </table>
        </div>
      )}

      {data && view !== "text" && (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,340px)]">
          <nav aria-label="Open a capability" className="flex flex-wrap gap-2">
            {caps.filter((c) => c.id !== "overview").map((c) => (
              <button key={c.id} type="button" onClick={() => onOpen(c.id)} onFocus={() => setInspected(c.id)} onMouseEnter={() => setInspected(c.id)} onBlur={() => setInspected(null)}
                className={`min-h-11 border px-3 text-left text-caption hover:bg-surface-2 ${inspected === c.id ? "border-ink bg-surface-2" : "border-line bg-surface"}`}>
                <span aria-hidden className={`mr-2 inline-block size-2 rounded-full ${c.state === "OPERATIONAL" ? "bg-verified" : c.state === "LIMITED" ? "bg-caution" : "bg-danger"}`} />
                {c.name}<span className="sr-only"> ({c.state.toLowerCase()})</span>
              </button>))}
          </nav>
          <aside aria-live="polite" className="min-h-28 border border-line bg-surface p-4 text-caption">
            {focus ? (<>
              <p className="flex items-center justify-between gap-2"><strong className="text-body">{focus.name}</strong><StatusBadge tone={TONE[focus.state]}>{focus.state.toLowerCase()}</StatusBadge></p>
              <p className="mt-1 text-muted">{focus.detail}</p>
              {focus.limits.length > 0 && <ul className="mt-2 list-disc space-y-1 pl-5 text-micro text-muted">{focus.limits.map((l) => <li key={l}>{l}</li>)}</ul>}
              {(related(focus.id).dependsOn.length > 0 || related(focus.id).feeds.length > 0) && <p className="mt-2 text-micro text-muted">{related(focus.id).dependsOn.length > 0 && <>Depends on {related(focus.id).dependsOn.join(", ")}. </>}{related(focus.id).feeds.length > 0 && <>Feeds {related(focus.id).feeds.join(", ")}.</>}</p>}
              <Button className="mt-3" variant="primary" onClick={() => onOpen(focus.id)}>Open {focus.name}</Button>
            </>) : <p className="text-muted">Hover or focus a capability to see its live status, its limits and what it connects to.</p>}
            {data && <p className="mt-3 text-micro text-muted">Status read {data.generated_at.slice(11, 19)} UTC · refreshes every 30 seconds</p>}
          </aside>
        </div>
      )}
    </div>
  );
}
