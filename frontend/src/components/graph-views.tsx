"use client";

// One graph, six lenses. Network / Layered / Radial are SVG node-link views; Matrix shows who-links-to-whom;
// Timeline shows when relationships were valid; Table is the accessible, sortable-by-eye fallback. Every view
// reads the same `marks` returned by a Graph Lab engine, so a result is coloured identically everywhere.
import { useMemo, useState } from "react";
import { FilterTabs } from "@/components/ui";
import { layout, type LabEdge, type LabGraph, type LabNode, type LayoutKind } from "@/lib/graph-layout";

export interface GraphMarks {
  node_marks?: Record<string, string>;
  edge_marks?: Record<string, string>;
  node_badges?: Record<string, string>;
  node_metric?: Record<string, number>;
}
type Tone = "accent" | "danger" | "caution" | "verified" | "info" | "muted";
type ViewKey = "network" | "layered" | "radial" | "matrix" | "timeline" | "table";

const W = 1000, H = 600, PAD = 60, MATRIX_LIMIT = 60;
const NO_MARKS: Record<string, string> = {};
const VAR: Record<Tone, string> = { accent: "var(--accent)", danger: "var(--danger)", caution: "var(--caution)", verified: "var(--verified)", info: "var(--info)", muted: "var(--muted)" };
const COMMUNITY: Tone[] = ["info", "verified", "caution", "accent", "danger", "muted"];
const ROLE_TONE: Record<string, Tone> = {
  impacted: "danger", blocker: "danger", cut: "danger", contaminated: "danger", retracted: "danger", cycle: "danger", chokepoint: "danger",
  disrupted: "danger", refutes: "danger", refuted: "danger", hold: "danger", impact: "danger",
  possible: "caution", review: "caution", exposed: "caution", bridge: "caution", contested: "caution", insufficient_evidence: "caution", unverified: "caution",
  proceed: "verified", supported: "verified", supports: "verified", route: "verified",
  changed: "accent", source: "accent", claim: "accent", hub: "accent", target: "info",
};

export const TYPE_TONES: Record<string, Tone> = {
  Document: "accent",
  SourceVersion: "accent",
  Claim: "accent",
  Decision: "verified",
  DecisionRevision: "accent",
  Memory: "verified",
  Agent: "info",
  AgentSession: "caution",
  Approval: "verified",
  ActionProposal: "caution",
  ChangeEvent: "danger",
  Asset: "caution",
  Supplier: "accent",
  AuditEvent: "muted",
  Transaction: "danger",
  Account: "accent",
  Device: "info",
  CitizenCase: "caution",
};

export const TYPE_GLYPHS: Record<string, string> = {
  Document: "DOC",
  SourceVersion: "SRC",
  Claim: "CLM",
  Decision: "DEC",
  DecisionRevision: "REV",
  Memory: "MEM",
  Agent: "AGT",
  AgentSession: "SES",
  Approval: "APP",
  ActionProposal: "ACT",
  ChangeEvent: "EVT",
  Asset: "AST",
  Supplier: "SUP",
  AuditEvent: "LOG",
  Transaction: "TX",
  Account: "ACC",
  Device: "DEV",
};

export function toneFor(role?: string): Tone | null {
  if (!role || role === "hidden") return null;
  if (role.startsWith("community:")) return COMMUNITY[Number(role.slice(10)) % COMMUNITY.length] ?? "muted";
  return ROLE_TONE[role] ?? null;
}

const short = (s: string, n = 22) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);
const fmtDate = (s: string | null) => (s ? s.slice(0, 10) : "—");

export function GraphViews({ graph, marks, selected, onSelect }: {
  graph: LabGraph; marks?: GraphMarks; selected?: string | null; onSelect?: (id: string) => void;
}) {
  const hasTime = graph.edges.some((e) => e.at || e.until);
  const [view, setView] = useState<ViewKey>("network");
  const [zoom, setZoom] = useState(1);
  const [hover, setHover] = useState<string | null>(null);
  const [showDisabled, setShowDisabled] = useState(true);
  const nodeMarks = marks?.node_marks ?? NO_MARKS, edgeMarks = marks?.edge_marks ?? NO_MARKS;
  const byId = useMemo(() => new Map(graph.nodes.map((n) => [n.id, n])), [graph]);
  const visibleEdges = useMemo(
    () => graph.edges.map((e, i) => ({ e, i })).filter(({ e }) => showDisabled || !e.disabled),
    [graph, showDisabled],
  );
  const layoutKind: LayoutKind = view === "layered" ? "layered" : view === "radial" ? "radial" : "network";
  const pos = useMemo(() => layout(layoutKind, graph, selected ?? undefined), [layoutKind, graph, selected]);
  const roles = useMemo(() => [...new Set([...Object.values(nodeMarks), ...Object.values(edgeMarks), ...Object.values(marks?.node_badges ?? {})])].filter((r) => r !== "hidden").sort(), [nodeMarks, edgeMarks, marks]);
  const metricMax = Math.max(...Object.values(marks?.node_metric ?? { x: 0 }), 1e-9);
  const neighbours = useMemo(() => {
    const set = new Set<string>();
    if (hover) for (const { e } of visibleEdges) { if (e.source === hover) set.add(e.target); if (e.target === hover) set.add(e.source); }
    return set;
  }, [hover, visibleEdges]);

  const tabs = [
    { key: "network", label: "Network" }, { key: "layered", label: "Layered" }, { key: "radial", label: "Radial" },
    { key: "matrix", label: "Matrix" }, ...(hasTime ? [{ key: "timeline", label: "Timeline" }] : []), { key: "table", label: "Table" },
  ];
  const px = (id: string) => PAD + (pos[id]?.x ?? 0.5) * (W - 2 * PAD);
  const py = (id: string) => PAD + (pos[id]?.y ?? 0.5) * (H - 2 * PAD);
  const labelAll = graph.nodes.length <= 150;
  const sel = selected ? byId.get(selected) : undefined;

  function edgePath(e: LabEdge) {
    const [x1, y1, x2, y2] = [px(e.source), py(e.source), px(e.target), py(e.target)];
    if (e.source === e.target) return `M ${x1} ${y1 - 14} c -26 -44 26 -44 0 0`;
    const dx = x2 - x1, dy = y2 - y1, d = Math.hypot(dx, dy) || 1;
    const ux = dx / d, uy = dy / d, r = 16;
    const [sx, sy, tx, ty] = [x1 + ux * r, y1 + uy * r, x2 - ux * (r + 6), y2 - uy * (r + 6)];
    const bend = 0.12 * d;
    return `M ${sx} ${sy} Q ${(sx + tx) / 2 - uy * bend} ${(sy + ty) / 2 + ux * bend} ${tx} ${ty}`;
  }

  function nodeEl(n: LabNode) {
    const role = nodeMarks[n.id];
    const status = String(n.props?.status ?? "");
    const isUnsafeStatus = status === "INVALIDATED" || status === "STALE" || status === "SUPERSEDED" || status === "DISRUPTED";
    const tone = toneFor(role) ?? (isUnsafeStatus ? "danger" : TYPE_TONES[n.type] ?? null);
    const hidden = role === "hidden";
    const baseR = n.type === "Document" || n.type === "Decision" || n.type === "Agent" ? 14 : 12;
    const r = baseR + 12 * Math.sqrt((marks?.node_metric?.[n.id] ?? 0) / metricMax);
    const dim = hidden || (hover !== null && hover !== n.id && !neighbours.has(n.id));
    const isSel = selected === n.id;
    const badge = marks?.node_badges?.[n.id] ?? (status || undefined);
    const glyph = TYPE_GLYPHS[n.type] ?? n.type.slice(0, 3).toUpperCase();
    return (
      <g key={n.id} transform={`translate(${px(n.id)} ${py(n.id)})`} opacity={dim ? 0.28 : 1} role="button" tabIndex={0} style={{ cursor: "pointer" }}
        aria-label={`${n.label}, ${n.type}${role ? `, ${role}` : ""}${status ? `, ${status}` : ""}`} aria-pressed={isSel}
        onClick={() => onSelect?.(n.id)} onKeyDown={(ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); onSelect?.(n.id); } }}
        onMouseEnter={() => setHover(n.id)} onMouseLeave={() => setHover(null)} onFocus={() => setHover(n.id)} onBlur={() => setHover(null)}>
        {isSel && <circle r={r + 7} style={{ fill: "none", stroke: "var(--ink)", strokeWidth: 2.5, strokeDasharray: "4 3" }} />}
        <circle r={r} style={{ fill: tone ? VAR[tone] : "var(--surface)", fillOpacity: tone ? 0.22 : 1, stroke: tone ? VAR[tone] : "var(--muted)", strokeWidth: tone ? 2.5 : 1.5 }} />
        {badge && <circle r={r + 3.5} style={{ fill: "none", stroke: VAR[toneFor(badge) ?? tone ?? "accent"], strokeWidth: 1.5, strokeDasharray: "2 2" }} />}
        <text textAnchor="middle" dominantBaseline="central" fontSize={r >= 14 ? 9.5 : 8} fontWeight="700" style={{ fill: tone ? VAR[tone] : "var(--ink)", pointerEvents: "none", userSelect: "none" }}>{glyph}</text>
        {(labelAll || tone || isSel || hover === n.id) && (
          <text y={r + 14} textAnchor="middle" fontSize={11} fontWeight={isSel ? "700" : "500"} style={{ fill: "var(--ink)", stroke: "var(--surface)", strokeWidth: 3, paintOrder: "stroke" }}>{short(n.label)}</text>
        )}
        <title>{`${n.label} (${n.type}) · ID: ${n.id}${role ? ` · ${role}` : ""}${status ? ` · Status: ${status}` : ""}`}</title>
      </g>
    );
  }

  return (
    <div className="border border-line bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line p-3">
        <FilterTabs tabs={tabs} active={view} onChange={(k) => setView(k as ViewKey)} />
        <div className="flex flex-wrap items-center gap-3 text-caption text-muted">
          {graph.edges.some((e) => e.disabled) && (
            <label className="flex items-center gap-2"><input type="checkbox" checked={showDisabled} onChange={(ev) => setShowDisabled(ev.target.checked)} />Show non-dependency links</label>
          )}
          {(view === "network" || view === "layered" || view === "radial") && (
            <span className="flex items-center gap-1" role="group" aria-label="Zoom">
              <button type="button" className="min-h-9 min-w-9 border border-line" aria-label="Zoom out" onClick={() => setZoom((z) => Math.max(1, z - 0.5))}>−</button>
              <button type="button" className="min-h-9 min-w-9 border border-line" aria-label="Zoom in" onClick={() => setZoom((z) => Math.min(3, z + 0.5))}>+</button>
              <button type="button" className="min-h-9 border border-line px-2" onClick={() => setZoom(1)}>Fit</button>
            </span>
          )}
          <span>{graph.nodes.length} nodes · {graph.edges.length} links</span>
        </div>
      </div>

      {(view === "network" || view === "layered" || view === "radial") && (
        <div className="max-h-[640px] overflow-auto" role="region" aria-label={`${view} graph view`}>
          <svg viewBox={`0 0 ${W} ${H}`} style={{ width: `${zoom * 100}%`, minWidth: 560 }} role="img" aria-label={`Graph with ${graph.nodes.length} nodes and ${graph.edges.length} links`}>
            <defs>
              {(Object.keys(VAR) as Tone[]).map((t) => (
                <marker key={t} id={`arr-${t}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" markerUnits="userSpaceOnUse" orient="auto-start-reverse">
                  <path d="M0,0 L10,5 L0,10 z" style={{ fill: VAR[t] }} />
                </marker>
              ))}
            </defs>
            {visibleEdges.map(({ e, i }) => {
              const role = edgeMarks[String(i)];
              const tone = toneFor(role) ?? "muted";
              const hidden = role === "hidden";
              const faded = hidden || (hover !== null && e.source !== hover && e.target !== hover);
              return (
                <path key={i} d={edgePath(e)} fill="none" markerEnd={e.source === e.target ? undefined : `url(#arr-${tone})`}
                  opacity={faded ? 0.12 : e.disabled ? 0.4 : role ? 0.95 : 0.55}
                  style={{ stroke: VAR[tone], strokeWidth: role === "cut" ? 3.5 : role ? 2.5 : 1.3, strokeDasharray: role === "cut" || e.certainty === "maybe" ? "7 5" : e.disabled ? "2 4" : undefined }}>
                  <title>{`${e.source} —${e.rel}→ ${e.target} · weight ${e.weight}${e.certainty === "maybe" ? " · maybe" : ""}${e.disabled ? " · not a dependency" : ""}${role ? ` · ${role}` : ""}`}</title>
                </path>
              );
            })}
            {graph.nodes.map(nodeEl)}
          </svg>
        </div>
      )}

      {view === "matrix" && (graph.nodes.length > MATRIX_LIMIT
        ? <p className="p-5 text-caption text-muted">The matrix shows up to {MATRIX_LIMIT} nodes. This graph has {graph.nodes.length}; use another view.</p>
        : <MatrixView graph={graph} edgeMarks={edgeMarks} nodeMarks={nodeMarks} selected={selected} onSelect={onSelect} showDisabled={showDisabled} />)}

      {view === "timeline" && <TimelineView edges={visibleEdges} edgeMarks={edgeMarks} />}
      {view === "table" && <TableView edges={visibleEdges} edgeMarks={edgeMarks} />}

      {roles.length > 0 && (
        <ul className="flex flex-wrap gap-x-4 gap-y-1 border-t border-line p-3 text-micro text-muted" aria-label="Legend">
          {roles.map((r) => <li key={r} className="flex items-center gap-1.5"><span className="inline-block size-2.5 rounded-full" style={{ background: VAR[toneFor(r) ?? "muted"] }} />{r}</li>)}
          <li className="flex items-center gap-1.5"><span className="inline-block w-5 border-t-2 border-dashed border-muted" />maybe / cut</li>
        </ul>
      )}

      {sel && (
        <div className="border-t border-line p-4" aria-live="polite">
          <h3 className="text-body font-semibold text-ink">{sel.label} <span className="font-mono text-micro font-normal text-muted">{sel.id} · {sel.type}</span></h3>
          {Object.keys(sel.props).length > 0 && <dl className="mt-2 grid gap-x-6 gap-y-1 text-caption sm:grid-cols-2">{Object.entries(sel.props).map(([k, v]) => <div key={k} className="flex justify-between gap-3"><dt className="text-muted">{k}</dt><dd className="break-all font-medium">{String(v)}</dd></div>)}</dl>}
          <p className="mt-3 text-micro text-muted">Links</p>
          <ul className="mt-1 flex flex-wrap gap-2 text-caption">
            {graph.edges.filter((e) => e.source === sel.id || e.target === sel.id).slice(0, 24).map((e, i) => {
              const other = e.source === sel.id ? e.target : e.source;
              return <li key={i}><button type="button" className="min-h-9 border border-line px-2 hover:bg-surface-2" onClick={() => onSelect?.(other)}>{e.source === sel.id ? "→" : "←"} {e.rel} {short(byId.get(other)?.label ?? other, 24)}</button></li>;
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

function MatrixView({ graph, nodeMarks, edgeMarks, selected, onSelect, showDisabled }: {
  graph: LabGraph; nodeMarks: Record<string, string>; edgeMarks: Record<string, string>; selected?: string | null; onSelect?: (id: string) => void; showDisabled: boolean;
}) {
  const ids = graph.nodes.map((n) => n.id).sort();
  const cell = new Map<string, { e: LabEdge; i: number }>();
  graph.edges.forEach((e, i) => { if (showDisabled || !e.disabled) cell.set(`${e.source}\u0000${e.target}`, { e, i }); });
  return (
    <div className="max-h-[640px] overflow-auto p-3" role="region" aria-label="Adjacency matrix">
      <table className="border-collapse text-micro">
        <thead><tr><th className="sticky left-0 bg-surface" scope="col"><span className="sr-only">From \ To</span></th>
          {ids.map((id) => <th key={id} scope="col" className="p-0.5 font-normal text-muted" style={{ writingMode: "vertical-rl" }}><button type="button" onClick={() => onSelect?.(id)} className={selected === id ? "font-semibold text-ink" : ""}>{short(graph.nodes.find((n) => n.id === id)?.label ?? id, 16)}</button></th>)}</tr></thead>
        <tbody>{ids.map((row) => <tr key={row}>
          <th scope="row" className="sticky left-0 bg-surface pr-2 text-right font-normal"><button type="button" onClick={() => onSelect?.(row)} className={selected === row ? "font-semibold text-ink" : "text-muted"}>{short(graph.nodes.find((n) => n.id === row)?.label ?? row, 18)}</button></th>
          {ids.map((col) => {
            const hit = cell.get(`${row}\u0000${col}`);
            const tone = hit ? toneFor(edgeMarks[String(hit.i)]) ?? "muted" : null;
            return <td key={col} className="border border-line p-0" style={{ width: 18, height: 18, background: tone ? VAR[tone] : nodeMarks[row] === "hidden" ? "transparent" : "transparent", opacity: hit?.e.disabled ? 0.35 : 1 }}
              title={hit ? `${row} —${hit.e.rel}→ ${col} · weight ${hit.e.weight}` : undefined}>{hit ? <span className="sr-only">{hit.e.rel}</span> : null}</td>;
          })}
        </tr>)}</tbody>
      </table>
    </div>
  );
}

function TimelineView({ edges, edgeMarks }: { edges: { e: LabEdge; i: number }[]; edgeMarks: Record<string, string> }) {
  const dated = edges.filter(({ e }) => e.at || e.until).sort((a, b) => (a.e.at ?? "").localeCompare(b.e.at ?? "")).slice(0, 80);
  const times = dated.flatMap(({ e }) => [e.at, e.until]).filter(Boolean).map((s) => Date.parse(s as string));
  const [lo, hi] = [Math.min(...times), Math.max(...times)];
  const span = Math.max(hi - lo, 1);
  const pct = (s: string | null, fallback: number) => (s ? ((Date.parse(s) - lo) / span) * 100 : fallback);
  if (!dated.length) return <p className="p-5 text-caption text-muted">No relationship carries a validity date.</p>;
  return (
    <div className="max-h-[640px] overflow-auto p-3" role="region" aria-label="Relationship validity timeline">
      <div className="mb-2 flex justify-between text-micro text-muted"><span>{fmtDate(new Date(lo).toISOString())}</span><span>{fmtDate(new Date(hi).toISOString())}</span></div>
      <ol className="space-y-1.5">
        {dated.map(({ e, i }) => {
          const start = pct(e.at, 0), end = pct(e.until, 100);
          const tone = toneFor(edgeMarks[String(i)]) ?? "info";
          return (
            <li key={i} className="grid grid-cols-[minmax(0,15rem)_1fr] items-center gap-3 text-micro">
              <span className="truncate text-muted" title={`${e.source} ${e.rel} ${e.target}`}>{short(e.source, 18)} <span className="text-ink">{e.rel}</span> {short(e.target, 18)}</span>
              <span className="relative block h-3 border border-line bg-surface-2" aria-label={`${fmtDate(e.at)} to ${e.until ? fmtDate(e.until) : "open"}`}>
                <span className="absolute inset-y-0" style={{ left: `${start}%`, width: `${Math.max(end - start, 1.2)}%`, background: VAR[tone], opacity: edgeMarks[String(i)] === "hidden" ? 0.25 : 0.85 }} />
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function TableView({ edges, edgeMarks }: { edges: { e: LabEdge; i: number }[]; edgeMarks: Record<string, string> }) {
  return (
    <div className="max-h-[640px] overflow-auto" role="region" aria-label="Links table">
      <table className="w-full text-left text-caption">
        <thead className="sticky top-0 bg-surface-2 text-muted"><tr>{["From", "Relation", "To", "Weight", "Certainty", "Valid from", "Valid until", "Mark"].map((h) => <th key={h} scope="col" className="p-2 font-semibold">{h}</th>)}</tr></thead>
        <tbody>{edges.slice(0, 250).map(({ e, i }) => <tr key={i} className="border-t border-line">
          <td className="p-2">{e.source}</td><td className="p-2 font-mono text-micro">{e.rel}{e.disabled ? " (context)" : ""}</td><td className="p-2">{e.target}</td>
          <td className="p-2">{e.weight}</td><td className="p-2">{e.certainty}</td><td className="p-2">{fmtDate(e.at)}</td><td className="p-2">{fmtDate(e.until)}</td>
          <td className="p-2">{edgeMarks[String(i)] ?? ""}</td></tr>)}</tbody>
      </table>
      {edges.length > 250 && <p className="p-3 text-micro text-muted">Showing the first 250 of {edges.length} links.</p>}
    </div>
  );
}
