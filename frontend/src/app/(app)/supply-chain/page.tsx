"use client";

import { useState } from "react";
import { PageHeader } from "@/components/ui";
import { fetchWithSession } from "@/lib/api";
import { useFetch } from "@/lib/use-fetch";
import { GraphLabWorkspace } from "@/features/graph-lab/graph-lab-workspace";

type EvaluationCase = {
  id: string;
  expected: unknown;
  actual: unknown;
  pass: boolean;
  receipt: Record<string, unknown>;
};

type Evaluation = {
  workflow: string;
  data_class: string;
  summary: { cases: number; passed: number; failed: number; accuracy: number; verdict: string };
  cases: EvaluationCase[];
  graph: { nodes: { id: string; label: string; type: string }[]; edges: { source: string; target: string; rel: string; certainty: string }[] };
  method: string;
};

const TITLES: Record<string, string> = {
  vulnerability_reachability: "Software exposure",
  settlement_conflict: "Supplier settlement evidence",
  disruption_path: "Disruption impact path",
  alternate_supplier_path: "Alternate source recovery",
  evidence_gated_settlement: "Settlement decision gate",
  counterfactual_supplier_isolation: "Counterfactual isolation",
};

function display(value: unknown): string {
  if (typeof value === "string") return value.replaceAll("_", " ");
  if (typeof value === "boolean") return value ? "Confirmed" : "Not confirmed";
  if (value && typeof value === "object") {
    return Object.entries(value as Record<string, unknown>).map(([key, item]) => `${key.replaceAll("_", " ")}: ${String(item)}`).join(" · ");
  }
  return String(value ?? "Unknown");
}

async function fetchEvaluation() {
  const response = await fetchWithSession("/graphlab/evaluation/supply-chain", { cache: "no-store" });
  if (!response.ok) throw new Error(`Evaluation service returned ${response.status}.`);
  return { data: await response.json() as Evaluation, source: "live" as const };
}

export default function SupplyChainPage() {
  const [revision, setRevision] = useState(0);
  const state = useFetch(fetchEvaluation, [revision]);
  const evaluation = state.status === "live" ? state.data : null;
  const error = state.status === "error" ? state.error.message : null;
  const loading = state.status === "loading";
  const load = () => setRevision((value) => value + 1);
  const settlement = evaluation?.cases.find((item) => item.id === "evidence_gated_settlement")?.actual;
  const conflict = evaluation?.cases.find((item) => item.id === "settlement_conflict")?.actual;
  const shortfall = conflict && typeof conflict === "object" && "shortfall_units" in conflict ? conflict.shortfall_units : undefined;
  const recovery = evaluation?.cases.find((item) => item.id === "alternate_supplier_path")?.actual;

  return (
    <main className="mx-auto max-w-[1400px]">
      <PageHeader title="Supply Chain" lede="Trace software vulnerabilities and supplier disruptions through the same evidence graph. Review affected services, settlement conflicts, recovery paths, and the checks behind each decision." />

      {loading && <div className="mt-6 rounded-xl border border-line bg-surface p-6 text-body text-muted" role="status">Loading supply-chain evaluation…</div>}

      {error && <section className="mt-6 rounded-xl border border-line bg-surface p-6" role="alert">
        <h2 className="text-title font-semibold text-ink">Evaluation unavailable</h2>
        <p className="mt-2 text-body text-muted">{error}</p>
        <button type="button" onClick={() => void load()} className="mt-4 min-h-11 bg-accent px-4 text-body font-semibold text-on-accent">Retry</button>
      </section>}

      {evaluation && <>
        <section aria-label="Evaluation summary" className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {[
            ["Evaluation state", evaluation.summary.verdict],
            ["Cases passed", `${evaluation.summary.passed} / ${evaluation.summary.cases}`],
            ["Agreement", `${Math.round(evaluation.summary.accuracy * 100)}%`],
            ["Graph scope", `${evaluation.graph.nodes.length} nodes, ${evaluation.graph.edges.length} relationships`],
          ].map(([label, value]) => <article key={label} className="rounded-xl border border-line bg-surface p-4 shadow-sm">
            <p className="text-label font-medium text-muted">{label}</p>
            <p className="mt-2 text-title font-semibold capitalize text-ink">{value}</p>
          </article>)}
        </section>

        <section className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(320px,0.8fr)]">
          <div>
            <div className="mb-3 flex items-end justify-between gap-3">
              <div><h2 className="text-heading font-semibold text-ink">Evaluation cases</h2><p className="mt-1 text-caption text-muted">Each result includes the graph evidence used to check it.</p></div>
              <button type="button" onClick={() => void load()} className="min-h-11 border border-line bg-surface px-3 text-label font-semibold text-ink hover:bg-surface-2">Run again</button>
            </div>
            <div className="space-y-3">
              {evaluation.cases.map((item) => <article key={item.id} className="rounded-xl border border-line bg-surface p-4 shadow-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="text-body font-semibold text-ink">{TITLES[item.id] ?? item.id}</h3>
                  <span className={`rounded-md border px-2 py-1 text-label font-semibold ${item.pass ? "border-line bg-surface-2 text-ink" : "border-danger text-danger"}`}>{item.pass ? "PASS" : "REVIEW"}</span>
                </div>
                <p className="mt-2 text-caption text-muted">Expected: <span className="text-ink">{display(item.expected)}</span></p>
                <p className="mt-1 text-caption text-muted">Observed: <span className="text-ink">{display(item.actual)}</span></p>
                <details className="mt-3 border-t border-line pt-3">
                  <summary className="min-h-8 cursor-pointer text-label font-semibold text-accent">Evidence receipt</summary>
                  <pre className="mt-2 max-h-64 overflow-auto rounded-lg bg-surface-2 p-3 text-micro leading-relaxed text-ink">{JSON.stringify(item.receipt, null, 2)}</pre>
                </details>
              </article>)}
            </div>
          </div>

          <aside className="space-y-4">
            <section className="rounded-xl border border-line bg-surface p-4 shadow-sm">
              <h2 className="text-heading font-semibold text-ink">Connected supply graph</h2>
              <p className="mt-1 text-caption text-muted">Software, services, suppliers, evidence, plant impact, and controls.</p>
              <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-2">
                {Object.entries(Object.groupBy(evaluation.graph.nodes, (node) => node.type)).map(([type, nodes]) => <div key={type} className="rounded-lg border border-line bg-surface-2 p-3">
                  <p className="text-micro font-semibold uppercase tracking-wide text-muted">{type.replaceAll("_", " ")}</p>
                  <p className="mt-1 text-title font-semibold text-ink">{nodes?.length ?? 0}</p>
                </div>)}
              </div>
              <p className="mt-4 text-caption text-muted">{evaluation.graph.edges.filter((edge) => edge.certainty === "maybe").length} uncertain relationship; possible exposure remains separate from confirmed impact.</p>
            </section>

            <section className="rounded-xl border border-line bg-surface p-4 shadow-sm">
              <h2 className="text-heading font-semibold text-ink">Workflow outcome</h2>
              <dl className="mt-3 space-y-3 text-caption">
                <div className="flex justify-between gap-3"><dt className="text-muted">Settlement</dt><dd className="font-semibold text-ink">{display(settlement)}</dd></div>
                <div className="flex justify-between gap-3"><dt className="text-muted">Supplier shortfall</dt><dd className="font-semibold text-ink">{typeof shortfall === "number" ? `${shortfall} units` : "Unknown"}</dd></div>
                <div className="flex justify-between gap-3"><dt className="text-muted">Alternate route</dt><dd className="font-semibold text-ink">{recovery === true ? "Available in scenario" : recovery === false ? "No route found" : "Unknown"}</dd></div>
                <div className="flex justify-between gap-3"><dt className="text-muted">Data class</dt><dd className="font-semibold capitalize text-ink">{evaluation.data_class}</dd></div>
              </dl>
            </section>
          </aside>
        </section>

        <p className="mt-5 rounded-lg bg-surface-2 p-3 text-caption text-muted">{evaluation.method}</p>
      </>}
      <section className="mt-6" aria-label="Interactive supply-chain investigation">
        <GraphLabWorkspace embedded initialScenario="supply_chain" initialAlgo="blast_radius" title="Investigate Supply Chain" lede="Change the graph, engine or parameters to recalculate impact and recovery paths. The built-in scenario is synthetic; choose Site evidence or Paste JSON to investigate your own data." />
      </section>
    </main>
  );
}
