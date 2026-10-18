"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useState } from "react";
import { InteractiveGlobe } from "@/components/features/greenchain/InteractiveGlobe";
import { GraphViews } from "@/components/graph-views";
import { Button, StatusBadge } from "@/components/ui";
import { apiResultToScenario } from "@/lib/greenchain/api-to-scenario";
import type { ManufacturerResult, TransportMode } from "@/lib/greenchain/api";
import type { ScenarioSearchCsv } from "@/lib/greenchain/csv-to-search";
import {
  applyScoringLens, DEFAULT_SCORING_WEIGHTS, normalizeWeights, TRANSPORT_MODE_LABELS, TRANSPORT_MODES, WEIGHT_KEYS, WEIGHT_LABELS,
} from "@/lib/greenchain/scoring-lens";
import type { SupplyScenarioSelectableNodeId } from "@/lib/greenchain/supply-chain-scenario";
import {
  greenchainDemo, greenchainHealth, greenchainPersist, greenchainScore, greenchainWhatIf,
  type GreenchainDemo, type GreenchainHealth, type GreenchainWhatIf,
} from "@/lib/lab-api";

// CesiumJS is large and WebGL-only, so it loads on demand; the SVG globe remains as the no-WebGL fallback.
const CesiumGlobe = dynamic(() => import("@/components/features/greenchain/CesiumGlobe").then((m) => m.CesiumGlobe), {
  ssr: false,
  loading: () => <p role="status" className="grid size-full place-items-center text-caption text-muted">Loading satellite globe…</p>,
});

const COMPONENT = "Corrugated packaging";
const incumbent = (demo: GreenchainDemo) => demo.results.find((r) => (r as { is_current?: boolean }).is_current) as ManufacturerResult | undefined;

/** GreenChain procurement intelligence inside AIDTRACE. Scores come from the migrated XGBoost quantile models and
 *  public reference data on the server; the globe and the instant re-ranking lens are GreenChain's own code. */
export function GreenChainWorkspace() {
  const [demo, setDemo] = useState<GreenchainDemo | null>(null);
  const [health, setHealth] = useState<GreenchainHealth | null>(null);
  const [mode, setMode] = useState<TransportMode>("sea");
  const [weights, setWeights] = useState(DEFAULT_SCORING_WEIGHTS);
  const [selected, setSelected] = useState<SupplyScenarioSelectableNodeId | null>(null);
  const [hovered, setHovered] = useState<SupplyScenarioSelectableNodeId | null>(null);
  const [server, setServer] = useState<{ name: string; rank: number }[] | null>(null);
  const [whatIf, setWhatIf] = useState<GreenchainWhatIf | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [globeFallback, setGlobeFallback] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    Promise.all([greenchainDemo("sea"), greenchainHealth()])
      .then(([d, h]) => { if (live) { setDemo(d); setHealth(h); } })
      .catch((e: unknown) => { if (live) setError(e instanceof Error ? e.message : "GreenChain could not load."); });
    return () => { live = false; };
  }, []);

  const base = useMemo(() => {
    if (!demo) return null;
    const current = incumbent(demo);
    const csv: ScenarioSearchCsv = {
      product: demo.product, destination: demo.destination, quantity: 10000, unit: "units", targetCount: null, transportMode: "sea",
      components: [{ component: COMPONENT, currentManufacturer: current?.name ?? "Incumbent", currentCountry: current?.country ?? "CN", currentCity: null,
        currentCertifications: current?.certifications ?? [], currentDisclosureStatus: "none", currentRenewablePct: null, currentRevenueUsdM: null, currentWebsite: null }],
    };
    return apiResultToScenario({ product: demo.product, destination: demo.destination, transport_mode: "sea", countries: [], duration_seconds: 0,
      count: demo.results.length, results: demo.results as unknown as ManufacturerResult[] }, csv);
  }, [demo]);

  const scenario = useMemo(() => (base ? applyScoringLens(base, { transportMode: mode, weights }) : null), [base, mode, weights]);
  const ranked = useMemo(() => (scenario ? [...scenario.manufacturers].sort((a, b) => a.ecoScore - b.ecoScore || a.name.localeCompare(b.name)) : []), [scenario]);
  const best = useMemo(() => (ranked[0] ? { [ranked[0].componentId]: ranked[0].id } : {}), [ranked]);
  const visible = useMemo(() => Object.fromEntries((scenario?.components ?? []).map((c) => [c.id, true])), [scenario]);
  const normalized = normalizeWeights(weights);

  const verifyOnServer = useCallback(async () => {
    if (!demo) return;
    setBusy(true); setError(null);
    try { setServer((await greenchainScore(demo.results, mode, normalized as unknown as Record<string, number>)).results); }
    catch (e) { setError(e instanceof Error ? e.message : "Server scoring failed."); }
    finally { setBusy(false); }
  }, [demo, mode, normalized]);

  async function removeSupplier(name: string) {
    setBusy(true); setError(null);
    try { setWhatIf(await greenchainWhatIf(name, mode)); } catch (e) { setError(e instanceof Error ? e.message : "What-if failed."); }
    finally { setBusy(false); }
  }
  async function persist() {
    if (!demo) return;
    setBusy(true); setError(null);
    try { const r = await greenchainPersist(demo.results); setSaved(`Saved ${r.nodes} nodes and ${r.edges} relationships to this site's FalkorDB graph.`); }
    catch (e) { setError(e instanceof Error ? e.message : "Persisting failed."); }
    finally { setBusy(false); }
  }

  // Globe and graph share one selection: a supplier is the same entity in both, matched by name.
  const graphSelected = useMemo(() => {
    const m = scenario?.manufacturers.find((x) => x.id === selected);
    return m ? demo?.graph.nodes.find((n) => n.type === "Supplier" && n.label === m.name)?.id ?? null : null;
  }, [scenario, selected, demo]);
  const selectFromGraph = useCallback((id: string) => {
    const node = demo?.graph.nodes.find((n) => n.id === id);
    const m = node?.type === "Supplier" ? scenario?.manufacturers.find((x) => x.name === node.label) : undefined;
    if (m) setSelected(m.id);
  }, [demo, scenario]);

  const top = ranked[0];
  const serverTop = server?.[0]?.name;
  const clientOrder = ranked.map((r) => r.name).join("|");
  const serverOrder = server ? [...server].sort((a, b) => a.rank - b.rank).map((r) => r.name).join("|") : null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-title font-semibold">GreenChain · sustainable procurement intelligence</h2>
          <p className="mt-1 max-w-3xl text-caption leading-relaxed text-muted">Compare sourcing options by modelled emissions, transport mode, certifications and climate risk. Estimates are modelled industry intensities with uncertainty intervals, not factory-specific measurements.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <StatusBadge tone="caution">Illustrative candidates</StatusBadge>
          {health && <StatusBadge tone={health.ml_models && health.reference_data ? "verified" : "danger"}>{health.ml_models && health.reference_data ? "ML models + reference data loaded" : "models or data missing"}</StatusBadge>}
          {health && <StatusBadge tone="neutral">live discovery: {health.live_discovery.toLowerCase().replace("_", " ")}</StatusBadge>}
        </div>
      </div>
      {demo && <p className="border-l-2 border-caution bg-surface p-3 text-micro text-muted">{demo.notice}</p>}
      {error && <p role="alert" className="border-l-2 border-danger bg-surface p-3 text-caption text-danger">{error}</p>}

      {scenario && (
        <div className="grid gap-4 xl:grid-cols-[300px_minmax(0,1fr)]">
          <section className="space-y-4" aria-label="Scoring controls">
            <div className="border border-line bg-surface p-4">
              <h3 className="text-body font-semibold">Transport mode</h3>
              <div className="mt-2 flex flex-wrap gap-2" role="group" aria-label="Transport mode">
                {TRANSPORT_MODES.map((m) => <Button key={m} aria-pressed={mode === m} variant={mode === m ? "primary" : "ghost"} onClick={() => { setMode(m); setServer(null); }}>{TRANSPORT_MODE_LABELS[m]}</Button>)}
              </div>
              <h3 className="mt-4 text-body font-semibold">Scoring weights</h3>
              <ul className="mt-2 space-y-3">{WEIGHT_KEYS.map((k) => (
                <li key={k}><label className="block text-caption" htmlFor={`w-${k}`}>{WEIGHT_LABELS[k]} <span className="text-muted">{Math.round(normalized[k] * 100)}%</span></label>
                  <input id={`w-${k}`} type="range" min={0} max={100} value={Math.round(weights[k] * 100)} className="w-full"
                    onChange={(e) => { setWeights({ ...weights, [k]: Number(e.target.value) / 100 }); setServer(null); }} /></li>
              ))}</ul>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button variant="ghost" onClick={() => { setWeights(DEFAULT_SCORING_WEIGHTS); setServer(null); }}>Reset weights</Button>
                <Button variant="primary" disabled={busy} onClick={() => void verifyOnServer()}>Verify on server</Button>
              </div>
              {serverOrder && <p role="status" className="mt-3 text-micro text-muted">Server ranking (XGBoost pipeline): <strong className="text-ink">{serverTop}</strong> first. {serverOrder === clientOrder ? "Matches the instant lens." : "Order differs from the instant lens: the server result is authoritative."}</p>}
            </div>
            <div className="border border-line bg-surface p-4">
              <h3 className="text-body font-semibold">What if a supplier leaves?</h3>
              <ul className="mt-2 flex flex-wrap gap-2">{ranked.map((m) => <li key={m.id}><Button variant="ghost" disabled={busy} onClick={() => void removeSupplier(m.name)}>{m.name.replace("Illustrative ", "")}</Button></li>)}</ul>
              {whatIf && <p role="status" className="mt-3 text-caption">Without <strong>{whatIf.removed}</strong>: top choice {whatIf.recommendation_changes ? <>changes from <strong>{whatIf.top_before}</strong> to <strong>{whatIf.top_after}</strong></> : <>stays <strong>{whatIf.top_after}</strong></>}; {whatIf.rank_changes.length} rank change(s).</p>}
            </div>
            <div className="border border-line bg-surface p-4">
              <h3 className="text-body font-semibold">Decision memory</h3>
              <p className="mt-1 text-micro text-muted">Saves suppliers, certifications, estimates and the datasets they rest on as a graph, so a changed source can be traced to the decision.</p>
              <Button className="mt-2" variant="ghost" disabled={busy} onClick={() => void persist()}>Save to FalkorDB</Button>
              {saved && <p role="status" className="mt-2 text-micro text-muted">{saved}</p>}
            </div>
          </section>

          <section className="min-w-0 space-y-4" aria-label="Globe and comparison">
            <div className="h-[520px] overflow-hidden border border-line bg-surface-2" aria-label="Interactive globe of supplier locations">
              {globeFallback ? (
                <div className="flex size-full flex-col">
                  <p role="status" className="border-b border-line bg-surface p-2 text-micro text-muted">{globeFallback} Showing the schematic globe instead; the supplier table below has the same information.</p>
                  <div className="min-h-0 flex-1">
                    <InteractiveGlobe scenario={scenario} bestEcoManufacturerByComponent={best} pinnedManufacturerByComponent={{}} routeVisibleByComponent={visible}
                      selectedNodeId={selected} hoveredNodeId={hovered} onHoverNode={setHovered} onSelectNode={setSelected} className="size-full" />
                  </div>
                </div>
              ) : (
                <CesiumGlobe scenario={scenario} bestEcoManufacturerByComponent={best} routeVisibleByComponent={visible}
                  selectedNodeId={selected} hoveredNodeId={hovered} onHoverNode={setHovered} onSelectNode={setSelected}
                  onUnsupported={setGlobeFallback} className="size-full" />
              )}
            </div>
            <div className="overflow-x-auto border border-line bg-surface">
              <table className="w-full text-left text-caption">
                <caption className="p-3 text-left text-body font-semibold">Supplier comparison <span className="font-normal text-muted">(lower environmental score is better)</span></caption>
                <thead className="bg-surface-2 text-muted"><tr>{["#", "Supplier", "Country", "Eco score", "Emissions q10–q50–q90 (tCO2e)", `Transport (${mode})`, "Certifications (claimed)"].map((h) => <th key={h} scope="col" className="p-2 font-semibold">{h}</th>)}</tr></thead>
                <tbody>{ranked.map((m, i) => (
                  <tr key={m.id} className={`border-t border-line ${selected === m.id ? "bg-surface-2" : ""}`} onClick={() => setSelected(m.id)}>
                    <td className="p-2">{i + 1}</td><th scope="row" className="p-2 font-medium">{m.name}{m.isCurrent && <span className="ml-2 text-micro font-normal text-muted">incumbent</span>}</th>
                    <td className="p-2">{m.location.countryCode}</td><td className="p-2">{m.ecoScore.toFixed(0)}</td>
                    <td className="p-2 font-mono text-micro">{m.manufacturingEmissionsTco2e.q10.toFixed(0)} – {m.manufacturingEmissionsTco2e.q50.toFixed(0)} – {m.manufacturingEmissionsTco2e.q90.toFixed(0)}</td>
                    <td className="p-2">{m.transportEmissionsTco2e.toFixed(2)}</td><td className="p-2 text-muted">{m.certifications.join(", ") || "none"}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
            {top && <p className="border border-line bg-surface p-4 text-caption leading-relaxed"><strong>Summary from the scores (not a language-model memo):</strong> under the current weights and {TRANSPORT_MODE_LABELS[mode].toLowerCase()} transport, <strong>{top.name}</strong> ({top.location.country}) ranks first with a modelled manufacturing estimate of {top.manufacturingEmissionsTco2e.q50.toFixed(0)} tCO2e (80% interval {top.manufacturingEmissionsTco2e.q10.toFixed(0)}–{top.manufacturingEmissionsTco2e.q90.toFixed(0)}). Estimates rest on USEEIO, Ember, GLEC and ND-GAIN reference data; certifications are unverified claims. Confirm with supplier evidence before any purchase.</p>}
            {demo && <GraphViews graph={demo.graph} selected={graphSelected} onSelect={selectFromGraph} />}
          </section>
        </div>
      )}
    </div>
  );
}
