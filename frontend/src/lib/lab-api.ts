// Typed client for Graph Lab (/graphlab/*) and the Source Library (/sources/*). Kept out of the large
// shared api.ts; it reuses that module's authenticated fetch so session refresh behaves identically, and
// surfaces the server's `detail` message (e.g. "unknown node(s) for 'changed'") instead of a bare status.
import { fetchWithSession, type Fetched } from "@/lib/api";
import type { LabGraph } from "@/lib/graph-layout";

export type ParamKind = "node" | "nodes" | "int" | "number" | "select" | "datetime" | "tags";
export interface LabParam { name: string; kind: ParamKind; label: string; default: unknown; options: string[]; required: boolean }
export interface Provenance {
  engine: string; implementation: string; status: string; tests: string;
  readme_derived_hypothesis_from: { repo: string; url: string | null }[];
}
export interface LabAlgorithm { id: string; title: string; summary: string; test: string; sources: string[]; params: LabParam[]; provenance: Provenance }
export interface LabPreset { algorithm: string; params: Record<string, unknown> }
export interface LabScenario { id: string; title: string; description: string; nodes: number; edges: number; recommended: LabPreset[] }
export interface LabResult {
  summary: Record<string, string | number | boolean | null>;
  findings: Record<string, unknown>[];
  node_marks: Record<string, string>;
  edge_marks: Record<string, string>;
  node_badges?: Record<string, string>;
  node_metric?: Record<string, number>;
  hotspots?: { node: string; paths_through: number }[];
  rings?: string[][];
  timeline?: string[];
  notes: string[];
}
export interface LabAnalysis { algorithm: string; graph_source: string; graph: LabGraph; result: LabResult; provenance: Provenance; elapsed_ms: number }
export interface LabSource { scenario?: string; graph?: LabGraph; site_graph?: boolean }

export type SourceStage = "README_READ" | "FEATURE_DESIGNED" | "SOURCE_AUDITED" | "INTEGRATED" | "TESTED" | "BROWSER_VERIFIED" | "BLOCKED";
export interface SourceRepo {
  repo: string; slug: string; url: string; project: string; summary: string; family: string; pack: string; license_status: string;
  readme: { present: boolean; bytes: number; origin: string | null };
  stages: SourceStage[]; stage: SourceStage; engines: string[]; blocked_reason: string | null; note: string;
}
export interface SourceSummary {
  repositories: number; readme_present: number; readme_absent: number; engines: number; integrated_repositories: number;
  by_family: Record<string, number>; by_stage: Record<string, number>; stages: SourceStage[]; untrusted_notice: string;
}
export interface SourceReadme { slug: string; repo: string; url: string; untrusted: true; bytes: number; sha256: string; truncated: boolean; text: string }

async function call<T>(path: string, init: RequestInit = {}, timeoutMs = 15000): Promise<T> {
  const res = await fetchWithSession(path, { cache: "no-store", ...init }, timeoutMs);
  if (!res.ok) {
    let detail = "";
    try {
      const body = await res.json();
      detail = typeof body?.detail === "string" ? body.detail : typeof body?.detail?.message === "string" ? body.detail.message : "";
    } catch { /* non-JSON error body */ }
    throw new Error(detail || `${path} → HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}
const live = async <T>(path: string, timeoutMs?: number): Promise<Fetched<T>> => ({ data: await call<T>(path, {}, timeoutMs), source: "live" });

export const getLabAlgorithms = () => live<{ algorithms: LabAlgorithm[] }>("/graphlab/algorithms");
export const getLabScenarios = () => live<{ scenarios: LabScenario[] }>("/graphlab/scenarios");
export const getLabScenario = (id: string) =>
  live<{ id: string; title: string; description: string; graph: LabGraph; recommended: LabPreset[] }>(`/graphlab/scenario?scenario_id=${encodeURIComponent(id)}`);

export interface FalkorDBInfo {
  status: string;
  graph_name: string;
  engine: string;
  host: string;
  site_id: string;
  node_count: number;
  edge_count: number;
  node_distribution?: { type: string; count: number }[];
  relationship_distribution?: { relationship: string; count: number }[];
}

export interface CypherQueryResult {
  graph_name: string;
  query: string;
  run_time_ms: number;
  header: string[];
  rows: unknown[][];
  row_count: number;
  engine: string;
}

export const getSiteGraph = () => live<{ graph: LabGraph; truncated: boolean; empty: boolean; falkordb?: FalkorDBInfo }>("/graphlab/site-graph");
export function runSiteCypher(query: string, params?: Record<string, unknown>): Promise<CypherQueryResult> {
  return call<CypherQueryResult>("/graphlab/site-cypher", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, params: params ?? {} }),
  }, 10000);
}
export function analyzeLab(algorithm: string, source: LabSource, params: Record<string, unknown>, signal?: AbortSignal): Promise<LabAnalysis> {
  return call<LabAnalysis>("/graphlab/analyze", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ algorithm, params, ...source }),
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(30000)]) : undefined,
  }, 30000);
}

export const getSourceSummary = () => live<SourceSummary>("/sources/summary");
export function getSourceRepos(filter: { family?: string; stage?: string; engine?: string; q?: string }) {
  const q = new URLSearchParams({ limit: "200" });
  for (const [k, v] of Object.entries(filter)) if (v) q.set(k, v);
  return live<{ total: number; items: SourceRepo[] }>(`/sources/repos?${q}`);
}
// ---- Resolve consumer-remedy workspace (/resolveai/consumer/*), tenant-scoped on the server with FALKOR DB ----
export interface ConsumerCondition { id: string; text: string; status: string; reasons: string[]; paths: string[] }
export interface ConsumerVerdict {
  strategy_id: string; title: string; remedy_title: string; domains: string[]; verdict: "VERIFIED" | "REJECTED" | "INSUFFICIENT_EVIDENCE";
  blocked_by: string | null; conditions: ConsumerCondition[]; reasons: string[]; missing_evidence: string[];
}
export interface ConsumerGap { item_id: string; kind: string; label: string; verified_gain: number; changes: { strategy_id: string; from: string; to: string }[]; note: string[] }
export interface ConsumerAnalysis {
  status: string; message?: string; revision?: string; verdicts?: ConsumerVerdict[]; evidence_gaps?: ConsumerGap[];
  cross_domain?: {
    shared_evidence: { evidence_id: string; type: string; status: string; domains: string[] }[];
    dependencies: { condition: string; depends_on: string; strategies: string[] }[];
    conflicts: { event: string; strategies: string[] }[];
  };
  plan?: { status: string; draft_strategy_id: string | null; next_evidence: ConsumerGap | null };
  independent_check?: { agrees: boolean };
  draft?: { action_id: string; revision: string; body: string } | null;
  trace?: { agent: string; event: string; detail: string }[];
}
export interface ConsumerState {
  evidence: { id: string; type: string; status: string; amount: number | null }[];
  sources: { id: string; title: string; verified: boolean }[];
  revision: { revision: string };
}
export interface ConsumerAction { action_id: string; status: string; approved_revision?: string; current_revision?: string; body?: string; approved_by?: string }
export interface ConsumerIntake {
  status: string; domains: string[]; missing: string[]; ambiguities: string[]; institutions: string[]; ignored_instructions: string[];
  events: { type: string }[]; amounts: unknown[]; dates: unknown[];
}
const C = "/resolveai/consumer";
const post = <T>(path: string, body: unknown = {}) => call<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }, 30000);
export const consumerHealth = () => call<{ falkordb: boolean; case_loaded?: boolean; message?: string }>(`${C}/health`);
export const consumerLoad = () => post(`${C}/case/load`, { overrides: {} });
export const consumerState = () => call<ConsumerState>(`${C}/state`);
export const consumerGraph = () => call<{ graph: LabGraph; revision: { revision: string } }>(`${C}/graph`);
export const consumerActions = () => call<{ actions: ConsumerAction[] }>(`${C}/actions`);
export const consumerAnalyze = () => post<ConsumerAnalysis>(`${C}/analyze`);
export const consumerSetEvidence = (id: string, status: string) => post(`${C}/evidence?evidence_id=${encodeURIComponent(id)}`, { status });
export const consumerSetSource = (id: string, verified: boolean) => post(`${C}/source?source_id=${encodeURIComponent(id)}`, { verified });
export const consumerDropEdge = (e: { src_label: string; src_id: string; rel: string; dst_label: string; dst_id: string }) => post(`${C}/edges/drop`, e);
export const consumerApprove = (id: string, revision: string) => post(`${C}/actions/approve?action_id=${encodeURIComponent(id)}`, { revision });
export const consumerIntake = (text: string) => post<ConsumerIntake>(`${C}/intake`, { text });

// ---- GreenChain procurement intelligence (/greenchain/*) ----
export interface GreenchainHealth { ml_models: boolean; reference_data: boolean; live_discovery: string; missing_provider_keys: string[]; demo_mode: string }
export interface GreenchainDemo {
  mode: string; notice: string; product: string; destination: string; transport_mode: string; results: Record<string, unknown>[]; graph: LabGraph;
}
export interface GreenchainWhatIf { removed: string; top_before: string | null; top_after: string | null; recommendation_changes: boolean; rank_changes: { name: string; from: number | null; to: number }[] }
export const greenchainHealth = () => call<GreenchainHealth>("/greenchain/health");
export const greenchainDemo = (mode = "sea") => call<GreenchainDemo>(`/greenchain/demo?transport_mode=${encodeURIComponent(mode)}`, {}, 60000);
export const greenchainScore = (manufacturers: unknown[], transport_mode: string, weights: Record<string, number>) =>
  post<{ count: number; results: { name: string; rank: number }[] }>("/greenchain/score", { manufacturers, transport_mode, weights });
export const greenchainWhatIf = (remove: string, transport_mode: string) => post<GreenchainWhatIf>("/greenchain/whatif/remove-supplier", { remove, transport_mode });
export const greenchainPersist = (results: unknown[]) => post<{ nodes: number; edges: number }>("/greenchain/graph/persist", { results });

// ---- Fraud investigation + agent operations (/fraud/*) ----
export interface FraudEvent { seq: number; at: string; type: string; text?: string; name?: string; summary?: string; cypher?: string; ms?: number; rows?: number; reason?: string; message?: string; mode?: string; action?: FraudAction }
export interface FraudAction { action_id: string; type: string; status: string; rule: string; targets: string[]; evidence: { account_id: string; hops: number }[]; receipt?: string | null }
export interface FraudRun { run_id: string; status: string; mode: string; started_at: string; events: FraudEvent[]; proposals: FraudAction[] }
export interface FraudHealth { falkordb: boolean; graph?: string; loaded?: boolean; llm_available?: boolean }
const F = "/fraud";
export const fraudHealth = () => call<FraudHealth>(`${F}/health`);
export const fraudSeed = () => post<{ graph: string; counts: Record<string, number> }>(`${F}/seed`);
export const fraudFlagged = () => call<{ transactions: { transaction_id: string; amount: number; account_id: string }[] }>(`${F}/flagged`);
export const fraudStart = (use_llm: boolean) => post<{ run_id: string; mode: string }>(`${F}/investigations`, { use_llm });
export const fraudRun = (run_id: string) => call<FraudRun>(`${F}/investigation?run_id=${encodeURIComponent(run_id)}`);
export const fraudActions = () => call<{ actions: FraudAction[] }>(`${F}/actions`);
export const fraudApprove = (id: string) => post<{ status: string; frozen_accounts: string[]; receipt: string }>(`${F}/actions/approve?action_id=${encodeURIComponent(id)}`);
export const fraudReject = (id: string) => post<{ status: string }>(`${F}/actions/reject?action_id=${encodeURIComponent(id)}`);
export const fraudRing = (account_id: string) => call<{ members: { account_id: string; hops: number }[]; graph: LabGraph }>(`${F}/ring?account_id=${encodeURIComponent(account_id)}`);

// ---- Resolve platform gateway (/resolveai/platform/*): the private RESOLVE worker behind AIDTRACE with FALKOR DB ----
export interface PlatformDomain { id: string; label: string; active: boolean }
export interface PlatformRuntime { model_provider: string; model_provider_name: string | null; vector_backend: string | null; indexed_points: number | null; collections: number | null; graph_backend: string | null; case_store: string }
export interface PlatformStatus { connected: boolean; domains?: PlatformDomain[]; runtime?: PlatformRuntime | null; status?: string; message?: string; setup?: string }
export interface PlatformCase { id: string; domain: string; title: string; institution_name: string; summary: string; status?: string }
export interface PlatformRun { case_id: string; status: string; route?: string; strategy?: string; final_report?: string; appeal_draft?: string; evidence_summary?: string;
  research_summary?: string; citations?: unknown[]; agent_trace?: unknown[]; llm_call_count?: number; review_notes?: string[] }
const P = "/resolveai/platform";
export const platformStatus = () => call<PlatformStatus>(`${P}/status`, {}, 20000);
export const platformCases = () => call<{ cases: PlatformCase[] }>(`${P}/cases`, {}, 30000);
export const platformCreateCase = (c: { domain: string; title: string; institution_name: string; summary: string }) => post<PlatformCase>(`${P}/cases`, c);
export interface PlatformEvidence {
  title: string; authority: string; section: string | null; url: string | null; domain: string; retrieved_chunk: string;
  confidence: number; evidence_scores: Record<string, number>; chunk_id: string | null; retrieval_score: number | null;
  vector_score: number | null; lexical_score: number | null;
}
export interface PlatformInvestigation {
  case_id: string; mode: "retrieval_only" | "retrieval_plus_model"; llm_used: boolean; routing: { domain: string; confidence: number | null }[];
  domains_searched: string[]; retrieval: { domain: string; hits_considered: number; collection: string; indexed_points: number }[];
  evidence: PlatformEvidence[]; graph_patterns: Record<string, unknown>[]; agent_trace: string[]; limitations: string[];
  synthesis: { status: string; reason?: string; research_summary?: string; strategy?: string; review_notes?: string[]; llm_call_count?: number };
}
export interface PlatformSearchHit { id: string; score: number; text: string; metadata: Record<string, string | number | null> }
export interface PlatformCaseGraph { case_id: string; domain: string; nodes: { id: string; kind: string; label: string; detail: Record<string, unknown> }[]; edges: { source: string; target: string }[] }
export interface PlatformEvent { id?: string; event_type: string; title?: string; body?: string; actor?: string; created_at?: string }
export interface PlatformRunRecord { id: string; workflow_name: string; status: string; output?: Record<string, unknown> }
export interface PlatformReport {
  case: PlatformCase | null; appeals: { id: string; title: string; content?: string; status?: string }[]; events: PlatformEvent[]; agent_runs: PlatformRunRecord[];
  latest_analysis: { research_summary: string; evidence_summary: string; strategy: string; appeal_draft: string; final_report: string; review_notes: string[]; citations: unknown[]; agent_trace: string[]; llm_call_count: number };
}
export interface PlatformSummary { totals: { cases: number; appeals: number; documents: number; domains_engaged: number }; domain_breakdown: { domain: string; count: number }[]; case_status_breakdown: { status: string; count: number }[] }
export const platformInvestigate = (case_id: string, run_model_synthesis = false) => post<PlatformInvestigation>(`${P}/agents/investigate`, { case_id, run_model_synthesis });
export const platformSearch = (domain: string, query: string, limit = 6) => post<{ hits: PlatformSearchHit[] }>(`${P}/search`, { domain, query, limit });
export const platformCaseGraph = (case_id: string) => call<PlatformCaseGraph>(`${P}/case-graph?case_id=${encodeURIComponent(case_id)}`, {}, 30000);
export const platformTrail = (case_id: string) => call<{ steps: { index: number; token: string; node_id: string }[] }>(`${P}/reasoning-trail?case_id=${encodeURIComponent(case_id)}`, {}, 30000);
export const platformReport = (case_id: string) => call<PlatformReport>(`${P}/report?case_id=${encodeURIComponent(case_id)}`, {}, 30000);
export const platformSummary = () => call<PlatformSummary>(`${P}/summary`, {}, 30000);
export const platformRunCase = (case_id: string) => post<PlatformRun>(`${P}/agents/run-case`, { case_id, include_negotiation_draft: true });

// ---- Hub capability status (/hub/capabilities): every overview node is labelled from a live probe ----
export type CapabilityState = "OPERATIONAL" | "LIMITED" | "UNAVAILABLE";
export interface HubCapability { id: string; name: string; state: CapabilityState; detail: string; limits: string[]; metrics: Record<string, number | boolean | null> }
export interface HubCapabilities { generated_at: string; site_id: string | null; capabilities: HubCapability[]; edges: { source: string; target: string; rel: string }[] }
export const hubCapabilities = () => call<HubCapabilities>("/hub/capabilities", {}, 20000);

// ---- Agent memory, evidence revision and approvals (/agent-memory/*) ----
export interface MemoryRecord { id: string; memory_kind: string; summary: string; agent_id: string; status: string; verification_status: string; confidence: number; independent_sources: number;
  recorded_at: string; last_verified_at: string; investigation_ref: string; blocked_reason: string | null;
  claims: { id: string; fact_key: string; fact_value: string | number | boolean | null; status: string }[]; sources: { id: string; status: string; document_id: string | null; content_sha256: string | null }[] }
export interface Eligibility { eligible: boolean; reasons: string[]; decision_id: string | null; revision_n?: number; approval_current: boolean }
export interface MemoryDecision { id: string; summary: string; status: string; revision_n: number; dependency_ids: string[]; revision_id: string | null; graph_revision: string | null }
export interface MemoryAction { id: string; summary: string; status: string; eligibility: Eligibility }
export interface MemoryApproval { id: string; decision_id: string; revision_id: string; graph_revision: string; approval_status: string; approved_by: string; approved_at: string; note?: string }
export interface MemorySnapshot { memories: MemoryRecord[]; decisions: MemoryDecision[]; actions: MemoryAction[]; approvals: MemoryApproval[];
  sources: { id: string; title: string; status: string; version_label: string; authority_level: number }[]; changes: { id: string; verdict: string; reason: string; observed_at: string; result_json?: string }[]; agents: { id: string; name: string; system: string }[] }
export interface RankRow { name: string; country: string | null; rank_before: number; rank_after: number; total_before: number; total_after: number }
export interface CascadeItem { id: string; label: string; before: string; after: string; depth: number; via: string[] }
export interface GcRecorded { scenario_id: string; top: string; ranking: { name: string; rank: number; total_tco2e: number; manufacturing_q50: number; country: string | null }[]; memory_id: string; decision_id: string; action_id: string; datasets: Record<string, string> }
export interface GcRevised { duplicate: boolean; dataset: string; revision: { country: string; factor: number; label: string }; cascade: { verdict: string; invalidated: CascadeItem[]; audit_hash?: string }; ranking: RankRow[];
  recommendation_changed: boolean; top_before: string; top_after: string; old_decision: { id: string; status: string }; old_action: { id: string; eligibility: Eligibility };
  new_proposal: { decision_id: string; action_id: string; eligibility: Eligibility } | null; new_memory_id: string }
export interface GcPreview { read_only: true; counterfactual: true; dataset: string; revision: { country: string; factor: number }; top_before: string; top_after: string; recommendation_changes: boolean; ranking: RankRow[] }
export interface ImpactPreview { source_id: string; read_only: true; would_mark_stale: { id: string; label: string; status: string; depth: number; via: string[]; summary: string }[] }
export interface Handoff { memory_id: string; produced_by: string; recalled_by: string; memory_status: string; recall_session: string; at: string; usable: boolean }
export interface RecallResult { agent_id: string; usable: MemoryRecord[]; blocked: MemoryRecord[]; influenced_by: string[] }
const M = "/agent-memory";
export const memorySnapshot = () => call<MemorySnapshot>(`${M}/snapshot`, {}, 30000);
export const memoryRecordScenario = (transport_mode = "sea") => post<GcRecorded>(`${M}/greenchain/record`, { transport_mode });
export const memoryRevise = (b: { scenario_id: string; dataset: string; country: string; factor: number; label: string }) => post<GcRevised>(`${M}/greenchain/revise`, b);
export const memoryPreviewRevision = (b: { scenario_id: string; dataset: string; country: string; factor: number; label: string }) => post<GcPreview>(`${M}/greenchain/preview-revision`, b);
export const memoryImpactPreview = (source_id: string) => call<ImpactPreview>(`${M}/impact-preview?source_id=${encodeURIComponent(source_id)}`, {}, 30000);
export const memoryApprove = (action_id: string, note = "") => post<{ approved: true; approval_id: string; graph_revision: string; reviewer: string }>(`${M}/actions/approve`, { action_id, note });
export const memoryRecall = (agent_id: string, fact_key?: string) => post<RecallResult>(`${M}/recall`, { agent_id, fact_key: fact_key || null, limit: 10 });
export const memoryHandoffs = () => call<{ handoffs: Handoff[] }>(`${M}/handoffs`, {}, 30000);
export const memoryRememberCase = (case_id: string) => post<{ remembered: boolean; memory_id?: string; claims?: string[]; independent_sources?: number; verified?: boolean; reason?: string }>(`${M}/resolveai/remember`, { case_id });
export const memoryGreenchainReport = (scenario_id: string) => call<{ scenario_id: string; markdown: string; decisions: number; revisions: number; approvals: number }>(`${M}/greenchain/report?scenario_id=${encodeURIComponent(scenario_id)}`, {}, 30000);

// ---- Agent operations (/agents/*): one view over four runtimes ----
export interface AgentTool { name: string; interface: string; description: string; read_only: boolean; invokable: boolean }
export interface AgentRuntime { id: string; name: string; framework: string; origin: string; interfaces: Record<string, "native" | "via_kairos" | "none">; tools: AgentTool[]; limits: string[];
  status: { state: CapabilityState; detail: string; metrics?: Record<string, number | boolean | null> } }
export interface AgentRun { system: string; run_id: string; kind: string; status: string | null; at: string | null; summary: string; ref: string | null }
export interface AgentRuntimes { runtimes: AgentRuntime[]; matrix: { interfaces: string[]; runtimes: { id: string; name: string; support: Record<string, string> }[] } }
export const agentRuntimes = () => call<AgentRuntimes>("/agents/runtimes", {}, 30000);
export const agentRuns = (limit = 30) => call<{ runs: AgentRun[]; by_system: Record<string, number> }>(`/agents/runs?limit=${limit}`, {}, 30000);
export const agentInvoke = (runtime: string, tool: string, args: Record<string, unknown>) => post<{ runtime: string; tool: string; read_only: boolean; result: Record<string, unknown>; trace: Record<string, string> }>("/agents/tools/invoke", { runtime, tool, args });

export const getSourceLedger = () => live<{ stages: SourceStage[]; items: SourceRepo[] }>("/sources/ledger", 30000);
export const getSourceReadme = (slug: string) => live<SourceReadme>(`/sources/readme?slug=${encodeURIComponent(slug)}`);
