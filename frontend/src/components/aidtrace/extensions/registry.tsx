"use client";

// The one registry of workspace extensions. Every legacy page and hub feature that is still useful appears here exactly once, in a category, with the
// backend it depends on and the permission needed to open it. Heavy bodies load lazily, so the workspace itself starts without any of them.
import dynamic from "next/dynamic";
import type { ComponentType } from "react";
import { Boundary, FEATURES } from "@/features/feature-host";
import type { IconName } from "@/components/icon";
import { routeAllowed } from "@/components/use-role";
import type { Role } from "@/lib/types";

export const EXTENSION_CATEGORIES = [
  "Supply Chain Intelligence", "Investigation & Intelligence", "Evidence & Knowledge", "Decision Governance", "Specialist AI Engines",
] as const;
export type ExtensionCategory = (typeof EXTENSION_CATEGORIES)[number];

const Loading = () => <p role="status" className="p-6 text-caption text-muted">Loading…</p>;
const ConnectedGraph = dynamic(() => import("./native").then((m) => m.ConnectedGraph), { loading: Loading });
const RiskAnalytics = dynamic(() => import("./native").then((m) => m.RiskAnalytics), { loading: Loading });
const Provenance = dynamic(() => import("./native").then((m) => m.Provenance), { loading: Loading });
const ActivityTimeline = dynamic(() => import("./native").then((m) => m.ActivityTimeline), { loading: Loading });
const DecisionValidity = dynamic(() => import("./native").then((m) => m.DecisionValidity), { loading: Loading });
const EvidenceForContext = dynamic(() => import("./native").then((m) => m.EvidenceForContext), { loading: Loading });
const WorkflowPage = dynamic(() => import("./workflow").then((m) => m.WorkflowPage), { loading: Loading });

/** A hub feature (GreenChain, Resolve, Graph Lab, …) rendered as a tab body. */
function featureBody(id: string): ComponentType {
  const Body = () => {
    const feature = FEATURES.find((f) => f.id === id);
    if (!feature) return <p role="alert" className="p-4 text-caption text-danger">The “{id}” engine is not registered.</p>;
    return <div className="p-4"><Boundary label={feature.name}>{feature.render(() => {})}</Boundary></div>;
  };
  Body.displayName = `Feature(${id})`;
  return Body;
}

export interface ExtensionTab {
  id: string; label: string;
  /** A migrated legacy page. Navigation inside it stays in the workspace. */
  path?: string;
  /** A native body. Exactly one of `path` and `body` is set. */
  body?: ComponentType;
}

export interface AidtraceExtension {
  id: string;
  title: string;
  category: ExtensionCategory;
  icon: IconName;
  description: string;
  keywords: string[];
  tabs: ExtensionTab[];
  /** Shown above the tabs, for context-aware summaries that belong to the whole extension. */
  header?: ComponentType;
  /** The route whose access rule decides who may open this (see ROUTE_ACCESS). Absent means any signed-in workspace user. */
  permissionPath?: string;
  /** The backend routes it calls, for the migration ledger and the unavailable message. */
  backend: string[];
  /** True when it reads the shared selection and changes with it. */
  contextual: boolean;
  /** Honest scope notes (for example, a plant-specific engine) shown in the extension. */
  scope?: string;
  /** "partial" marks engines whose real capability is narrower than their name suggests. */
  status?: "partial";
}

const f = (id: string, label: string): ExtensionTab => ({ id: `feature-${id}`, label, body: featureBody(id) });

export const EXTENSIONS: AidtraceExtension[] = [
  // ---- The single workflow: every graph-backed panel on one page, in review order.
  { id: "workflow", title: "Investigation Workflow", category: "Investigation & Intelligence", icon: "target", contextual: true, permissionPath: "/hub",
    description: "One page from risk to audit: investigate, check the evidence, review the decision and trace its provenance, all from the FalkorDB graph.",
    keywords: ["workflow", "investigate", "evidence", "decision", "audit", "risk", "provenance", "timeline", "graph"],
    tabs: [{ id: "workflow", label: "Workflow", body: WorkflowPage }], backend: ["/agent-memory/snapshot", "/graphlab/*"] },
  // ---- A. Supply Chain Intelligence
  { id: "greenchain", title: "GreenChain", category: "Supply Chain Intelligence", icon: "pulse", contextual: false, permissionPath: "/hub",
    description: "Supplier scoring and discovery, emissions, transport comparison, ranking, routes and what-if scenarios.", keywords: ["supplier", "scoring", "emissions", "transport", "ranking", "what-if", "procurement", "carbon"],
    tabs: [f("greenchain", "Scoring & routes"), f("simulations", "What-if simulations")], backend: ["/greenchain/*", "/agent-memory/*"] },
  { id: "supplier-registry", title: "Supplier Registry", category: "Supply Chain Intelligence", icon: "target", contextual: true, permissionPath: "/assets",
    description: "Asset and facility records with ownership, documents and event history, plus registration and identity confirmation.", keywords: ["asset", "facility", "supplier", "registry", "ownership", "records", "register"],
    scope: "These are asset and facility records. The illustrative suppliers on the globe are scenario data and are not registry records.",
    tabs: [{ id: "registry", label: "Registry", path: "/assets" }, { id: "register", label: "Register", path: "/assets/register" }, { id: "identity", label: "Identity confirmation", path: "/assets/bootstrap" }], backend: ["/assets/*"] },
  { id: "risk-analytics", title: "Risk Analytics", category: "Supply Chain Intelligence", icon: "warning-circle", contextual: true, permissionPath: "/hub",
    description: "Connected records, stale memories, blocked decisions, pending reviews and evidence completeness for the selected supplier, plus the governance queues.", keywords: ["risk", "analytics", "dashboard", "overview", "stale", "blocked", "reviews", "conflicts", "trend"],
    tabs: [{ id: "analytics", label: "Analytics", body: RiskAnalytics }], backend: ["/agent-memory/snapshot", "/governance/*", "/compliance/dashboard", "/events"] },
  // ---- B. Investigation & Intelligence
  { id: "assistant", title: "Agent Assistant", category: "Investigation & Intelligence", icon: "file-text", contextual: false, permissionPath: "/copilot",
    description: "Ask questions of the document vault and get source-backed answers, with uncertainty and refusals shown.", keywords: ["copilot", "ask", "question", "answer", "retrieval", "documents", "assistant", "citations"],
    tabs: [{ id: "assistant", label: "Assistant", path: "/copilot" }], backend: ["/search/*"] },
  { id: "rca", title: "Root Cause Analysis", category: "Investigation & Intelligence", icon: "target", contextual: false, permissionPath: "/rca",
    description: "Ranks likely causes of a failure from evidence, with supporting documents and a timeline.", keywords: ["rca", "root cause", "failure", "hypothesis", "analysis", "incident"],
    scope: "Built for equipment-failure analysis on maintenance records (failure codes, work orders). It has not been adapted to supplier-disruption analysis.",
    tabs: [{ id: "rca", label: "Analysis", path: "/rca" }], backend: ["/rca/*"] },
  { id: "connected-graph", title: "Connected Graph", category: "Investigation & Intelligence", icon: "graph", contextual: true, permissionPath: "/hub",
    description: "Dependency and impact exploration over the persisted FalkorDB graph, focused on the selected supplier, with filters, entity details and temporal views.", keywords: ["graph", "dependencies", "impact", "falkordb", "entity", "temporal", "relationships", "blast radius"],
    tabs: [{ id: "dependencies", label: "Dependencies", body: ConnectedGraph }, { id: "entities", label: "Entity graph", path: "/graph" }, f("graph", "Graph engines")], backend: ["/graphlab/*", "/graph/*"] },
  { id: "events", title: "Event Timeline", category: "Investigation & Intelligence", icon: "pulse", contextual: true, permissionPath: "/events",
    description: "Searchable events with their sources, chronology and linked incidents, plus this investigation's activity.", keywords: ["events", "timeline", "history", "incidents", "activity", "chronology", "cross-site"],
    tabs: [{ id: "activity", label: "Investigation activity", body: ActivityTimeline }, { id: "events", label: "Events", path: "/events" }, { id: "cross-site", label: "Cross-site patterns", path: "/overview/cross-site" }], backend: ["/events/*", "/agent-memory/snapshot"] },
  // ---- C. Evidence & Knowledge
  { id: "evidence-vault", title: "Evidence Vault", category: "Evidence & Knowledge", icon: "file-text", contextual: true, permissionPath: "/documents", header: EvidenceForContext,
    description: "Document ingestion, source records, extraction review, citations, revision comparison and evidence attachments.", keywords: ["documents", "evidence", "ingest", "upload", "citations", "extraction", "compare", "sources", "vault"],
    tabs: [{ id: "library", label: "Library", path: "/documents" }, { id: "ingest", label: "Ingest", path: "/documents/ingest" }, { id: "compare", label: "Compare revisions", path: "/documents/compare" }], backend: ["/documents/*"] },
  { id: "coverage", title: "Evidence Coverage", category: "Evidence & Knowledge", icon: "shield-check", contextual: false, permissionPath: "/overview/coverage",
    description: "Missing evidence, incomplete records, coverage metrics and confidence gaps.", keywords: ["coverage", "missing", "gaps", "completeness", "confidence", "evidence"],
    tabs: [{ id: "coverage", label: "Coverage", path: "/overview/coverage" }], backend: ["/compliance/*", "/assets/*"] },
  { id: "knowledge-transfer", title: "Knowledge Transfer", category: "Evidence & Knowledge", icon: "file-text", contextual: false, permissionPath: "/offboarding",
    description: "Structured knowledge-capture sessions for departing experts. An optional, advanced extension.", keywords: ["offboarding", "handover", "knowledge", "capture", "expert", "sessions"],
    tabs: [{ id: "programmes", label: "Programmes", path: "/offboarding" }], backend: ["/offboarding/*"] },
  { id: "projects", title: "Investigation Workspaces", category: "Evidence & Knowledge", icon: "target", contextual: false, permissionPath: "/projects",
    description: "Organise investigations, scenarios, supporting documents and case history.", keywords: ["projects", "cases", "investigations", "scenarios", "workspaces", "history"],
    tabs: [{ id: "projects", label: "Workspaces", path: "/projects" }], backend: ["/projects/*"] },
  { id: "field-capture", title: "Field Capture", category: "Evidence & Knowledge", icon: "pulse", contextual: false,
    description: "Voice notes and deviation flags captured on site.", keywords: ["voice", "field", "deviation", "capture", "observation", "inspection"],
    tabs: [{ id: "voice", label: "Voice note", path: "/field/voice" }, { id: "deviation", label: "Deviation flag", path: "/field/deviation" }], backend: ["/field/*", "/elicitation/*"] },
  // ---- D. Decision Governance
  { id: "governance", title: "Governance", category: "Decision Governance", icon: "shield-check", contextual: true, permissionPath: "/governance", header: DecisionValidity,
    description: "Decision validity and approvals, conflicting claims, quarantined evidence, controlled changes and review deadlines.", keywords: ["governance", "approval", "conflicts", "quarantine", "change", "moc", "sla", "review", "decision", "validity", "drift"],
    tabs: [{ id: "queues", label: "Queues", path: "/governance" }, { id: "conflicts", label: "Conflicts", path: "/governance/conflicts" }, { id: "quarantine", label: "Quarantine", path: "/governance/quarantine" },
      { id: "change", label: "Change control", path: "/governance/moc" }, { id: "deadlines", label: "Deadlines", path: "/governance/sla" }], backend: ["/governance/*", "/agent-memory/*"] },
  { id: "audit", title: "Audit & Provenance", category: "Decision Governance", icon: "shield-check", contextual: true, permissionPath: "/audit",
    description: "Chronological audit history, evidence lineage, user and agent actions, approval receipts and source changes.", keywords: ["audit", "provenance", "lineage", "history", "receipts", "actions", "trail"],
    tabs: [{ id: "provenance", label: "Provenance", body: Provenance }, { id: "audit", label: "Audit trail", path: "/audit" }], backend: ["/audit/*", "/agent-memory/snapshot"] },
  { id: "compliance", title: "Compliance & Controls", category: "Decision Governance", icon: "shield-check", contextual: false, permissionPath: "/compliance",
    description: "Applicable controls, regulatory mappings, evidence-supported checks, audit packs and non-conformance handling.", keywords: ["compliance", "controls", "regulatory", "audit pack", "nonconformance", "oisd", "iso 45001"],
    scope: "The bundled frameworks (OISD, ISO 45001, PESO) are industrial-plant regulations. They are not supply-chain or cybersecurity requirements.",
    tabs: [{ id: "coverage", label: "Coverage", path: "/compliance" }, { id: "pack", label: "Audit pack", path: "/compliance/audit-pack" }, { id: "nc", label: "Non-conformance", path: "/compliance/nonconformance" }], backend: ["/compliance/*"] },
  { id: "notices", title: "Notices & Acknowledgements", category: "Decision Governance", icon: "warning-circle", contextual: false, permissionPath: "/briefs",
    description: "Notices with their evidence, required acknowledgements and warnings.", keywords: ["briefs", "notices", "acknowledge", "warnings", "inbox", "alerts"],
    tabs: [{ id: "inbox", label: "Inbox", path: "/briefs" }], backend: ["/briefs/*"] },
  // ---- E. Specialist AI Engines
  { id: "resolveai", title: "Resolve", category: "Specialist AI Engines", icon: "target", contextual: false, permissionPath: "/hub",
    description: "Case investigation with retrieval, evidence scoring, citations, specialist agents and reports; plus cross-domain remedy investigation on a tenant-scoped FalkorDB case graph.", keywords: ["resolve", "case", "investigation", "agents", "retrieval", "remedy", "consumer", "falkordb"],
    tabs: [f("resolveai", "Investigations"), f("consumer", "Remedy investigation")], backend: ["/resolveai/*"] },
  { id: "cyberflow", title: "Cybersecurity Analysis", category: "Specialist AI Engines", icon: "warning-circle", contextual: false, permissionPath: "/hub", status: "partial",
    description: "Attack-path containment cuts, chokepoints and vulnerability blast radius over a supplied graph. Model-only: no live security feed.", keywords: ["cyber", "cyberflow", "security", "attack path", "min cut", "chokepoint", "vulnerability"],
    scope: "Runs on a synthetic or supplied graph. No live security or telemetry feed is connected.", tabs: [f("cybersecurity", "Attack paths")], backend: ["/graphlab/analyze"] },
  { id: "track1", title: "Connected-Risk Analysis (Track 01)", category: "Specialist AI Engines", icon: "graph", contextual: false, permissionPath: "/hub",
    description: "Multi-hop link traversal, ring and hub detection, freeze proposals and human authorisation on FalkorDB.", keywords: ["track 01", "fraud", "ring", "connected", "traversal", "proposal", "authorisation"],
    scope: "Runs on a synthetic transfer network. No production transaction feed is connected.", tabs: [f("fraud", "Investigation")], backend: ["/fraud/*", "/graphlab/analyze"] },
  { id: "agent-memory", title: "Agent Memory", category: "Specialist AI Engines", icon: "graph", contextual: false, permissionPath: "/hub",
    description: "Evidence-backed memory in the site graph: recall by other agents, dataset revision cascade, stale-approval refusal and receipts.", keywords: ["memory", "recall", "agents", "stale", "receipts", "cascade", "falkordb"],
    tabs: [f("memory", "Memory")], backend: ["/agent-memory/*"] },
  { id: "evidence-drift", title: "Evidence Drift", category: "Specialist AI Engines", icon: "warning-circle", contextual: false, permissionPath: "/hub",
    description: "Source supersession, memory invalidation, action suspension, decision gates and as-of time travel on the persisted graph.", keywords: ["drift", "supersede", "invalidate", "decision gate", "time travel", "as-of"],
    tabs: [f("evidence-drift", "Drift & gates")], backend: ["/resolveai/drift/demo", "/graphlab/*"] },
  { id: "agents", title: "Agent Operations", category: "Specialist AI Engines", icon: "pulse", contextual: false, permissionPath: "/hub",
    description: "The four agent runtimes: live status, tools, runs and handoffs.", keywords: ["agents", "runtimes", "tools", "runs", "handoffs", "operations"],
    tabs: [f("agents", "Runtimes")], backend: ["/agents/*"] },
  { id: "reports", title: "Reports", category: "Specialist AI Engines", icon: "file-text", contextual: false, permissionPath: "/hub",
    description: "Case reports, procurement memos and approval receipts, written only from what ran.", keywords: ["reports", "memo", "export", "receipts"],
    tabs: [f("reports", "Reports")], backend: ["/resolveai/platform/report", "/agent-memory/greenchain/report"] },
  { id: "capability-workbench", title: "Capability Workbench", category: "Specialist AI Engines", icon: "file-text", contextual: false, permissionPath: "/hub",
    description: "The source repositories behind AIDTRACE's engines, their READMEs and an evidence-based ledger of what was built from each.", keywords: ["sources", "repositories", "ledger", "capabilities", "engines"],
    tabs: [f("capabilities", "Ledger")], backend: ["/sources/*"] },
  { id: "system-health", title: "Service Health", category: "Specialist AI Engines", icon: "pulse", contextual: false, permissionPath: "/system-health",
    description: "Connectivity and health of every backing service.", keywords: ["health", "services", "status", "infrastructure", "connectivity"],
    tabs: [{ id: "health", label: "Services", path: "/system-health" }], backend: ["/health/*"] },
];

export const extensionById = (id: string) => EXTENSIONS.find((e) => e.id === id) ?? null;

/** Pages whose data lives in Neo4j, Qdrant, Elasticsearch or Supabase. Kept registered, so links still open them, but left out of the launcher
 *  while those stores are not running here: listing them only showed empty pages. */
export const NEEDS_EXTERNAL_STORES = new Set([
  "supplier-registry", "rca", "evidence-vault", "coverage", "knowledge-transfer", "projects", "field-capture", "governance", "compliance", "notices",
]);

/** What the launcher lists: everything except the pages above. */
export const LAUNCHER_EXTENSIONS = EXTENSIONS.filter((e) => !NEEDS_EXTERNAL_STORES.has(e.id));

/** Can this role open the extension? The route access rules decide, exactly as they did for the old pages. */
export function isAvailable(ext: AidtraceExtension, role: Role): boolean {
  return ext.permissionPath ? routeAllowed(ext.permissionPath, role) : true;
}

/** Case-insensitive search over title, category, description and keywords; the best matches come first. */
export function searchExtensions(list: AidtraceExtension[], query: string): AidtraceExtension[] {
  const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (!terms.length) return list;
  const scored = list.map((e) => {
    let score = 0;
    for (const t of terms) {
      const title = e.title.toLowerCase();
      if (title.includes(t)) score += title.startsWith(t) ? 6 : 4;
      else if (e.keywords.some((k) => k.includes(t))) score += 3;
      else if (e.category.toLowerCase().includes(t) || e.description.toLowerCase().includes(t)) score += 1;
      else return { e, score: -1 };
    }
    return { e, score };
  });
  return scored.filter((s) => s.score > 0).sort((a, b) => b.score - a.score).map((s) => s.e);
}

/** The tab that shows `path`: the longest tab path that prefixes it. */
export function tabForPath(ext: AidtraceExtension, path: string): ExtensionTab | null {
  const clean = path.split("?")[0];
  let best: ExtensionTab | null = null;
  for (const t of ext.tabs) {
    if (!t.path) continue;
    if ((clean === t.path || clean.startsWith(`${t.path}/`)) && (!best || t.path.length > (best.path?.length ?? 0))) best = t;
  }
  return best;
}
