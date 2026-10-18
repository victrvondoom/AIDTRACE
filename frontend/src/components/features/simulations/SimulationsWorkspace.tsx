"use client";

// Simulations: every tab runs a REAL computation on a copy of the inputs and says what it changed (nothing). Rankings come from
// GreenChain's scorer, impact previews from graph traversal on the site's FalkorDB graph, and domain comparisons from Resolve's
// retrieval. Counterfactual inputs are labelled as such.
import { useCallback, useEffect, useState } from "react";
import { Button, FilterTabs, StatusBadge } from "@/components/ui";
import { WEIGHT_KEYS, WEIGHT_LABELS, TRANSPORT_MODES, TRANSPORT_MODE_LABELS } from "@/lib/greenchain/scoring-lens";
import {
  greenchainDemo, greenchainScore, greenchainWhatIf, memoryImpactPreview, memoryPreviewRevision, memorySnapshot, platformSearch, platformStatus,
  type GcPreview, type GreenchainDemo, type GreenchainWhatIf, type ImpactPreview, type MemorySnapshot, type PlatformSearchHit,
} from "@/lib/lab-api";

type Tab = "removal" | "scoring" | "revision" | "impact" | "compare";
const PRESETS: Record<string, Record<string, number>> = {
  Balanced: { manufacturing: 0.4, transport: 0.25, grid_carbon: 0.2, certifications: 0.1, climate_risk: 0.05 },
  "Manufacturing first": { manufacturing: 0.7, transport: 0.1, grid_carbon: 0.1, certifications: 0.05, climate_risk: 0.05 },
  "Transport first": { manufacturing: 0.15, transport: 0.6, grid_carbon: 0.1, certifications: 0.05, climate_risk: 0.1 },
  "Climate risk first": { manufacturing: 0.2, transport: 0.15, grid_carbon: 0.15, certifications: 0.1, climate_risk: 0.4 },
};
const short = (n: string) => n.replace("Illustrative Packaging ", "");
const note = "Candidates are illustrative; nothing here changes stored data.";

function Frame({ title, children, hint }: { title: string; hint: string; children: React.ReactNode }) {
  return <div className="space-y-3 border border-line bg-surface p-4"><div><h3 className="text-body font-semibold">{title}</h3><p className="mt-1 text-micro text-muted">{hint}</p></div>{children}</div>;
}

export function SimulationsWorkspace() {
  const [tab, setTab] = useState<Tab>("removal");
  const [demo, setDemo] = useState<GreenchainDemo | null>(null);
  const [mode, setMode] = useState("sea");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [removed, setRemoved] = useState<GreenchainWhatIf | null>(null);
  const [byMode, setByMode] = useState<Record<string, { name: string; rank: number }[]> | null>(null);
  const [byPreset, setByPreset] = useState<Record<string, { name: string; rank: number }[]> | null>(null);
  const [rev, setRev] = useState({ dataset: "EMBER", country: "PT", factor: 50 });
  const [preview, setPreview] = useState<GcPreview | null>(null);
  const [snap, setSnap] = useState<MemorySnapshot | null>(null);
  const [source, setSource] = useState("");
  const [impact, setImpact] = useState<ImpactPreview | null>(null);
  const [domains, setDomains] = useState<string[]>([]);
  const [picked, setPicked] = useState<string[]>(["health_insurance", "banking", "telecom"]);
  const [query, setQuery] = useState("refund within 30 days");
  const [hits, setHits] = useState<Record<string, PlatformSearchHit[]> | null>(null);

  useEffect(() => {
    let live = true;
    greenchainDemo("sea").then((d) => { if (live) setDemo(d); }).catch((e: unknown) => { if (live) setError(e instanceof Error ? e.message : "GreenChain could not load."); });
    memorySnapshot().then((s) => { if (live) { setSnap(s); setSource(s.sources.find((x) => x.status === "ACTIVE")?.id ?? ""); } }).catch(() => undefined);
    platformStatus().then((s) => { if (live && s.connected) setDomains((s.domains ?? []).filter((d) => d.active).map((d) => d.id)); }).catch(() => undefined);
    return () => { live = false; };
  }, []);

  const run = useCallback(async (fn: () => Promise<void>) => {
    setBusy(true); setError(null);
    try { await fn(); } catch (e) { setError(e instanceof Error ? e.message : "The simulation failed."); } finally { setBusy(false); }
  }, []);

  const suppliers = (demo?.results ?? []) as { name: string }[];
  return (
    <section className="space-y-4" aria-labelledby="sim-heading">
      <div>
        <h2 id="sim-heading" className="text-title font-semibold">Simulations and what-if</h2>
        <p className="mt-1 max-w-3xl text-caption leading-relaxed text-muted">Ask what would change before anything does. Each run is computed for real and discarded: {note}</p>
      </div>
      {error && <p role="alert" className="border-l-2 border-danger bg-surface p-3 text-caption text-danger">{error}</p>}
      <FilterTabs tabs={[{ key: "removal", label: "Supplier removal" }, { key: "scoring", label: "Transport & weights" }, { key: "revision", label: "Dataset revision" }, { key: "impact", label: "Impact preview" }, { key: "compare", label: "Compare domain packs" }]} active={tab} onChange={(k) => setTab(k as Tab)} />

      {tab === "removal" && (
        <Frame title="What if a supplier leaves?" hint="Re-ranks the same candidates without one supplier, using the real scorer.">
          {!demo ? <p role="status" className="text-caption text-muted">Loading candidates…</p> : <>
            <div className="flex flex-wrap gap-2">{suppliers.map((s) => <Button key={s.name} variant="ghost" disabled={busy} onClick={() => void run(async () => setRemoved(await greenchainWhatIf(s.name, mode)))}>Remove {short(s.name)}</Button>)}</div>
            {removed && <p role="status" className="text-caption">Without <strong>{short(removed.removed)}</strong>: {removed.recommendation_changes ? <>the top choice changes from <strong>{short(removed.top_before ?? "")}</strong> to <strong>{short(removed.top_after ?? "")}</strong></> : <>the top choice stays <strong>{short(removed.top_after ?? "")}</strong></>}; {removed.rank_changes.length} rank change(s).
              {removed.rank_changes.length > 0 && <span className="block text-micro text-muted">{removed.rank_changes.map((r) => `${short(r.name)}: ${r.from ?? "–"} → ${r.to}`).join(" · ")}</span>}</p>}</>}
        </Frame>
      )}

      {tab === "scoring" && (
        <Frame title="Transport mode and weighting counterfactuals" hint="Runs the server scorer under each transport mode and each weighting. Lower rank number is better.">
          <div className="flex flex-wrap gap-2">
            <Button variant="primary" disabled={busy || !demo} onClick={() => void run(async () => {
              const out: Record<string, { name: string; rank: number }[]> = {};
              for (const m of TRANSPORT_MODES) { const d = await greenchainDemo(m); out[TRANSPORT_MODE_LABELS[m]] = (d.results as { name: string; rank: number }[]).map((r) => ({ name: r.name, rank: r.rank })); }
              setByMode(out);
            })}>Compare transport modes</Button>
            <Button variant="primary" disabled={busy || !demo} onClick={() => void run(async () => {
              const out: Record<string, { name: string; rank: number }[]> = {};
              for (const [label, w] of Object.entries(PRESETS)) out[label] = (await greenchainScore(demo!.results, mode, w)).results.map((r) => ({ name: r.name, rank: r.rank }));
              setByPreset(out);
            })}>Compare weightings ({TRANSPORT_MODE_LABELS[mode as keyof typeof TRANSPORT_MODE_LABELS].toLowerCase()})</Button>
            <select aria-label="Transport mode for the weighting comparison" className="min-h-11 border border-line bg-surface px-2 text-caption" value={mode} onChange={(e) => setMode(e.target.value)}>{TRANSPORT_MODES.map((m) => <option key={m} value={m}>{TRANSPORT_MODE_LABELS[m]}</option>)}</select>
          </div>
          {([["Rank by transport mode", byMode], ["Rank by weighting", byPreset]] as const).map(([title, table]) => table && (
            <div key={title} className="overflow-x-auto"><table className="w-full text-left text-caption"><caption className="py-1 text-left font-semibold">{title}</caption>
              <thead className="text-muted"><tr><th scope="col" className="p-2">Supplier</th>{Object.keys(table).map((k) => <th key={k} scope="col" className="p-2">{k}</th>)}</tr></thead>
              <tbody>{Object.values(table)[0].map((s) => <tr key={s.name} className="border-t border-line"><th scope="row" className="p-2 font-medium">{short(s.name)}</th>
                {Object.values(table).map((rows, i) => { const r = rows.find((x) => x.name === s.name)!.rank; return <td key={i} className={`p-2 ${r === 1 ? "font-semibold text-verified" : ""}`}>{r}</td>; })}</tr>)}</tbody></table></div>))}
          <p className="text-micro text-muted">Weight sets: {Object.entries(PRESETS).map(([k, w]) => `${k} (${WEIGHT_KEYS.map((x) => `${WEIGHT_LABELS[x].toLowerCase()} ${Math.round(w[x] * 100)}%`).join(", ")})`).join(" · ")}</p>
        </Frame>
      )}

      {tab === "revision" && (
        <Frame title="If a dataset's emission factor were revised" hint="A counterfactual: scale one country's modelled manufacturing emissions, re-rank with the real scorer, write nothing.">
          <div className="flex flex-wrap items-end gap-2">
            <label className="text-caption">Dataset<select className="mt-1 min-h-11 border border-line bg-surface px-2" value={rev.dataset} onChange={(e) => setRev({ ...rev, dataset: e.target.value })}>{["EMBER", "USEEIO", "GLEC", "NDGAIN"].map((d) => <option key={d}>{d}</option>)}</select></label>
            <label className="text-caption">Country<select className="mt-1 min-h-11 border border-line bg-surface px-2" value={rev.country} onChange={(e) => setRev({ ...rev, country: e.target.value })}>{["PT", "DE", "MX", "VN", "CN"].map((d) => <option key={d}>{d}</option>)}</select></label>
            <label className="text-caption">Factor (×)<input type="number" min={0.1} max={100} step={0.5} className="mt-1 min-h-11 w-24 border border-line bg-surface px-2" value={rev.factor} onChange={(e) => setRev({ ...rev, factor: Number(e.target.value) })} /></label>
            <Button variant="primary" disabled={busy} onClick={() => void run(async () => setPreview(await memoryPreviewRevision({ scenario_id: "preview", dataset: rev.dataset, country: rev.country, factor: rev.factor, label: "Preview only" })))}>Simulate</Button>
          </div>
          {preview && <div className="space-y-2" aria-live="polite"><p className="text-caption"><StatusBadge tone="info">counterfactual · nothing written</StatusBadge> {preview.recommendation_changes ? <>The recommendation would change from <strong>{short(preview.top_before)}</strong> to <strong>{short(preview.top_after)}</strong>.</> : <>The recommendation would hold at <strong>{short(preview.top_after)}</strong>; any approval would still have to be repeated.</>}</p>
            <ul className="space-y-0.5 text-caption">{[...preview.ranking].sort((a, b) => a.rank_after - b.rank_after).map((r) => <li key={r.name}>{short(r.name)}: rank {r.rank_before} → <strong>{r.rank_after}</strong> · total {r.total_before.toFixed(1)} → {r.total_after.toFixed(1)} tCO2e</li>)}</ul></div>}
        </Frame>
      )}

      {tab === "impact" && (
        <Frame title="Non-destructive impact preview" hint="Traverses the site graph to list what WOULD go stale if a source were superseded. Reads only.">
          {!snap || snap.sources.length === 0 ? <p className="text-caption text-muted">No sources are recorded yet. Record a decision in Agent Memory first.</p> : <>
            <div className="flex flex-wrap gap-2"><select aria-label="Source" className="min-h-11 min-w-0 flex-1 border border-line bg-surface px-2 text-caption" value={source} onChange={(e) => setSource(e.target.value)}>{snap.sources.map((s) => <option key={s.id} value={s.id}>{s.id} ({s.status.toLowerCase()})</option>)}</select>
              <Button variant="primary" disabled={busy || !source} onClick={() => void run(async () => setImpact(await memoryImpactPreview(source)))}>Preview impact</Button></div>
            {impact && <div aria-live="polite"><p className="text-caption">{impact.would_mark_stale.length === 0 ? "Nothing depends on this source." : `${impact.would_mark_stale.length} item(s) would be marked stale or suspended:`}</p>
              <ul className="mt-1 space-y-1 text-caption">{impact.would_mark_stale.map((i) => <li key={i.id} className="border-b border-line pb-1"><StatusBadge tone="caution">{i.label}</StatusBadge> <span className="font-mono text-micro">{i.id}</span> <span className="text-muted">now {i.status?.toLowerCase()}</span><span className="block text-micro text-muted">via {i.via.join(" → ")}</span></li>)}</ul></div>}</>}
        </Frame>
      )}

      {tab === "compare" && (
        <Frame title="Compare Resolve domain packs for one question" hint="Runs the worker's retrieval in several domain packs on FALKOR DB and shows each pack's best passage side by side. Retrieval only; no model.">
          {domains.length === 0 ? <p className="text-caption text-muted">The Resolve worker is not connected, so there is nothing to compare.</p> : <>
            <div className="flex flex-wrap gap-2">{domains.map((d) => { const on = picked.includes(d); return <Button key={d} variant={on ? "primary" : "ghost"} aria-pressed={on} onClick={() => setPicked(on ? picked.filter((x) => x !== d) : [...picked, d].slice(-4))}>{d.replace(/_/g, " ")}</Button>; })}</div>
            <div className="flex flex-wrap gap-2"><input aria-label="Question" className="min-h-11 min-w-0 flex-1 border border-line bg-surface px-2 text-caption" value={query} onChange={(e) => setQuery(e.target.value)} />
              <Button variant="primary" disabled={busy || query.length < 3 || picked.length === 0} onClick={() => void run(async () => { const out: Record<string, PlatformSearchHit[]> = {}; for (const d of picked) out[d] = (await platformSearch(d, query, 2)).hits; setHits(out); })}>Compare</Button></div>
            {hits && <div className="grid gap-3 md:grid-cols-2">{Object.entries(hits).map(([d, list]) => (
              <div key={d} className="border border-line p-3 text-caption"><p className="font-semibold">{d.replace(/_/g, " ")}</p>
                {list.length === 0 ? <p className="text-muted">No passage matched.</p> : list.map((h) => <div key={h.id} className="mt-2"><p className="font-medium">{String(h.metadata.title ?? h.metadata.filename ?? h.id)} <span className="font-normal text-muted">· {String(h.metadata.authority ?? "authority unknown")} · {h.score.toFixed(2)}</span></p><p className="line-clamp-3 text-muted">{h.text}</p></div>)}</div>))}</div>}</>}
        </Frame>
      )}
    </section>
  );
}
