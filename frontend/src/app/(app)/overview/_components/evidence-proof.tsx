"use client";

import Link from "next/link";
import { useState } from "react";
import { Icon } from "@/components/icon";
import { getDriftDemo, runDriftDemo, type DriftDemoResult } from "@/lib/api";
import { useFetch } from "@/lib/use-fetch";

const NODE_NAMES: Record<string, string> = {
  "DEMO-DRIFT-SOP-V1": "Earlier procedure",
  "DEMO-DRIFT-CLAIM-V1": "Earlier claim",
  "DEMO-DRIFT-MEMORY-001": "Agent memory",
  "DEMO-DRIFT-DECISION-001": "Decision",
  "DEMO-DRIFT-PLAN-001": "Audit plan",
  "DEMO-DRIFT-ACTION-001": "Action",
};

function shortHash(value: string | undefined) {
  return value ? value.slice(0, 12) : "Unavailable";
}

export function EvidenceProof() {
  const state = useFetch(getDriftDemo, [], 30000);
  const [latest, setLatest] = useState<DriftDemoResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const proof = latest ?? (state.status === "live" ? state.data : null);
  const seeded = Boolean(proof?.seeded || proof?.source_after);
  const oldSource = proof?.sources?.find((source) => source.id === "DEMO-DRIFT-SOP-V1");
  const newSource = proof?.sources?.find((source) => source.id === "DEMO-DRIFT-SOP-V2");
  const condition = proof?.condition_results?.find((item) => item.key === "inspection_interval_days");
  const actionPath = proof?.impact_paths?.find((item) => item.node_id === "DEMO-DRIFT-ACTION-001")?.path ?? [];
  const staleApproval = proof?.human_review?.matches_current_revision === false;

  async function replay() {
    setBusy(true);
    setRunError(null);
    try {
      await runDriftDemo();
      const persistedProof = await getDriftDemo();
      setLatest(persistedProof.data);
    } catch (error) {
      setRunError(error instanceof Error ? error.message : "The local evidence proof could not run.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section data-testid="overview-evidence-proof" aria-labelledby="overview-evidence-title" className="mt-6 overflow-hidden rounded-2xl border border-[#34465d] bg-[#101b2c] text-[#f4f7fb] shadow-[0_20px_48px_rgba(10,22,38,.16)]">
      <div className="flex flex-wrap items-start justify-between gap-5 border-b border-[#34465d] px-5 py-6 sm:px-7">
        <div className="max-w-2xl">
          <p className="text-micro font-bold uppercase tracking-[.18em] text-[#ffb974]">AIDTRACE · evidence control</p>
          <h2 id="overview-evidence-title" className="mt-2 text-title font-semibold tracking-tight sm:text-display">Evidence, in plain sight.</h2>
          <p className="mt-2 text-caption leading-relaxed text-[#b5c4d6]">A site-scoped FalkorDB proof: see the source revision, the fact it changed, every dependent decision, and why an earlier approval cannot carry forward.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-md border border-[#53647a] px-2.5 py-1 text-micro font-semibold text-[#cedae8]">SYNTHETIC CASE</span>
          <button type="button" disabled={busy} onClick={replay} className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-[#ffad5c] bg-[#ffad5c] px-4 text-caption font-semibold text-[#171d28] transition-colors hover:bg-[#ffc487] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ffad5c] disabled:opacity-60">
            <Icon name="arrow-clockwise" className="size-4" />{busy ? "Running proof…" : seeded ? "Replay proof" : "Run evidence proof"}
          </button>
        </div>
      </div>

      {runError && <p role="alert" className="mx-5 mt-4 border-l-2 border-[#ff8e91] pl-3 text-caption text-[#ffb8ba] sm:mx-7">{runError}</p>}
      {state.status === "error" && !latest && <div role="status" className="flex flex-wrap items-center justify-between gap-3 px-5 py-6 text-caption text-[#d2ddeb] sm:px-7"><span>Evidence graph unavailable: {state.error.message}</span><button type="button" onClick={state.retry} className="min-h-11 rounded-md border border-[#6c819d] px-3 font-semibold focus-visible:outline-2 focus-visible:outline-[#ffad5c]">Retry read</button></div>}
      {state.status === "loading" && !latest && <p role="status" className="px-5 py-6 text-caption text-[#b5c4d6] sm:px-7">Reading the site evidence graph…</p>}
      {state.status === "live" && !seeded && !latest && <div className="px-5 py-6 sm:px-7"><p className="text-body font-medium">No synthetic proof has been recorded for this site yet.</p><p className="mt-1 text-caption text-[#b5c4d6]">Run the isolated case to create a reviewable evidence trail. It does not execute a plant action.</p></div>}

      {seeded && proof && <div className="px-5 py-6 sm:px-7">
        <div className="grid gap-3 md:grid-cols-3">
          <div className="rounded-xl border border-[#40536b] bg-[#1b2a3f] p-4">
            <p className="text-micro font-bold uppercase tracking-[.12em] text-[#aabbd0]">01 · Source changed</p>
            <div className="mt-3 flex flex-wrap items-center gap-2 text-body font-semibold"><span>Earlier procedure</span><span aria-hidden="true" className="text-[#ffb974]">→</span><span>Current procedure</span></div>
            <p className="mt-2 text-caption text-[#c3d0df]">{oldSource?.status ?? proof.statuses["DEMO-DRIFT-SOP-V1"] ?? "Unknown"} → {newSource?.status ?? proof.statuses["DEMO-DRIFT-SOP-V2"] ?? "Unknown"}</p>
            <p className="mt-1 text-micro text-[#aabbd0]">{oldSource && newSource ? `Verified graph versions · authority ${oldSource.authority_level} → ${newSource.authority_level}` : proof.authority_verdict ? `Authority check: ${proof.authority_verdict}` : "Authority details unavailable"}</p>
          </div>
          <div className="rounded-xl border border-[#40536b] bg-[#1b2a3f] p-4">
            <p className="text-micro font-bold uppercase tracking-[.12em] text-[#aabbd0]">02 · Claim checked</p>
            <p className="mt-3 text-body font-semibold">Inspection interval</p>
            <p className="mt-2 text-caption text-[#c3d0df]">Reviewed condition <strong className="text-white">{String(condition?.value ?? "?")} days</strong> · current claim <strong className="text-[#ffb974]">{String(condition?.actual ?? "?")} days</strong></p>
            <p className="mt-1 text-micro text-[#aabbd0]">{condition ? condition.holds ? "Condition holds" : "Condition no longer holds" : "Condition result unavailable"}</p>
          </div>
          <div className="rounded-xl border border-[#efaa68] bg-[#322a2a] p-4">
            <p className="text-micro font-bold uppercase tracking-[.12em] text-[#ffbb7e]">03 · Action held</p>
            <p className="mt-3 text-body font-semibold">{proof.action_eligibility ?? proof.statuses["DEMO-DRIFT-ACTION-001"] ?? "Unknown"}</p>
            <p className="mt-2 text-caption text-[#ead1c1]">{staleApproval ? "Approval belongs to the earlier decision revision." : "Review state is still being checked."}</p>
            <p className="mt-1 text-micro text-[#e5ba9e]">External actions executed: no</p>
          </div>
        </div>

        <div className="mt-5 grid gap-5 border-t border-[#34465d] pt-5 lg:grid-cols-[minmax(0,1.5fr)_minmax(240px,.7fr)]">
          <div>
            <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="text-caption font-semibold">Recorded dependency path</h3><span className="text-micro text-[#aabbd0]">{proof.impact_paths?.length ?? 0} affected records</span></div>
            {actionPath.length ? <ol className="mt-3 flex flex-wrap gap-2" aria-label="Source to action dependency path">{actionPath.map((node, index) => <li key={`${node}-${index}`} className="flex items-center gap-2"><span className="rounded-md border border-[#4b607a] bg-[#1b2a3f] px-2.5 py-2 text-micro font-medium" title={node}>{NODE_NAMES[node] ?? node}</span>{index < actionPath.length - 1 && <span aria-hidden="true" className="text-[#ffb974]">→</span>}</li>)}</ol> : <p className="mt-3 text-caption text-[#aabbd0]">No dependency path has been recorded.</p>}
          </div>
          <div className="min-w-0 border-l border-[#34465d] pl-4 text-micro text-[#adbed0]">
            <p>Case <span className="font-mono text-[#e5edf6]">{proof.case_id}</span></p>
            <p className="mt-2">Current revision <span className="font-mono text-[#e5edf6]" title={proof.decision_revision?.current_graph_revision}>{shortHash(proof.decision_revision?.current_graph_revision)}</span></p>
            <p className="mt-2">Audit chain <span className="font-mono text-[#e5edf6]" title={proof.audit_chain_hash}>{shortHash(proof.audit_chain_hash)}</span></p>
            <div className="mt-4 flex flex-wrap gap-3"><Link href="/resolveai" className="font-semibold text-[#ffbd7e] underline-offset-4 hover:underline">Inspect full case</Link><Link href="/documents" className="font-semibold text-[#ffbd7e] underline-offset-4 hover:underline">Open document vault</Link></div>
          </div>
        </div>
      </div>}
    </section>
  );
}
