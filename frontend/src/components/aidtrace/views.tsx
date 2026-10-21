"use client";

// The four switchable views of the AIDTRACE centre. They share one selection and one data object owned by the workspace, so switching views never
// reloads data or loses the active investigation.
import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { InteractiveGlobe } from "@/components/features/greenchain/InteractiveGlobe";
import { GraphViews, TYPE_TONES, TYPE_GLYPHS, type GraphMarks } from "@/components/graph-views";
import { Button, StatusBadge } from "@/components/ui";
import type { LabGraph } from "@/lib/graph-layout";
import type { SupplyScenarioSelectableNodeId } from "@/lib/greenchain/supply-chain-scenario";
import { chainOf, isUnsafe, LINEAGE_COLUMNS, LINEAGE_LABELS, type LineageNode } from "@/lib/aidtrace-lineage";
import { getSiteGraph, runSiteCypher, type CypherQueryResult } from "@/lib/lab-api";
import type { AidtraceData, Selection } from "./data";

const CesiumGlobe = dynamic(() => import("@/components/features/greenchain/CesiumGlobe").then((m) => m.CesiumGlobe), {
  ssr: false,
  loading: () => <p role="status" className="grid size-full place-items-center text-caption text-muted">Loading the globe…</p>,
});

type Tone = "verified" | "danger" | "caution" | "neutral";
export const toneOf = (status: string): Tone => (isUnsafe(status) ? "danger" : /VALID|ACTIVE|APPROVED|ELIGIBLE/i.test(status) ? "verified" : "caution");
const plain = (name: string) => name.replace("Illustrative ", "");
const when = (iso: string | undefined) => (iso ? iso.slice(0, 16).replace("T", " ") : "—");
const message = (e: unknown) => (e instanceof Error ? e.message : "The request failed.");

export interface ViewProps { data: AidtraceData; selection: Selection; onSelect: (s: Selection) => void }

function Empty({ children }: { children: React.ReactNode }) {
  return <div className="grid size-full place-items-center p-8 text-center text-caption text-muted"><div className="max-w-sm space-y-3">{children}</div></div>;
}

// ---- Globe -----------------------------------------------------------------------------------------------------------------------------

/** `recommendedName` is the supplier the graph currently recommends; `banner` is a one-line backend-derived result shown over the globe. */
export function GlobeView({ data, selection, onSelect, recommendedName, banner }: ViewProps & { recommendedName?: string | null; banner?: string | null }) {
  const [hovered, setHovered] = useState<SupplyScenarioSelectableNodeId | null>(null);
  const [fallback, setFallback] = useState<string | null>(null);
  const scenario = data.scenario;
  const ranked = useMemo(() => (scenario ? [...scenario.manufacturers].sort((a, b) => a.ecoScore - b.ecoScore) : []), [scenario]);
  const best = useMemo(() => {
    const target = recommendedName ? ranked.find((m) => m.name === recommendedName) : ranked[0];
    return target ? { [target.componentId]: target.id } : {};
  }, [ranked, recommendedName]);
  const visible = useMemo(() => Object.fromEntries((scenario?.components ?? []).map((c) => [c.id, true])), [scenario]);
  if (data.errors.supply) return <Empty><p role="alert" className="text-danger">{data.errors.supply}</p><p>The supplier scenario could not be loaded. Graph, Lineage and Timeline still work.</p></Empty>;
  if (!scenario) return <Empty><p role="status">Loading the supply network…</p></Empty>;
  const selectedId = selection?.kind === "supplier" ? (selection.id as SupplyScenarioSelectableNodeId) : null;
  const pick = (id: SupplyScenarioSelectableNodeId | null) => {
    const m = id ? scenario.manufacturers.find((x) => x.id === id) : undefined;
    onSelect(m ? { kind: "supplier", id: m.id, label: m.name } : null);
  };
  const globeProps = { scenario, bestEcoManufacturerByComponent: best, routeVisibleByComponent: visible, selectedNodeId: selectedId, hoveredNodeId: hovered, onHoverNode: setHovered, onSelectNode: pick, className: "size-full" };
  return (
    <div className="relative size-full" aria-label="Interactive globe of supplier locations" data-testid="aidtrace-globe">
      {fallback ? (
        <div className="flex size-full flex-col">
          <p role="status" className="border-b border-line bg-surface p-2 text-micro text-muted">Degraded view: {fallback} Showing the schematic 2D globe, not CesiumJS.</p>
          <div className="min-h-0 flex-1"><InteractiveGlobe {...globeProps} pinnedManufacturerByComponent={{}} /></div>
        </div>
      ) : <CesiumGlobe {...globeProps} onUnsupported={setFallback} />}
      {banner && <p role="status" className="pointer-events-none absolute left-1/2 top-12 z-20 max-w-[80%] -translate-x-1/2 border border-line bg-surface px-3 py-1.5 text-caption font-medium text-ink shadow-sm">{banner}</p>}
    </div>
  );
}

// ---- Graph -----------------------------------------------------------------------------------------------------------------------------

const CYPHER_IDENTIFIER = /^[A-Za-z_][A-Za-z0-9_]*$/;

/** Console presets built from what the persisted graph really holds. Only plain identifiers become labels or relationship types, so a preset never names a
 *  record type the graph lacks and never breaks out of its backticks. */
export function cypherPresets(graph: LabGraph | null): { label: string; query: string }[] {
  const presets = [
    { label: "Node counts", query: "MATCH (n) RETURN labels(n)[0] AS type, count(n) AS cnt ORDER BY cnt DESC" },
    { label: "Relationship stats", query: "MATCH ()-[r]->() RETURN type(r) AS relationship, count(r) AS cnt ORDER BY cnt DESC" },
  ];
  if (!graph) return presets;
  const mostCommon = (values: unknown[]) => {
    const counts = new Map<string, number>();
    for (const v of values) if (typeof v === "string" && CYPHER_IDENTIFIER.test(v)) counts.set(v, (counts.get(v) ?? 0) + 1);
    return [...counts].sort((a, b) => b[1] - a[1]).slice(0, 2).map(([v]) => v);
  };
  for (const type of mostCommon(graph.nodes.map((n) => n.type))) {
    presets.push({ label: `Sample ${type}`, query: `MATCH (n:\`${type}\`) RETURN n.id AS id, labels(n)[0] AS type LIMIT 10` });
  }
  for (const rel of mostCommon(graph.edges.map((e) => e.rel))) {
    presets.push({ label: `${rel} links`, query: `MATCH (a)-[r:\`${rel}\`]->(b) RETURN a.id AS source, type(r) AS relationship, b.id AS target LIMIT 10` });
  }
  return presets;
}

export function GraphView({ data, selection, onSelect }: ViewProps) {
  const [source, setSource] = useState<"scenario" | "site">("site");
  const [fetched, setFetched] = useState<AidtraceData["site"]>(null);
  const [siteError, setSiteError] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<string | null>(null);
  const [showConsole, setShowConsole] = useState(false);
  const [cypherQuery, setCypherQuery] = useState("MATCH (n) RETURN labels(n)[0] AS type, count(n) AS cnt ORDER BY cnt DESC");
  const [cypherLoading, setCypherLoading] = useState(false);
  const [cypherResult, setCypherResult] = useState<CypherQueryResult | null>(null);
  const [cypherError, setCypherError] = useState<string | null>(null);

  const site = data.site ?? fetched;
  useEffect(() => {
    if (source !== "site" || site) return;
    let live = true;
    getSiteGraph()
      .then((r) => { if (live) setFetched(r.data); })
      .catch((e: unknown) => { if (live) { setSiteError(message(e)); setSource("scenario"); } });
    return () => { live = false; };
  }, [source, site]);

  const usingSite = source === "site" && site && !site.empty;
  const rawGraph: LabGraph | null = usingSite ? site.graph : data.demo?.graph ?? null;

  // Filter or highlight by node type if filter selected
  const graph: LabGraph | null = useMemo(() => {
    if (!rawGraph) return null;
    if (!typeFilter) return rawGraph;
    const matchIds = new Set(rawGraph.nodes.filter((n) => n.type === typeFilter).map((n) => n.id));
    // include immediate 1-hop connected neighbors for context
    const connectedIds = new Set(matchIds);
    rawGraph.edges.forEach((e) => {
      if (matchIds.has(e.source)) connectedIds.add(e.target);
      if (matchIds.has(e.target)) connectedIds.add(e.source);
    });
    return {
      nodes: rawGraph.nodes.filter((n) => connectedIds.has(n.id)),
      edges: rawGraph.edges.filter((e) => connectedIds.has(e.source) && connectedIds.has(e.target)),
    };
  }, [rawGraph, typeFilter]);

  const falkor = site?.falkordb;
  // Presets follow the persisted graph, because the console queries that graph and not the scenario sandbox.
  const presets = useMemo(() => cypherPresets(site?.graph ?? null), [site]);

  // Compute node type distribution
  const typeCounts = useMemo(() => {
    if (!rawGraph) return [];
    const counts: Record<string, number> = {};
    rawGraph.nodes.forEach((n) => {
      counts[n.type] = (counts[n.type] ?? 0) + 1;
    });
    return Object.entries(counts).sort((a, b) => b[1] - a[1]);
  }, [rawGraph]);

  // Compute marks so nodes have distinct type tones, badges, and status colors
  const marks = useMemo<GraphMarks>(() => {
    if (!graph) return {};
    const node_marks: Record<string, string> = {};
    const node_badges: Record<string, string> = {};
    graph.nodes.forEach((n) => {
      const st = String(n.props?.status ?? n.props?.verification_status ?? "");
      if (st === "INVALIDATED") {
        node_marks[n.id] = "danger";
      } else if (st === "SUPERSEDED" || st === "STALE") {
        node_marks[n.id] = "caution";
      } else if (st === "ACTIVE" || st === "VALID" || st === "VERIFIED") {
        node_marks[n.id] = "verified";
      } else if (typeFilter && n.type === typeFilter) {
        node_marks[n.id] = "accent";
      } else {
        node_marks[n.id] = TYPE_TONES[n.type] ?? "muted";
      }
      node_badges[n.id] = TYPE_GLYPHS[n.type] ?? n.type.slice(0, 3).toUpperCase();
    });
    return { node_marks, node_badges };
  }, [graph, typeFilter]);

  async function executeCypher(q: string) {
    setCypherLoading(true);
    setCypherError(null);
    try {
      const res = await runSiteCypher(q);
      setCypherResult(res);
    } catch (e) {
      setCypherError(message(e));
      setCypherResult(null);
    } finally {
      setCypherLoading(false);
    }
  }

  if (data.errors.supply && !graph) return <Empty><p role="alert" className="text-danger">{data.errors.supply}</p></Empty>;
  if (!graph) return <Empty><p role="status">Reading FalkorDB graph…</p></Empty>;

  const supplierNode = selection?.kind === "supplier" ? graph.nodes.find((n) => n.type === "Supplier" && n.label === selection.label)?.id ?? null : null;
  const selectedId = selection && graph.nodes.some((n) => n.id === selection.id) ? selection.id : supplierNode;

  function pick(id: string) {
    const node = graph?.nodes.find((n) => n.id === id);
    if (!node) return;
    const m = node.type === "Supplier" ? data.scenario?.manufacturers.find((x) => x.name === node.label) : undefined;
    onSelect(m ? { kind: "supplier", id: m.id, label: m.name } : { kind: "node", id: node.id, label: node.label });
  }

  return (
    <div className="flex size-full flex-col overflow-y-auto p-3" data-testid="aidtrace-graph-view">
      {/* FalkorDB Live Provenance Banner */}
      <div className="mb-3 rounded border border-line bg-surface p-3 shadow-xs">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-2.5">
          <div className="flex items-center gap-2">
            <span className={`inline-block size-2.5 rounded-full ${usingSite ? "bg-verified" : "bg-caution"}`} aria-hidden="true" />
            <span className="text-caption font-semibold text-ink">
              {usingSite ? "FalkorDB site graph" : "Scenario graph"}: <span className="font-mono text-accent">{usingSite ? falkor?.graph_name ?? "Current site" : "Illustrative sandbox"}</span>
            </span>
            {usingSite && <StatusBadge tone="verified">Live site data</StatusBadge>}
            <StatusBadge tone="info">Graph traversal</StatusBadge>
          </div>
          <div className="flex items-center gap-2 text-micro">
            <Button
              aria-pressed={source === "site"}
              variant={source === "site" ? "primary" : "ghost"}
              onClick={() => setSource("site")}
            >
              FalkorDB Live Graph
            </Button>
            <Button
              aria-pressed={source === "scenario"}
              variant={source === "scenario" ? "primary" : "ghost"}
              onClick={() => setSource("scenario")}
            >
              Scenario Sandbox
            </Button>
            <Button
              variant={showConsole ? "primary" : "ghost"}
              onClick={() => setShowConsole(!showConsole)}
              title="Open the read-only Cypher console for your site graph"
            >
              ⚡ {showConsole ? "Close Cypher Console" : "Live Cypher Console"}
            </Button>
          </div>
        </div>

        {/* Live Metrics & Filter Chips */}
        <div className="mt-2.5 flex flex-wrap items-center justify-between gap-2 text-micro">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-medium text-muted">Entity Filters:</span>
            <button
              type="button"
              onClick={() => setTypeFilter(null)}
              className={`rounded px-2 py-0.5 text-micro transition-colors ${!typeFilter ? "bg-ink font-semibold text-canvas" : "border border-line bg-surface hover:bg-surface-2"}`}
            >
              All ({rawGraph?.nodes.length ?? 0})
            </button>
            {typeCounts.map(([t, count]) => (
              <button
                key={t}
                type="button"
                onClick={() => setTypeFilter(typeFilter === t ? null : t)}
                className={`flex items-center gap-1 rounded border px-2 py-0.5 text-micro transition-colors ${typeFilter === t ? "border-ink bg-ink font-semibold text-canvas" : "border-line bg-surface hover:bg-surface-2"}`}
              >
                <span>{t}</span>
                <span className="font-mono text-muted text-[10px]">({count})</span>
              </button>
            ))}
          </div>
          <span className="font-mono text-muted">
            {graph.nodes.length} nodes · {graph.edges.length} edges
          </span>
        </div>

        {/* Expandable FalkorDB Cypher Console */}
        {showConsole && (
          <div className="mt-3 rounded border border-line bg-canvas p-3">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <span className="text-caption font-semibold text-ink">Read-only Cypher on your site graph</span>
              <div className="flex flex-wrap items-center gap-1">
                {presets.map((p) => (
                  <button
                    key={p.label}
                    type="button"
                    onClick={() => { setCypherQuery(p.query); void executeCypher(p.query); }}
                    className="rounded border border-line bg-surface px-2 py-0.5 text-[11px] text-muted hover:border-accent hover:text-ink"
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex gap-2">
              <input
                value={cypherQuery}
                onChange={(e) => setCypherQuery(e.target.value)}
                placeholder="MATCH (n) RETURN n LIMIT 10"
                className="h-9 flex-1 rounded border border-line bg-surface px-2.5 font-mono text-micro text-ink placeholder:text-muted focus-visible:outline-2 focus-visible:outline-accent"
              />
              <Button
                variant="primary"
                disabled={cypherLoading || !cypherQuery.trim()}
                onClick={() => void executeCypher(cypherQuery)}
              >
                {cypherLoading ? "Running…" : "Run Cypher"}
              </Button>
            </div>
            {cypherError && (
              <p role="alert" className="mt-2 text-micro text-danger">{cypherError}</p>
            )}
            {cypherResult && (
              <div className="mt-2 max-h-48 overflow-auto rounded border border-line bg-surface p-2 text-micro">
                <div className="mb-1.5 flex items-center justify-between text-muted">
                  <span>Returned {cypherResult.row_count} rows across {cypherResult.header.length} columns</span>
                  <span className="font-mono font-medium text-verified">⏱ {cypherResult.run_time_ms} ms (GraphBLAS)</span>
                </div>
                <table className="w-full text-left font-mono text-[11px]">
                  <thead>
                    <tr className="border-b border-line text-muted">
                      {cypherResult.header.map((h, i) => (
                        <th key={i} className="py-1 pr-3">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {cypherResult.rows.map((row, rIdx) => (
                      <tr key={rIdx} className="border-b border-line/40 hover:bg-surface-2">
                        {row.map((cell, cIdx) => (
                          <td key={cIdx} className="py-1 pr-3 text-ink">{String(cell ?? "null")}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {siteError && <p role="alert" className="mt-2 text-micro text-danger">{siteError}</p>}
      </div>

      <GraphViews graph={graph} marks={marks} selected={selectedId} onSelect={pick} />
    </div>
  );
}

// ---- Lineage ---------------------------------------------------------------------------------------------------------------------------

const CARD_W = 168, CARD_H = 58, GAP = 10, COL_GAP = 36, TOP = 34;

export function LineageView({ data, selection, onSelect }: ViewProps) {
  const lineage = data.lineage;
  if (data.errors.memory) return <Empty><p role="alert" className="text-danger">{data.errors.memory}</p><p>Lineage is read from the agent-memory graph.</p></Empty>;
  if (!lineage) return <Empty><p role="status">Reading the evidence graph…</p></Empty>;
  if (!lineage.nodes.length) return <Empty><p className="text-body font-semibold text-ink">No evidence lineage yet</p><p>Choose Investigate Risk. It records the supplier decision, so its sources, claims and memory appear here.</p></Empty>;
  const cols = LINEAGE_COLUMNS.map((kind) => lineage.nodes.filter((n) => n.kind === kind));
  const pos = new Map<string, { x: number; y: number }>();
  cols.forEach((nodes, c) => nodes.forEach((n, r) => pos.set(n.id, { x: c * (CARD_W + COL_GAP), y: TOP + r * (CARD_H + GAP) })));
  const width = LINEAGE_COLUMNS.length * CARD_W + (LINEAGE_COLUMNS.length - 1) * COL_GAP;
  const height = TOP + Math.max(1, ...cols.map((c) => c.length)) * (CARD_H + GAP);
  const active = selection && lineage.nodes.some((n) => n.id === selection.id) ? chainOf(lineage, selection.id) : null;
  const lit = (id: string) => !active || id === selection?.id || active.upstream.has(id) || active.downstream.has(id);
  const unsafeCount = lineage.nodes.filter((n) => isUnsafe(n.status)).length;
  const copies = lineage.sourceCount - lineage.originCount;
  return (
    <div className="flex size-full flex-col" data-testid="aidtrace-lineage">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-line px-4 py-2 text-micro text-muted">
        <span><strong className="text-ink">{lineage.sourceCount} source{lineage.sourceCount === 1 ? "" : "s"} → {lineage.originCount} origin{lineage.originCount === 1 ? "" : "s"}</strong>{copies > 0 && ` · ${copies} repeated citation${copies === 1 ? "" : "s"} counted once`}</span>
        <span>{lineage.nodes.length} records · {lineage.edges.length} dependencies read from FalkorDB</span>
        {unsafeCount > 0 && <StatusBadge tone="danger">{unsafeCount} stale or blocked</StatusBadge>}
        <span className="ml-auto">{lineage.hashedCount} of {lineage.sourceCount} sources carry a content hash; the rest are unverified. Paraphrased copies are not detected (experimental).</span>
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-4">
        <div className="relative" style={{ width, height }}>
          <svg className="absolute inset-0" width={width} height={height} aria-hidden="true">
            {lineage.edges.map((e) => {
              const a = pos.get(e.from), b = pos.get(e.to);
              if (!a || !b) return null;
              const x1 = a.x + CARD_W, y1 = a.y + CARD_H / 2, x2 = b.x, y2 = b.y + CARD_H / 2, mid = (x1 + x2) / 2;
              const on = !active || (lit(e.from) && lit(e.to));
              return <path key={`${e.from}>${e.to}`} d={`M${x1},${y1} C${mid},${y1} ${mid},${y2} ${x2},${y2}`} fill="none" stroke={on && active ? "var(--accent)" : "var(--line)"} strokeWidth={on && active ? 2 : 1} opacity={on ? 1 : 0.25} />;
            })}
          </svg>
          {LINEAGE_COLUMNS.map((kind, c) => <p key={kind} className="absolute text-micro font-semibold uppercase tracking-wider text-muted" style={{ left: c * (CARD_W + COL_GAP), top: 6 }}>{LINEAGE_LABELS[kind]} · {cols[c].length}</p>)}
          {lineage.nodes.map((n: LineageNode) => {
            const p = pos.get(n.id)!;
            const isSel = selection?.id === n.id;
            return (
              <button key={n.id} type="button" onClick={() => onSelect({ kind: n.kind, id: n.id, label: n.label })} aria-pressed={isSel} title={`${n.label} — ${n.trust ? n.trust + " · " : ""}${n.detail}`}
                className={`absolute overflow-hidden border bg-surface p-2 text-left transition-opacity hover:bg-surface-2 focus-visible:outline-2 focus-visible:outline-accent ${isSel ? "border-ink" : isUnsafe(n.status) ? "border-danger" : "border-line"} ${lit(n.id) ? "" : "opacity-30"}`}
                style={{ left: p.x, top: p.y, width: CARD_W, height: CARD_H }}>
                <span className="flex items-center justify-between gap-1"><span className="truncate text-caption font-medium text-ink">{n.label}</span><span className={`shrink-0 text-micro ${isUnsafe(n.status) ? "text-danger" : "text-muted"}`}>{n.status.toLowerCase()}</span></span>
                <span className="mt-0.5 block truncate text-micro text-muted">{n.trust ?? n.detail}</span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ---- Timeline --------------------------------------------------------------------------------------------------------------------------

export interface RunLogEntry { at: string; kind: string; text: string }

/** Source updates, agent operations, changes and approvals, all read from the graph, plus this session's workflow runs (labelled as such). */
export function TimelineView({ data, runs, onSelect }: { data: AidtraceData; runs: RunLogEntry[]; onSelect: (s: Selection) => void }) {
  const { snap, handoffs } = data;
  if (data.errors.memory) return <Empty><p role="alert" className="text-danger">{data.errors.memory}</p></Empty>;
  if (!snap) return <Empty><p role="status">Reading the audit history…</p></Empty>;
  type Ev = { at: string; kind: string; text: string; select?: Selection };
  const events: Ev[] = [
    ...runs.map((r) => ({ at: r.at, kind: "this session", text: r.text })),
    ...snap.changes.map((c) => ({ at: c.observed_at, kind: "source change", text: c.verdict && c.reason ? `${c.verdict}: ${c.reason}` : `Change recorded (${c.id})` })),
    ...snap.memories.filter((m) => m.recorded_at).map((m) => ({ at: m.recorded_at, kind: "memory", text: `${m.agent_id} recorded: ${m.summary}`, select: { kind: "memory" as const, id: m.id, label: m.summary } })),
    ...snap.approvals.map((a) => ({ at: a.approved_at, kind: "approval", text: `${a.approved_by} approved ${a.decision_id} (${a.approval_status.toLowerCase()})` })),
    ...handoffs.map((h) => ({ at: h.at, kind: "recall", text: `${h.recalled_by} recalled a memory by ${h.produced_by} — ${h.usable ? "usable" : "blocked as " + h.memory_status.toLowerCase()}` })),
  ].filter((e) => e.at).sort((a, b) => b.at.localeCompare(a.at)).slice(0, 80);
  if (!events.length) return <Empty><p className="text-body font-semibold text-ink">No activity yet</p><p>Run Investigate Risk or Update Evidence and each step is recorded here.</p></Empty>;
  return (
    <ol className="size-full space-y-1.5 overflow-y-auto p-4" aria-label="Activity timeline" data-testid="aidtrace-timeline">
      {events.map((e, i) => (
        <li key={`${e.at}-${i}`} className="grid grid-cols-[8.5rem_6.5rem_1fr] gap-3 border-b border-line pb-1.5 text-caption">
          <time className="font-mono text-micro text-muted">{when(e.at)}</time>
          <span className="text-micro uppercase tracking-wide text-muted">{e.kind}</span>
          {e.select ? <button type="button" onClick={() => onSelect(e.select!)} className="text-left underline-offset-2 hover:underline">{e.text}</button> : <span>{e.text}</span>}
        </li>
      ))}
    </ol>
  );
}

export { plain };
