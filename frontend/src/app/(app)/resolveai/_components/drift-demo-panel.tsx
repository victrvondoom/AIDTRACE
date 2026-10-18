"use client";

import { useState } from "react";
import { Button, StatusBadge } from "@/components/ui";
import { getDriftDemo, runDriftDemo, type DriftDemoResult } from "@/lib/api";
import { useFetch } from "@/lib/use-fetch";

const LABELS: Record<string, string> = {
  "DEMO-DRIFT-SOP-V1": "Earlier source",
  "DEMO-DRIFT-SOP-V2": "Updated source",
  "DEMO-DRIFT-CLAIM-V1": "Earlier extracted claim",
  "DEMO-DRIFT-CLAIM-V2": "Updated extracted claim",
  "DEMO-DRIFT-MEMORY-001": "Recalled agent memory",
  "DEMO-DRIFT-DECISION-001": "Dependent decision",
  "DEMO-DRIFT-PLAN-001": "Inspection plan",
  "DEMO-DRIFT-ACTION-001": "Pending action",
  "DEMO-DRIFT-DECISION-REV-001": "Previously reviewed decision revision",
  "DEMO-DRIFT-DECISION-REV-002": "Current decision revision",
  "DEMO-DRIFT-APPROVAL-REV-001": "Revision-bound approval",
};
const FOCUS_LEVELS = [
  { id: "BROAD", label: "Broad scan" },
  { id: "TARGETED", label: "Targeted" },
  { id: "HYPERFOCUS", label: "Hyperfocus" },
] as const;
const MODALITIES = ["DOCUMENT", "TEXT", "VOICE", "IMAGE", "VIDEO", "TELEMETRY"] as const;
type FocusLevel = (typeof FOCUS_LEVELS)[number]["id"];

export function DriftDemoPanel() {
  const state = useFetch(getDriftDemo, [], 30000);
  const [result, setResult] = useState<DriftDemoResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [focusLevel, setFocusLevel] = useState<FocusLevel>("HYPERFOCUS");
  const [modalities, setModalities] = useState<string[]>(["DOCUMENT", "TEXT"]);
  const current = result ?? (state.status === "live" ? state.data : null);

  async function run() {
    setBusy(true);
    setMessage(null);
    try {
      const next = await runDriftDemo(focusLevel, modalities);
      setResult(next);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "The evidence workflow could not run.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="drift-demo-heading" className="mt-8 border border-line bg-surface p-5 sm:p-7">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2"><h2 id="drift-demo-heading" className="text-title font-semibold">Evidence Drift Cascade</h2><StatusBadge tone="caution">Synthetic scenario</StatusBadge></div>
          <p className="mt-2 max-w-3xl text-caption leading-relaxed text-muted">Run a local, isolated case: one focused agent records an approved procedure, a second recalls it, and a new source revision forces CausalLatch to recheck the decision. The old review remains attached to its exact revision, so its approval cannot authorize the changed action.</p>
        </div>
        <Button variant="primary" disabled={busy} onClick={run}>{busy ? "Running evidence checks…" : current?.seeded ? "Replay synthetic case" : "Run synthetic case"}</Button>
      </div>
      <div className="mt-5 grid gap-5 border-y border-line py-4 lg:grid-cols-[minmax(240px,.8fr)_minmax(0,1.2fr)]">
        <fieldset>
          <legend className="text-caption font-semibold text-ink">Agent focus level</legend>
          <div className="mt-2 flex flex-wrap gap-2">{FOCUS_LEVELS.map((level) => <Button key={level.id} type="button" aria-pressed={focusLevel === level.id} onClick={() => setFocusLevel(level.id)} variant={focusLevel === level.id ? "primary" : "ghost"} className="min-h-10">{level.label}</Button>)}</div>
        </fieldset>
        <fieldset>
          <legend className="text-caption font-semibold text-ink">Requested input modalities</legend>
          <div className="mt-2 flex flex-wrap gap-2">{MODALITIES.map((modality) => {
            const selected = modalities.includes(modality);
            return <Button key={modality} type="button" aria-pressed={selected} onClick={() => setModalities((current) => selected ? current.filter((item) => item !== modality) : [...current, modality])} variant={selected ? "primary" : "ghost"} className="min-h-9 px-3 text-micro">{modality}</Button>;
          })}</div>
          <p className="mt-2 text-micro text-muted">The selector records focus and requested channels. A channel is only processed by this case when its ResolveAI evidence adapter is connected.</p>
        </fieldset>
      </div>
      {state.status === "loading" && !current && <p role="status" className="mt-5 text-caption text-muted">Checking the site-scoped local graph…</p>}
      {state.status === "error" && !current && <p role="status" className="mt-5 border-l-2 border-caution pl-3 text-caption text-muted">Current graph state is unavailable: {state.error.message}</p>}
      {message && <p role="alert" className="mt-4 border-l-2 border-danger pl-3 text-caption text-danger">{message}</p>}
      {current?.statuses && Object.values(current.statuses).some((value) => value !== "NOT_CREATED") && <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(240px,.7fr)]">
        <div className="overflow-x-auto border border-line">
          <table className="w-full text-left text-caption">
            <thead className="bg-surface-2 text-muted"><tr><th scope="col" className="p-3 font-semibold">Dependent record</th><th scope="col" className="p-3 font-semibold">Current state</th></tr></thead>
            <tbody>{Object.entries(current.statuses).filter(([id]) => LABELS[id]).map(([id, value]) => <tr key={id} className="border-t border-line"><th scope="row" className="p-3 font-medium text-ink">{LABELS[id]}</th><td className="p-3 text-muted">{value}</td></tr>)}</tbody>
          </table>
        </div>
        <aside className="border border-line bg-surface-2 p-4">
          <h3 className="text-body font-semibold text-ink">Decision integrity</h3>
          <dl className="mt-3 space-y-2 text-caption">
            {current.authority_verdict && <div className="flex justify-between gap-3"><dt className="text-muted">Source authority</dt><dd className="font-medium">{current.authority_verdict}</dd></div>}
            {current.decision_status && <div className="flex justify-between gap-3"><dt className="text-muted">Re-evaluated decision</dt><dd className="font-medium">{current.decision_status}</dd></div>}
            {current.action_eligibility && <div className="flex justify-between gap-3"><dt className="text-muted">Action eligibility</dt><dd className="font-medium">{current.action_eligibility}</dd></div>}
            {current.impact_paths && <div className="flex justify-between gap-3"><dt className="text-muted">Affected records</dt><dd className="font-medium">{current.impact_paths.length}</dd></div>}
          </dl>
          {(current.decision_revision || current.decision_head || current.human_review) && <div className="mt-4 border-t border-line pt-4">
            <h4 className="text-caption font-semibold text-ink">Revision-bound review</h4>
            <p className="mt-2 text-micro leading-relaxed text-muted">{current.human_review?.approval_id ?? "Review record"} applies to {current.human_review?.approved_revision_id ?? "the recorded revision"}. {current.human_review?.matches_current_revision === false ? "The current revision has changed; this approval does not carry forward." : current.human_review?.matches_current_revision === true ? "The approval matches the current revision." : "Review state loads from the site graph."}</p>
            {current.decision_revision && <p className="mt-2 break-all font-mono text-micro text-muted">Current graph revision: {current.decision_revision.current_graph_revision}</p>}
          </div>}
          {current.agent_focus_trace?.length ? <div className="mt-4 border-t border-line pt-4">
            <h4 className="text-caption font-semibold text-ink">Focused agent handoff <span className="font-normal text-muted">(synthetic trace)</span></h4>
            <ol className="mt-2 space-y-2">{current.agent_focus_trace.map((agent) => <li key={agent.session_id} className="border border-line bg-surface p-3">
              <div className="flex flex-wrap items-center justify-between gap-2"><span className="text-caption font-medium text-ink">{agent.agent_id}</span><span className="border border-line px-2 py-1 font-mono text-micro text-accent">{agent.focus_level}</span></div>
              <p className="mt-1 text-micro text-muted">Scope: {agent.scope}</p>
            </li>)}</ol>
          </div> : null}
          {current.focus_plan && <div className="mt-4 border-t border-line pt-4">
            <h4 className="text-caption font-semibold text-ink">Focus and modality plan</h4>
            <p className="mt-2 text-micro leading-relaxed text-muted">{current.focus_plan.focus_level}: {current.focus_plan.focus_scope}</p>
            <p className="mt-2 text-micro leading-relaxed text-muted">{current.focus_plan.focus_policy}</p>
            <p className="mt-2 text-micro leading-relaxed text-muted">Scenario representation: synthetic {current.focus_plan.scenario_modalities.join(" and ")} fixtures. Case-linked media processing: {current.focus_plan.media_processing_connected ? "connected" : "not connected"}.</p>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              {current.focus_plan.modality_capabilities.map((capability) => <div key={capability.modality} className={`border p-3 ${current.focus_plan?.requested_modalities.includes(capability.modality) ? "border-accent bg-accent/5" : "border-line bg-surface"}`}>
                <div className="flex flex-wrap items-center justify-between gap-2"><span className="text-micro font-semibold text-ink">{capability.modality}</span><span className="font-mono text-[10px] text-muted">{capability.status}</span></div>
                {capability.entrypoint && <p className="mt-1 break-all font-mono text-[10px] text-muted">{capability.entrypoint}</p>}
                <p className="mt-1 text-micro leading-relaxed text-muted">{capability.detail}</p>
              </div>)}
            </div>
            {current.focus_plan.unconnected_modalities.length > 0 && <p className="mt-2 text-micro leading-relaxed text-caution">Not connected to this workflow: {current.focus_plan.unconnected_modalities.join(", ")}.</p>}
          </div>}
          <p className="mt-4 break-all border-t border-line pt-3 text-micro text-muted">Audit chain hash: {current.audit_chain_hash ?? "Recorded in local graph after run"}</p>
          <p className="mt-3 text-micro leading-relaxed text-muted">Synthetic evidence only. No real asset or external action is affected.</p>
        </aside>
      </div>}
    </section>
  );
}
