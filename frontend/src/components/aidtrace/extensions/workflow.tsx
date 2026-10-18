"use client";

// One page for the whole investigation, in the order a reviewer works: what is at risk, what supports it, whether the decision still stands, and what
// happened. Every step is an existing native panel that reads the FalkorDB graph and the shared selection, so nothing here needs a store that is not running.
import type { ComponentType } from "react";
import { ActivityTimeline, ConnectedGraph, DecisionValidity, EvidenceForContext, Provenance, RiskAnalytics } from "./native";

// Risk without the governance queues: those live in the plant stores, not the graph.
const GraphRisk = () => <RiskAnalytics graphOnly />;

const STEPS: { n: number; title: string; purpose: string; panels: ComponentType[] }[] = [
  { n: 1, title: "Investigate", purpose: "What is at risk, and what depends on it.", panels: [GraphRisk, ConnectedGraph] },
  { n: 2, title: "Evidence", purpose: "The sources behind each claim, and whether they are still current.", panels: [EvidenceForContext] },
  { n: 3, title: "Decision", purpose: "Whether the decision still stands on current evidence, and who must review it.", panels: [DecisionValidity] },
  { n: 4, title: "Audit", purpose: "How each conclusion traces back to its source, and what changed when.", panels: [Provenance, ActivityTimeline] },
];

export function WorkflowPage() {
  return (
    <ol className="divide-y divide-line">
      {STEPS.map(({ n, title, purpose, panels }) => (
        <li key={n} aria-labelledby={`workflow-step-${n}`} className="py-4">
          <div className="px-4">
            <h3 id={`workflow-step-${n}`} className="text-body font-bold text-ink">{n} · {title}</h3>
            <p className="mt-0.5 text-caption text-muted">{purpose}</p>
          </div>
          {panels.map((Panel, i) => <Panel key={i} />)}
        </li>
      ))}
    </ol>
  );
}
