"use client";

// Agent memory and the evidence cascade, on the site's FalkorDB graph. Everything shown is read back from the graph: what each agent
// remembered, the evidence behind it, which memories are still usable, and whether a human approval still applies. The dataset
// revision is a counterfactual the user enters (country and factor); the cascade and the re-ranking that follow are real.
import { useCallback, useEffect, useMemo, useState } from "react";
import { normalizeSnapshot } from "@/components/aidtrace/data";
import { Button, StatusBadge } from "@/components/ui";
import {
  memoryApprove, memoryHandoffs, memoryPreviewRevision, memoryRecall, memoryRecordScenario, memoryRevise, memorySnapshot,
  type GcPreview, type GcRevised, type Handoff, type MemoryRecord, type MemorySnapshot, type RecallResult, type RankRow,
} from "@/lib/lab-api";

const DATASETS = [["EMBER", "Ember grid intensity"], ["USEEIO", "USEEIO supply-chain factors"], ["GLEC", "GLEC transport factors"], ["NDGAIN", "ND-GAIN climate risk"]] as const;
const COUNTRIES = ["PT", "DE", "MX", "VN", "CN"];
const tone = (s: string) => (s === "VALID" || s === "ACTIVE" || s === "APPROVED" ? "verified" : s === "STALE" || s === "SUSPENDED" || s === "VOID" || s === "SUPERSEDED" || s === "INVALIDATED" ? "danger" : "caution") as "verified" | "danger" | "caution";
const scenarioOf = (id: string) => /^gc:([^:]+):/.exec(id)?.[1] ?? null;

function RankTable({ rows }: { rows: RankRow[] }) {
  return (
    <div className="overflow-x-auto"><table className="w-full text-left text-caption">
      <caption className="sr-only">Supplier ranking before and after</caption>
      <thead className="text-muted"><tr>{["Supplier", "Rank before", "Rank after", "Total tCO2e before", "after"].map((h) => <th key={h} scope="col" className="p-2 font-semibold">{h}</th>)}</tr></thead>
      <tbody>{[...rows].sort((a, b) => a.rank_after - b.rank_after).map((r) => (
        <tr key={r.name} className={`border-t border-line ${r.rank_before !== r.rank_after ? "bg-surface-2" : ""}`}>
          <th scope="row" className="p-2 font-medium">{r.name.replace("Illustrative ", "")} <span className="font-normal text-muted">{r.country}</span></th>
          <td className="p-2">{r.rank_before}</td><td className="p-2">{r.rank_after}{r.rank_before !== r.rank_after && " ●"}</td>
          <td className="p-2 font-mono text-micro">{r.total_before.toFixed(1)}</td><td className="p-2 font-mono text-micro">{r.total_after.toFixed(1)}</td></tr>))}</tbody>
    </table></div>
  );
}

function Mem({ m }: { m: MemoryRecord }) {
  return (
    <li className="border border-line bg-surface p-3 text-caption">
      <div className="flex flex-wrap items-center justify-between gap-2"><span className="font-medium">{m.memory_kind.toLowerCase()} · {m.agent_id}</span><StatusBadge tone={tone(m.status)}>{m.status.toLowerCase()}</StatusBadge></div>
      <p className="mt-1">{m.summary}</p>
      <p className="mt-1 text-micro text-muted">{m.claims.length} claim(s) · {m.independent_sources} independent source(s) · {m.verification_status.toLowerCase()} · confidence {m.confidence.toFixed(2)}{m.blocked_reason ? ` · blocked: ${m.blocked_reason}` : ""}</p>
      <details className="mt-1 text-micro text-muted"><summary className="cursor-pointer">Provenance</summary>
        <ul className="mt-1 space-y-0.5 font-mono">{m.claims.map((c) => <li key={c.id}>claim {c.id} [{c.status}] {c.fact_key} = {String(c.fact_value)}</li>)}{m.sources.map((s) => <li key={s.id}>source {s.id} [{s.status}]</li>)}</ul></details>
    </li>
  );
}

export function AgentMemoryWorkspace() {
  const [snap, setSnap] = useState<MemorySnapshot | null>(null);
  const [handoffs, setHandoffs] = useState<Handoff[]>([]);
  const [scenario, setScenario] = useState<string | null>(null);
  const [form, setForm] = useState({ dataset: "EMBER", country: "PT", factor: 3, label: "Reference data revision (counterfactual)" });
  const [preview, setPreview] = useState<GcPreview | null>(null);
  const [revised, setRevised] = useState<GcRevised | null>(null);
  const [refusal, setRefusal] = useState<{ action: string; message: string } | null>(null);
  const [receipt, setReceipt] = useState<string | null>(null);
  const [recall, setRecall] = useState<RecallResult | null>(null);
  const [agent, setAgent] = useState("agent:fraud-investigator");
  const [factKey, setFactKey] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try { const [s, h] = await Promise.all([memorySnapshot(), memoryHandoffs()]); setSnap(normalizeSnapshot(s)); setHandoffs(h.handoffs ?? []); setError(null); }
    catch (e) { setError(e instanceof Error ? e.message : "Agent memory could not be read."); }
  }, []);
  useEffect(() => { const t = window.setTimeout(() => void refresh(), 0); return () => window.clearTimeout(t); }, [refresh]);

  const scenarios = useMemo(() => [...new Set((snap?.decisions ?? []).map((d) => scenarioOf(d.id)).filter((x): x is string => Boolean(x)))], [snap]);
  const active = scenario ?? scenarios[0] ?? null;
  const decisions = (snap?.decisions ?? []).filter((d) => active && d.id.startsWith(`gc:${active}:`));
  const memories = (snap?.memories ?? []).filter((m) => active && m.id.startsWith(`gc:${active}:`));
  const otherMemories = (snap?.memories ?? []).filter((m) => !m.id.startsWith("gc:"));
  const actionFor = (decisionId: string) => snap?.actions.find((a) => a.eligibility.decision_id === decisionId);
  const approvals = (snap?.approvals ?? []).filter((a) => active && a.decision_id.startsWith(`gc:${active}:`));

  async function run<T>(key: string, fn: () => Promise<T>): Promise<T | null> {
    setBusy(key); setError(null);
    try { return await fn(); } catch (e) { setError(e instanceof Error ? e.message : "The request failed."); return null; } finally { setBusy(null); }
  }
  function resetResults() { setRevised(null); setPreview(null); setReceipt(null); setRefusal(null); }
  async function record() {
    const r = await run("record", () => memoryRecordScenario());
    if (r) { setScenario(r.scenario_id); resetResults(); await refresh(); }
  }
  async function approve(actionId: string) {
    setRefusal(null); setReceipt(null); setBusy("approve");
    try { const r = await memoryApprove(actionId); setReceipt(`Approved revision ${r.graph_revision.slice(0, 10)}… as ${r.reviewer}. Nothing was sent or purchased.`); }
    catch (e) { setRefusal({ action: actionId, message: e instanceof Error ? e.message : "Approval was refused." }); }
    finally { setBusy(null); await refresh(); }
  }
  const body = () => ({ scenario_id: active!, dataset: form.dataset, country: form.country, factor: form.factor, label: form.label });
  async function doPreview() { const r = await run("preview", () => memoryPreviewRevision(body())); if (r) setPreview(r); }
  async function doRevise() {
    const r = await run("revise", () => memoryRevise(body()));
    if (r) { setRevised(r); setPreview(null); setReceipt(null); setRefusal(null); await refresh(); }
  }
  async function doRecall() { const r = await run("recall", () => memoryRecall(agent, factKey)); if (r) { setRecall(r); await refresh(); } }

  return (
    <section className="space-y-5" aria-labelledby="memory-heading">
      <div>
        <h2 id="memory-heading" className="text-title font-semibold">Agent memory and evidence drift</h2>
        <p className="mt-1 max-w-3xl text-caption leading-relaxed text-muted">Agents record what they concluded together with the evidence behind it. When a source is superseded, AIDTRACE traces which memories, decisions and approvals rested on it, marks them stale, and refuses to approve anything that no longer holds. Stored in this site&apos;s FalkorDB graph.</p>
      </div>
      {error && <p role="alert" className="border-l-2 border-danger bg-surface p-3 text-caption text-danger">{error}</p>}
      {!snap && !error && <p role="status" className="text-caption text-muted">Reading the memory graph…</p>}

      {snap && (<>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="primary" disabled={busy !== null} onClick={() => void record()}>{busy === "record" ? "Scoring and recording…" : "Record a GreenChain decision"}</Button>
          {scenarios.map((s) => <Button key={s} variant={s === active ? "primary" : "ghost"} aria-pressed={s === active} onClick={() => { setScenario(s); resetResults(); }}>Scenario {s}</Button>)}
          <span className="text-micro text-muted">Candidates are illustrative; scoring uses GreenChain&apos;s real models.</span>
        </div>
        {!active && <p className="border border-line bg-surface p-5 text-caption text-muted">No decision has been recorded yet. Record one to see its evidence, approve it, then revise a dataset and watch it go stale.</p>}

        {active && (
          <div className="grid gap-4 xl:grid-cols-2">
            <div className="space-y-4">
              <div className="border border-line bg-surface p-4">
                <h3 className="text-body font-semibold">Recommendations and approvals</h3>
                <ul className="mt-2 space-y-3">{decisions.map((d) => { const a = actionFor(d.id); return (
                  <li key={d.id} className="border-t border-line pt-3 text-caption first:border-t-0 first:pt-0">
                    <div className="flex flex-wrap items-center justify-between gap-2"><strong>{d.summary}</strong><StatusBadge tone={tone(d.status)}>{d.status.toLowerCase()} · rev {d.revision_n}</StatusBadge></div>
                    {a && <>
                      <p className="mt-1 text-muted">{a.summary} <StatusBadge tone={tone(a.status)}>{a.status.toLowerCase()}</StatusBadge></p>
                      <p className="mt-1 text-micro text-muted">{a.eligibility.approval_current ? "A human approval for this exact revision is on record." : a.eligibility.eligible ? "Eligible for approval; no approval on this revision yet." : `Not eligible: ${a.eligibility.reasons.join("; ")}.`}</p>
                      <Button className="mt-2" variant="ghost" disabled={busy !== null || a.eligibility.approval_current} onClick={() => void approve(a.id)}>Approve current revision</Button></>}
                    {refusal && a && refusal.action === a.id && <p role="alert" className="mt-2 border-l-2 border-danger bg-surface-2 p-2 text-micro text-danger">{refusal.message}</p>}
                  </li>); })}</ul>
                {receipt && <p role="status" className="mt-3 border-l-2 border-verified bg-surface-2 p-2 text-micro">{receipt}</p>}
                {approvals.length > 0 && <details className="mt-3 text-micro text-muted"><summary className="cursor-pointer">Approval receipts ({approvals.length})</summary>
                  <ul className="mt-1 space-y-1">{approvals.map((a) => <li key={a.id}><StatusBadge tone={tone(a.approval_status)}>{a.approval_status.toLowerCase()}</StatusBadge> {a.approved_by} · revision {a.graph_revision.slice(0, 10)}… · {a.approved_at.slice(0, 19).replace("T", " ")}</li>)}</ul></details>}
              </div>

              <div className="border border-line bg-surface p-4">
                <h3 className="text-body font-semibold">Revise a reference dataset (counterfactual)</h3>
                <p className="mt-1 text-micro text-muted">Scales the modelled manufacturing emissions of one country&apos;s suppliers, as if its factor had been revised. It does not claim any published dataset changed. Preview writes nothing; Apply runs the real cascade on the graph.</p>
                <div className="mt-3 grid gap-2 sm:grid-cols-2">
                  <label className="text-caption">Dataset<select className="mt-1 min-h-11 w-full border border-line bg-surface px-2" value={form.dataset} onChange={(e) => setForm({ ...form, dataset: e.target.value })}>{DATASETS.map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
                  <label className="text-caption">Country<select className="mt-1 min-h-11 w-full border border-line bg-surface px-2" value={form.country} onChange={(e) => setForm({ ...form, country: e.target.value })}>{COUNTRIES.map((c) => <option key={c}>{c}</option>)}</select></label>
                  <label className="text-caption">Factor (×)<input type="number" min={0.1} max={100} step={0.5} className="mt-1 min-h-11 w-full border border-line bg-surface px-2" value={form.factor} onChange={(e) => setForm({ ...form, factor: Number(e.target.value) })} /></label>
                  <label className="text-caption">Label<input className="mt-1 min-h-11 w-full border border-line bg-surface px-2" value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} /></label>
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  <Button variant="ghost" onClick={() => setForm({ ...form, country: "PT", factor: 3 })}>Moderate (×3)</Button>
                  <Button variant="ghost" onClick={() => setForm({ ...form, country: "PT", factor: 50 })}>Large (×50)</Button>
                  <Button variant="ghost" disabled={busy !== null} onClick={() => void doPreview()}>Preview (no writes)</Button>
                  <Button variant="primary" disabled={busy !== null || form.label.length < 3} onClick={() => void doRevise()}>{busy === "revise" ? "Running cascade…" : "Apply revision"}</Button>
                </div>
                {preview && <div className="mt-3 space-y-2 border-t border-line pt-3"><p className="text-caption"><StatusBadge tone="info">preview · nothing written</StatusBadge> Top supplier {preview.recommendation_changes ? <>would change from <strong>{preview.top_before}</strong> to <strong>{preview.top_after}</strong></> : <>would stay <strong>{preview.top_after}</strong></>}.</p><RankTable rows={preview.ranking} /></div>}
              </div>
            </div>

            <div className="space-y-4">
              {revised && (
                <div className="space-y-3 border border-line bg-surface p-4" aria-live="polite">
                  <h3 className="text-body font-semibold">Cascade result</h3>
                  {revised.duplicate ? <p className="text-caption text-muted">This exact revision was already applied; nothing changed a second time.</p> : <>
                    <p className="text-caption">Authority check: <strong>{revised.cascade.verdict}</strong>. {revised.recommendation_changed ? <>The recommendation <strong>changed</strong> from {revised.top_before} to {revised.top_after}.</> : <>The recommendation <strong>holds</strong> ({revised.top_after}), but its approval no longer applies.</>}</p>
                    <ul className="space-y-1 text-micro">{revised.cascade.invalidated.map((i) => <li key={i.id} className="border-b border-line pb-1"><StatusBadge tone={tone(i.after)}>{i.before.toLowerCase() || "—"} → {i.after.toLowerCase()}</StatusBadge> {i.label} <span className="font-mono">{i.id}</span><span className="block text-muted">via {i.via.join(" → ")}</span></li>)}</ul>
                    <RankTable rows={revised.ranking} />
                    {revised.new_proposal && <p className="border-l-2 border-caution bg-surface-2 p-2 text-micro">A new proposal for {revised.top_after} was created. It needs its own human approval on the left.</p>}</>}
                </div>
              )}
              <div className="border border-line bg-surface p-4">
                <h3 className="text-body font-semibold">Memory</h3>
                <ul className="mt-2 space-y-2">{memories.map((m) => <Mem key={m.id} m={m} />)}{memories.length === 0 && <li className="text-caption text-muted">None for this scenario.</li>}</ul>
              </div>
            </div>
          </div>
        )}

        <div className="grid gap-4 xl:grid-cols-2">
          <div className="space-y-3 border border-line bg-surface p-4">
            <h3 className="text-body font-semibold">Recall as another agent</h3>
            <p className="text-micro text-muted">What an agent may rely on right now. Stale or superseded memory comes back as blocked, with the reason, and is never offered as usable.</p>
            <div className="flex flex-wrap gap-2">
              <input aria-label="Agent id" className="min-h-11 min-w-0 flex-1 border border-line bg-surface px-2 text-caption" value={agent} onChange={(e) => setAgent(e.target.value)} />
              <input aria-label="Fact key (optional)" placeholder="fact key, e.g. top_supplier:s1" className="min-h-11 min-w-0 flex-1 border border-line bg-surface px-2 text-caption" value={factKey} onChange={(e) => setFactKey(e.target.value)} />
              <Button variant="primary" disabled={busy !== null || agent.length < 2} onClick={() => void doRecall()}>Recall</Button>
            </div>
            {recall && <div className="space-y-2 text-caption"><p>{recall.usable.length} usable · {recall.blocked.length} blocked</p>
              <ul className="space-y-2">{recall.usable.map((m) => <Mem key={m.id} m={m} />)}{recall.blocked.map((m) => <Mem key={m.id} m={m} />)}</ul></div>}
          </div>
          <div className="border border-line bg-surface p-4">
            <h3 className="text-body font-semibold">Handoffs between agents</h3>
            {handoffs.length === 0 ? <p className="mt-2 text-caption text-muted">No agent has recalled another agent&apos;s memory yet.</p> :
              <ul className="mt-2 space-y-1 text-caption">{handoffs.map((h) => <li key={h.recall_session + h.memory_id} className="border-b border-line pb-1"><strong>{h.recalled_by}</strong> used <span className="font-mono text-micro">{h.memory_id}</span> from {h.produced_by} <StatusBadge tone={h.usable ? "verified" : "danger"}>{h.usable ? "still usable" : "now stale"}</StatusBadge></li>)}</ul>}
            {otherMemories.length > 0 && <><h4 className="mt-4 text-caption font-semibold">Memories from other agents</h4><ul className="mt-2 space-y-2">{otherMemories.map((m) => <Mem key={m.id} m={m} />)}</ul></>}
          </div>
        </div>
      </>)}
    </section>
  );
}
