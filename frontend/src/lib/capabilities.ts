import type { IconName } from "@/components/icon";

export const CAPABILITY_GROUPS = [
  { id: "operations", title: "Plant Operations", icon: "pulse", description: "Your plant, people, assets and operational signals.", href: "/assets" },
  { id: "investigation", title: "Investigations", icon: "target", description: "Follow a question from source evidence to a defensible conclusion.", href: "/rca" },
  { id: "intelligence", title: "Agents & Infrastructure", icon: "graph", description: "Explore ResolveAI, agent responsibilities and reasoning infrastructure.", href: "/resolveai" },
  { id: "knowledge", title: "Data & Models", icon: "file-text", description: "Curate trusted knowledge and inspect model readiness.", href: "/documents" },
  { id: "governance", title: "Governance & Assurance", icon: "shield-check", description: "Resolve conflicts, review changes and preserve decision history.", href: "/governance" },
  { id: "cyber", title: "Cyber & Fraud", icon: "warning-circle", description: "Explore how evidence and agent memory can support cyber defense.", href: "/resolveai#cyber" },
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
  { title: "Plant Overview", description: "Operational KPIs, attention queue and recent signals.", href: "/overview", group: "operations", kind: "workspace" },
  { title: "Asset Inventory", description: "Assets, ownership, documents, events and detailed asset workspaces.", href: "/assets", group: "operations", kind: "workspace" },
  { title: "Register Asset", description: "Create a governed asset record.", href: "/assets/register", group: "operations", kind: "workspace" },
  { title: "Asset Bootstrap", description: "Bootstrap master data and canonical asset identities.", href: "/assets/bootstrap", group: "operations", kind: "workspace" },
  { title: "Operational Events", description: "Search events and inspect their source and timeline.", href: "/events", group: "operations", kind: "workspace" },
  { title: "Work Briefs", description: "Review work orders, evidence and required acknowledgements.", href: "/briefs", group: "operations", kind: "workspace" },
  { title: "Voice Workspace", description: "Voice capture, work-order sessions and guided elicitation.", href: "/field/voice", group: "operations", kind: "workspace" },
  { title: "Field Deviations", description: "Report observations that differ from approved instructions.", href: "/field/deviation", group: "operations", kind: "workspace" },
  { title: "Plant State", description: "Review operating state and governed state changes.", href: "/overview/plant-state", group: "operations", kind: "workspace" },
  { title: "Root Cause Analysis", description: "Investigate failures with traceable supporting evidence.", href: "/rca", group: "investigation", kind: "workspace" },
  { title: "Evidence Graph", description: "Explore relationships between assets, documents and events.", href: "/graph", group: "investigation", kind: "workspace" },
  { title: "Kairos Copilot", description: "Ask questions and inspect source-grounded answers.", href: "/copilot", group: "investigation", kind: "workspace" },
  { title: "Cross-site Patterns", description: "Inspect recurring patterns across permitted sites.", href: "/overview/cross-site", group: "investigation", kind: "workspace" },
  { title: "Coverage Analysis", description: "Inspect evidence coverage and missing asset knowledge.", href: "/overview/coverage", group: "investigation", kind: "workspace" },
  { title: "ResolveAI RDS", description: "Reasoning and Decision System inside Kairos.", href: "/resolveai", group: "intelligence", kind: "integration" },
  { title: "Agent Map", description: "Specialist responsibilities, handoffs and human review boundaries.", href: "/resolveai#agents", group: "intelligence", kind: "integration" },
  { title: "Memory & FalkorDB", description: "Reasoning infrastructure status and evidence memory contracts.", href: "/resolveai#memory", group: "intelligence", kind: "integration" },
  { title: "System Health", description: "Inspect service connectivity and infrastructure health.", href: "/system-health", group: "intelligence", kind: "workspace" },
  { title: "System Settings", description: "Workspace preferences and account settings.", href: "/settings", group: "intelligence", kind: "workspace" },
  { title: "Document Vault", description: "Source documents, extraction review, citations and topology.", href: "/documents", group: "knowledge", kind: "workspace" },
  { title: "Document Ingestion", description: "Bring source material into the governed evidence workflow.", href: "/documents/ingest", group: "knowledge", kind: "workspace" },
  { title: "Document Comparison", description: "Compare revisions and inspect changed claims.", href: "/documents/compare", group: "knowledge", kind: "workspace" },
  { title: "Team Data Curation", description: "Annotations, corrections and validation corpus summaries.", href: "/resolveai#curation", group: "knowledge", kind: "integration" },
  { title: "Models & Fine-tuning", description: "Configured model roles and fine-tuning integration readiness.", href: "/resolveai#models", group: "knowledge", kind: "integration" },
  { title: "Model Evaluation Gate", description: "Validation corpus and model promotion criteria.", href: "/governance/model-gate", group: "knowledge", kind: "workspace" },
  { title: "Projects", description: "Organize project knowledge and linked source material.", href: "/projects", group: "knowledge", kind: "workspace" },
  { title: "Knowledge Handover", description: "Capture departing expertise through off-boarding sessions.", href: "/offboarding", group: "knowledge", kind: "workspace" },
  { title: "Governance Center", description: "Review queues and policies governing plant knowledge.", href: "/governance", group: "governance", kind: "workspace" },
  { title: "Conflict Resolution", description: "Compare competing claims and record accountable decisions.", href: "/governance/conflicts", group: "governance", kind: "workspace" },
  { title: "Evidence Quarantine", description: "Review held evidence before promotion to trusted knowledge.", href: "/governance/quarantine", group: "governance", kind: "workspace" },
  { title: "SLA Monitoring", description: "Track overdue review and resolution obligations.", href: "/governance/sla", group: "governance", kind: "workspace" },
  { title: "Management of Change", description: "Review, approve and track controlled changes.", href: "/governance/moc", group: "governance", kind: "workspace" },
  { title: "Timestamp Drift", description: "Inspect timestamp consistency and clock-related anomalies.", href: "/governance/timestamp-drift", group: "governance", kind: "workspace" },
  { title: "Circuit Breakers", description: "Inspect safeguards and automation stop conditions.", href: "/governance/circuit-breaker", group: "governance", kind: "workspace" },
  { title: "Push Volume Gate", description: "Review volume safeguards before pushing changes.", href: "/governance/push-volume-gate", group: "governance", kind: "workspace" },
  { title: "Compliance Coverage", description: "Evidence-backed requirements and asset compliance gaps.", href: "/compliance", group: "governance", kind: "workspace" },
  { title: "Nonconformance", description: "Track findings that do not satisfy required controls.", href: "/compliance/nonconformance", group: "governance", kind: "workspace" },
  { title: "Audit Pack", description: "Prepare an evidence package for compliance review.", href: "/compliance/audit-pack", group: "governance", kind: "workspace" },
  { title: "Audit Trail", description: "Inspect the chronology of recorded actions and decisions.", href: "/audit", group: "governance", kind: "workspace" },
  { title: "Hidden Problem Discovery", description: "Workflow preview: missing telemetry and unsupported assumptions.", href: "/resolveai#cyber", group: "cyber", kind: "preview" },
  { title: "Fraud & Agent Memory", description: "Workflow preview: compare suspicious requests with verified history.", href: "/resolveai#cyber", group: "cyber", kind: "preview" },
  { title: "Response & Verification", description: "Workflow preview: authorize a response and independently verify its outcome.", href: "/resolveai#cyber", group: "cyber", kind: "preview" },
  { title: "NetForensiq Forensics", description: "Planned adapter for network evidence and chain of custody.", href: "/resolveai#cyber", group: "cyber", kind: "preview" },
];

export const CAPABILITY_KIND_LABELS = {
  workspace: "Workspace",
  integration: "Integration",
  preview: "Workflow preview",
} as const;
