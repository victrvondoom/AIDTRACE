"use client";

// Central feature host: every integrated capability renders here, inside the one AIDTRACE shell. Switching features changes React
// state only; the address bar, session, sidebar and theme never change. The home view is the live 3D capability graph, whose cards
// are labelled from runtime probes, and clicking one opens its workspace in this same page.
import dynamic from "next/dynamic";
import { Component, useState, type ErrorInfo, type ReactNode } from "react";
import { Button, StatusBadge } from "@/components/ui";
import { getSourceSummary } from "@/lib/lab-api";
import { useFetch } from "@/lib/use-fetch";

const Loading = () => <p role="status" className="p-6 text-caption text-muted">Loading workspace…</p>;
const ConsumerWorkspace = dynamic(() => import("@/features/resolveai/consumer-workspace").then((m) => m.ConsumerWorkspace), { loading: Loading });
const GraphLabWorkspace = dynamic(() => import("@/features/graph-lab/graph-lab-workspace").then((m) => m.GraphLabWorkspace), { loading: Loading });
const SourceLibrary = dynamic(() => import("@/features/sources/source-library").then((m) => m.SourceLibrary), { loading: Loading });
const ResolveAIWorkspace = dynamic(() => import("@/components/features/resolveai/ResolveAIWorkspace").then((m) => m.ResolveAIWorkspace), { loading: Loading });
const FraudWorkspace = dynamic(() => import("@/components/features/fraud/FraudWorkspace").then((m) => m.FraudWorkspace), { loading: Loading });
const GreenChainWorkspace = dynamic(() => import("@/components/features/greenchain/GreenChainWorkspace").then((m) => m.GreenChainWorkspace), { loading: Loading });
const DriftDemoPanel = dynamic(() => import("@/app/(app)/resolveai/_components/drift-demo-panel").then((m) => m.DriftDemoPanel), { loading: Loading });
const Overview3D = dynamic(() => import("@/components/features/overview/Overview3D").then((m) => m.Overview3D), { loading: Loading });
const AgentMemoryWorkspace = dynamic(() => import("@/components/features/memory/AgentMemoryWorkspace").then((m) => m.AgentMemoryWorkspace), { loading: Loading });
const AgentOpsWorkspace = dynamic(() => import("@/components/features/agents/AgentOpsWorkspace").then((m) => m.AgentOpsWorkspace), { loading: Loading });
const SimulationsWorkspace = dynamic(() => import("@/components/features/simulations/SimulationsWorkspace").then((m) => m.SimulationsWorkspace), { loading: Loading });
const ReportsWorkspace = dynamic(() => import("@/components/features/reports/ReportsWorkspace").then((m) => m.ReportsWorkspace), { loading: Loading });
const CoordinationWorkspace = dynamic(() => import("@/components/features/coordination/CoordinationWorkspace").then((m) => m.CoordinationWorkspace), { loading: Loading });

type Status = "INTEGRATED_TESTED" | "PARTIAL";
interface Feature { id: string; name: string; category: string; backend: string; status: Status; summary: string; render: (open: (id: string) => void) => ReactNode }

const LAB = (props: React.ComponentProps<typeof GraphLabWorkspace>) => <GraphLabWorkspace embedded {...props} />;

export const FEATURES: Feature[] = [
  { id: "overview", name: "Overview", category: "Hub", backend: "/hub/capabilities", status: "INTEGRATED_TESTED",
    summary: "A live 3D graph of every capability, coloured by whether its runtime answered just now.", render: (open) => <Overview onSelect={open} /> },
  { id: "greenchain", name: "GreenChain", category: "Supply chain", backend: "/greenchain/*", status: "INTEGRATED_TESTED",
    summary: "Sustainable procurement: CatBoost-first quantile emissions scoring with legacy XGBoost support, a satellite globe of suppliers and routes, transport what-ifs, supplier graph and decision memory. Candidates are illustrative; live discovery needs provider keys.",
    render: () => <GreenChainWorkspace /> },
  { id: "resolveai", name: "Resolve", category: "Investigation", backend: "/resolveai/platform/*", status: "INTEGRATED_TESTED",
    summary: "Case investigations on the real Resolve worker with FALKOR DB: routing, retrieval over eight domain packs, evidence scoring, citations, agents, graph and reports.", render: () => <ResolveAIWorkspace /> },
  { id: "consumer", name: "Consumer Intelligence", category: "Investigation", backend: "/resolveai/consumer/*", status: "INTEGRATED_TESTED",
    summary: "Cross-domain remedy investigation on a tenant-scoped FalkorDB case graph, with revision-bound human approval.", render: () => <ConsumerWorkspace /> },
  { id: "fraud", name: "Fraud Investigation", category: "Investigation", backend: "/fraud/* + /graphlab/analyze", status: "INTEGRATED_TESTED",
    summary: "Circular money flows, rings and hubs over a transfer network. Runs on a synthetic network or your own graph JSON; no production transaction feed is connected.",
    render: () => <div className="space-y-8"><FraudWorkspace /><LAB initialScenario="fraud_ring" initialAlgo="cycles" title="Transfer-network analytics" lede="Round-tripping accounts, mule fan-in and community structure on a synthetic or pasted transfer network. Cycles are leads for a human, never proof of fraud." /></div> },
  { id: "cybersecurity", name: "Cybersecurity", category: "Investigation", backend: "/graphlab/analyze (min_cut, chokepoints, blast_radius)", status: "PARTIAL",
    summary: "Attack-path containment cuts, chokepoints and vulnerability blast radius, verified by independent reachability. Model-only: nothing real is changed.",
    render: () => <LAB initialScenario="cloud_attack" initialAlgo="min_cut" title="Cybersecurity Intelligence" lede="Find the cheapest set of links to sever between entry points and protected assets, and the single nodes every path must cross." /> },
  { id: "agents", name: "Agent Operations", category: "Agents", backend: "/agents/*", status: "INTEGRATED_TESTED",
    summary: "The four agent runtimes in one view: live status, tools, runs, handoffs and which shared interfaces each really provides.", render: () => <AgentOpsWorkspace /> },
  { id: "memory", name: "Agent Memory", category: "Agents", backend: "/agent-memory/*", status: "INTEGRATED_TESTED",
    summary: "Evidence-backed memory in the site graph: recall by other agents, dataset revision cascade, stale-approval refusal, receipts.", render: () => <AgentMemoryWorkspace /> },
  { id: "evidence-drift", name: "Evidence Drift", category: "Reasoning", backend: "/resolveai/drift/demo, /graphlab/*", status: "INTEGRATED_TESTED",
    summary: "Source supersession, memory invalidation, action suspension, decision gates and as-of time travel on the persisted site graph.",
    render: () => <div className="space-y-6"><DriftDemoPanel /><LAB initialScenario="plant_evidence" initialAlgo="decision_gate" title="Decision gates & impact" lede="Run blast radius, decision gate and as-of engines on the evidence graph, including your site's persisted FalkorDB graph." /></div> },
  { id: "graph", name: "Graph Intelligence", category: "Reasoning", backend: "/graphlab/*", status: "INTEGRATED_TESTED",
    summary: "Any engine on any graph, viewed as a network, layers, rings, matrix, timeline or table.", render: () => <LAB title="Graph Explorer" lede="Choose a scenario, your site's evidence graph or your own JSON, then any of the ten engines." /> },
  { id: "simulations", name: "Simulations", category: "Reasoning", backend: "/greenchain/*, /agent-memory/*, /resolveai/platform/search", status: "INTEGRATED_TESTED",
    summary: "Supplier removal, transport and weighting counterfactuals, dataset-revision previews, graph impact previews and domain-pack comparisons. Nothing is written.", render: () => <SimulationsWorkspace /> },
  { id: "reports", name: "Reports", category: "Reasoning", backend: "/resolveai/platform/report, /agent-memory/greenchain/report", status: "INTEGRATED_TESTED",
    summary: "Case reports, procurement memos and approval receipts, written only from what ran and exportable.", render: () => <ReportsWorkspace /> },
  { id: "capabilities", name: "Capability Workbench", category: "Registry", backend: "/sources/*", status: "INTEGRATED_TESTED",
    summary: "The 98 source repositories, their READMEs and an evidence-based ledger of what AIDTRACE has built from each.", render: () => <SourceLibrary /> },
  { id: "coordination", name: "Multi-Agent Coordination & Swarm Brain", category: "Investigation", backend: "/coordination/*", status: "INTEGRATED_TESTED",
    summary: "Coordinator agent with DAG dependency scheduling, parallel Worker A (Evidence) & Worker B (Validation), Company Brain persistence, verified unlearning, and Capability Packs A through I.",
    render: () => <CoordinationWorkspace /> },
];

/** Work that is NOT done. Listed here so the product never advertises it as operational. */
const NOT_DONE = [
  ["Real sign-in", "Verified only with the development bypass: no Supabase project is configured here, so a real login has not been exercised."],
  ["Live model reasoning in Resolve", "Without a model key its LLM agents return placeholders. Retrieval, scoring, citations and the FALKOR DB graph run for real; nothing generated is shown as analysis."],
  ["GreenChain live discovery and scenario prompts", "Need Dedalus, Brave and model keys. Candidates are illustrative, and certifications are unverified claims."],
  ["MCP transport for Track 01", "Cannot import beside AIDTRACE's pinned pydantic; it would need its own private process."],
  ["Production data feeds", "Fraud runs on a synthetic network and cybersecurity on a supplied graph; no live security or transaction feed is connected."],
  ["~60 of the 98 research mechanisms", "READMEs are in the library; their mechanisms are not implemented (see the ledger)."],
];

export class Boundary extends Component<{ children: ReactNode; label: string }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  componentDidCatch(error: Error, info: ErrorInfo) { console.error("feature crashed", this.props.label, error, info.componentStack); }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div role="alert" className="border-l-2 border-danger bg-surface p-5 text-caption">
        <p className="font-semibold text-danger">{this.props.label} stopped unexpectedly.</p>
        <p className="mt-1 text-muted">The rest of AIDTRACE is unaffected. {this.state.error.message}</p>
        <Button className="mt-3" onClick={() => this.setState({ error: null })}>Try again</Button>
      </div>
    );
  }
}

function Overview({ onSelect }: { onSelect: (id: string) => void }) {
  const summary = useFetch(getSourceSummary);
  const s = summary.status === "live" ? summary.data : null;
  return (
    <div className="space-y-6">
      <Boundary label="The 3D overview"><Overview3D onOpen={onSelect} /></Boundary>
      {s && <p className="text-caption text-muted">{s.repositories} source repositories · {s.readme_present} READMEs collected · {s.engines} engines built · {s.integrated_repositories} repositories mapped to an engine.</p>}
      <details className="border border-line bg-surface p-4">
        <summary className="cursor-pointer text-body font-semibold">What is not done yet <StatusBadge tone="caution">{NOT_DONE.length}</StatusBadge></summary>
        <ul className="mt-3 space-y-2 text-caption">{NOT_DONE.map(([k, v]) => <li key={k}><strong>{k}</strong><span className="block text-muted">{v}</span></li>)}</ul>
      </details>
    </div>
  );
}

const KEY = "kairos.hub.feature";
function initialFeature(): string {
  try { const saved = window.sessionStorage.getItem(KEY); if (saved && FEATURES.some((f) => f.id === saved)) return saved; } catch { /* storage blocked */ }
  return "overview";
}

export function FeatureHost() {
  const [active, setActive] = useState(initialFeature);
  const feature = FEATURES.find((f) => f.id === active) ?? FEATURES[0];
  function select(id: string) {
    const next = FEATURES.some((f) => f.id === id) ? id : "overview";
    setActive(next);
    try { window.sessionStorage.setItem(KEY, next); } catch { /* storage blocked */ }
    window.scrollTo?.({ top: 0 });
  }
  return (
    <div className="mx-auto grid max-w-[1500px] gap-5 lg:grid-cols-[220px_minmax(0,1fr)]">
      <nav aria-label="Intelligence workspaces" className="flex gap-1 overflow-x-auto lg:flex-col lg:overflow-visible">
        {FEATURES.map((f) => (
          <button key={f.id} type="button" onClick={() => select(f.id)} aria-current={f.id === active ? "page" : undefined}
            className={`min-h-11 shrink-0 border px-3 text-left text-caption ${f.id === active ? "border-ink bg-surface-2 font-semibold" : "border-line bg-surface hover:bg-surface-2"}`}>
            {f.name}
            {f.status === "PARTIAL" && <span className="ml-2 text-micro font-normal text-muted">partial</span>}
          </button>
        ))}
      </nav>
      <section className="min-w-0" aria-label={feature.name}>
        <p className="mb-3 text-micro text-muted">{feature.category} · {feature.backend}</p>
        <Boundary key={feature.id} label={feature.name}>{feature.render(select)}</Boundary>
      </section>
    </div>
  );
}
