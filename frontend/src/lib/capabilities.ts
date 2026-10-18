import type { IconName } from "@/components/icon";

export const CAPABILITY_GROUPS = [
  { id: "operations", title: "Supply Chain Operations", icon: "pulse", description: "Suppliers, facilities, shipments and the signals that move them.", href: "/assets" },
  { id: "investigation", title: "Risk Investigations", icon: "target", description: "Trace a risk from source evidence to the decisions it affects.", href: "/rca" },
  { id: "intelligence", title: "Agent Memory & Graph", icon: "graph", description: "FalkorDB agent memory, specialist agents and graph reasoning.", href: "/resolveai" },
  { id: "knowledge", title: "Evidence & Models", icon: "file-text", description: "Curate trusted supplier evidence and inspect model readiness.", href: "/documents" },
  { id: "governance", title: "Decision Governance", icon: "shield-check", description: "Resolve conflicting evidence, approve changes and keep decision history.", href: "/governance" },
  { id: "cyber", title: "Cyber Supply-Chain Risk", icon: "warning-circle", description: "Cyber exposure in suppliers and connected services, tied to procurement decisions.", href: "/resolveai#cyber" },
] as const satisfies ReadonlyArray<{ id: string; title: string; icon: IconName; description: string; href: string }>;

export type CapabilityGroup = typeof CAPABILITY_GROUPS[number]["id"];
export type Capability = {
  title: string;
  description: string;
  href: string;
  group: CapabilityGroup;
  kind: "workspace" | "integration" | "preview";
};

// A product directory, not a health registry. A workspace entry means a route exists;
// service availability and permissions are still resolved by its destination.
export const CAPABILITIES: readonly Capability[] = [
  { title: "Risk Overview", description: "Decision KPIs, attention queue and recent supply-chain signals.", href: "/overview", group: "operations", kind: "workspace" },
  { title: "Supplier & Asset Inventory", description: "Suppliers, facilities and assets with ownership, evidence and events.", href: "/assets", group: "operations", kind: "workspace" },
  { title: "Register Supplier or Asset", description: "Create a governed supplier or facility record.", href: "/assets/register", group: "operations", kind: "workspace" },
  { title: "Master Data Bootstrap", description: "Bootstrap supplier master data and canonical identities.", href: "/assets/bootstrap", group: "operations", kind: "workspace" },
  { title: "Supply Events", description: "Search disruption and risk events with their source and timeline.", href: "/events", group: "operations", kind: "workspace" },
  { title: "Decision Briefs", description: "Review procurement decisions, evidence and required acknowledgements.", href: "/briefs", group: "operations", kind: "workspace" },
  { title: "Voice Workspace", description: "Capture field observations by voice for supplier and site inspections.", href: "/field/voice", group: "operations", kind: "workspace" },
  { title: "Field Deviations", description: "Report observations that differ from approved supplier requirements.", href: "/field/deviation", group: "operations", kind: "workspace" },
  { title: "Network State", description: "Review operating state and governed state changes.", href: "/overview/plant-state", group: "operations", kind: "workspace" },
  { title: "Root Cause Analysis", description: "Investigate disruptions with traceable supporting evidence.", href: "/rca", group: "investigation", kind: "workspace" },
  { title: "Evidence Graph", description: "Explore relationships between suppliers, assets, documents and events.", href: "/graph", group: "investigation", kind: "workspace" },
  { title: "AIDTRACE Copilot", description: "Ask supply-chain risk questions and inspect source-grounded answers.", href: "/copilot", group: "investigation", kind: "workspace" },
  { title: "Cross-site Patterns", description: "Inspect recurring risks across permitted sites and suppliers.", href: "/overview/cross-site", group: "investigation", kind: "workspace" },
  { title: "Coverage Analysis", description: "Inspect evidence coverage and missing supplier knowledge.", href: "/overview/coverage", group: "investigation", kind: "workspace" },
  { title: "Connected-Risk Agent", description: "Multi-hop link traversal across connected suppliers and services, with human-approved holds on FalkorDB.", href: "/track1", group: "investigation", kind: "workspace" },
  { title: "Disruption Remedy Simulation", description: "ResolveAI what-if graph simulations for remedies across carriers, suppliers and insurers.", href: "/resolveai", group: "investigation", kind: "workspace" },
  { title: "ResolveAI Reasoning", description: "The Reasoning and Decision System that powers AIDTRACE investigations.", href: "/resolveai", group: "intelligence", kind: "integration" },
  { title: "Agent Map", description: "Specialist responsibilities, handoffs and human review boundaries.", href: "/resolveai#agents", group: "intelligence", kind: "integration" },
  { title: "Agent Memory & FalkorDB", description: "Why the agent made each decision, and when it stops being valid.", href: "/resolveai#memory", group: "intelligence", kind: "integration" },
  { title: "Intelligence Hub", description: "Agent memory, cyber risk, evidence drift and graph exploration in one workspace; switching never leaves the page.", href: "/hub", group: "intelligence", kind: "workspace" },
  { title: "Graph Lab", description: "Run graph-reasoning engines on a scenario, your site's evidence graph or your own JSON, and view the result six ways.", href: "/graph-lab", group: "intelligence", kind: "workspace" },
  { title: "Capability Workbench", description: "Research repositories and an evidence-based ledger of what AIDTRACE has built from each.", href: "/capabilities", group: "knowledge", kind: "workspace" },
  { title: "Source Library", description: "Browse the research repositories and READMEs behind AIDTRACE capabilities.", href: "/sources", group: "knowledge", kind: "workspace" },
  { title: "System Health", description: "Inspect service connectivity and infrastructure health.", href: "/system-health", group: "intelligence", kind: "workspace" },
  { title: "System Settings", description: "Workspace preferences and account settings.", href: "/settings", group: "intelligence", kind: "workspace" },
  { title: "Document Vault", description: "Supplier documents, extraction review, citations and topology.", href: "/documents", group: "knowledge", kind: "workspace" },
  { title: "Document Ingestion", description: "Bring source material into the governed evidence workflow.", href: "/documents/ingest", group: "knowledge", kind: "workspace" },
  { title: "Document Comparison", description: "Compare revisions and inspect changed claims.", href: "/documents/compare", group: "knowledge", kind: "workspace" },
  { title: "Evidence Curation", description: "Annotations, corrections and validation corpus summaries.", href: "/resolveai#curation", group: "knowledge", kind: "integration" },
  { title: "Models & Fine-tuning", description: "Configured model roles and fine-tuning integration readiness.", href: "/resolveai#models", group: "knowledge", kind: "integration" },
  { title: "Model Evaluation Gate", description: "Validation corpus and model promotion criteria.", href: "/governance/model-gate", group: "knowledge", kind: "workspace" },
  { title: "Projects", description: "Organize sourcing projects and linked evidence.", href: "/projects", group: "knowledge", kind: "workspace" },
  { title: "Knowledge Handover", description: "Capture departing procurement and site expertise.", href: "/offboarding", group: "knowledge", kind: "workspace" },
  { title: "Governance Center", description: "Review queues and policies governing supplier evidence and decisions.", href: "/governance", group: "governance", kind: "workspace" },
  { title: "Conflict Resolution", description: "Compare competing supplier claims and record accountable decisions.", href: "/governance/conflicts", group: "governance", kind: "workspace" },
  { title: "Evidence Quarantine", description: "Review held evidence before it can support a decision.", href: "/governance/quarantine", group: "governance", kind: "workspace" },
  { title: "SLA Monitoring", description: "Track overdue review and resolution obligations.", href: "/governance/sla", group: "governance", kind: "workspace" },
  { title: "Management of Change", description: "Review, approve and track controlled changes.", href: "/governance/moc", group: "governance", kind: "workspace" },
  { title: "Timestamp Drift", description: "Inspect timestamp consistency and clock-related anomalies.", href: "/governance/timestamp-drift", group: "governance", kind: "workspace" },
  { title: "Circuit Breakers", description: "Inspect safeguards and automation stop conditions.", href: "/governance/circuit-breaker", group: "governance", kind: "workspace" },
  { title: "Push Volume Gate", description: "Review volume safeguards before pushing changes.", href: "/governance/push-volume-gate", group: "governance", kind: "workspace" },
  { title: "Compliance Coverage", description: "Evidence-backed requirements and supplier compliance gaps.", href: "/compliance", group: "governance", kind: "workspace" },
  { title: "Nonconformance", description: "Track findings that do not satisfy required controls.", href: "/compliance/nonconformance", group: "governance", kind: "workspace" },
  { title: "Audit Pack", description: "Prepare an evidence package for compliance review.", href: "/compliance/audit-pack", group: "governance", kind: "workspace" },
  { title: "Audit Trail", description: "Inspect the chronology of recorded actions and decisions.", href: "/audit", group: "governance", kind: "workspace" },
  { title: "Dependency Risk Discovery", description: "Workflow preview: find suppliers that depend on a newly risky service.", href: "/resolveai#cyber", group: "cyber", kind: "preview" },
  { title: "Evidence Drift & Memory", description: "Workflow preview: compare new evidence with the memory behind an earlier approval.", href: "/resolveai#cyber", group: "cyber", kind: "preview" },
  { title: "Response & Verification", description: "Workflow preview: authorize a response and independently verify its outcome.", href: "/resolveai#cyber", group: "cyber", kind: "preview" },
  { title: "Network Evidence Adapter", description: "Planned adapter for network evidence and chain of custody.", href: "/resolveai#cyber", group: "cyber", kind: "preview" },
];

export const CAPABILITY_KIND_LABELS = {
  workspace: "Workspace",
  integration: "Integration",
  preview: "Workflow preview",
} as const;
