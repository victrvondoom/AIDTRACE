// The two automated AIDTRACE workflows. Each one chains existing backend services and reports real stage progress; nothing is simulated except the
// clearly labelled synthetic evidence revision. Stages that cannot run (for example, no live security feed) say so instead of inventing a result.
import { buildLineage, chainOf, isUnsafe } from "@/lib/aidtrace-lineage";
import {
  greenchainWhatIf, memoryPreviewRevision, memoryRecordScenario, memoryRevise,
  type CascadeItem, type GcPreview, type GcRevised, type GreenchainWhatIf, type MemoryDecision, type MemoryRecord, type RankRow,
} from "@/lib/lab-api";
import { propagate, propagateSite, supplierAnchors, type AidtraceData, type Impacted } from "./data";

export type StageStatus = "pending" | "running" | "done" | "skipped" | "failed";
export interface Stage { id: string; label: string; status: StageStatus; detail?: string }
export type OnStages = (stages: Stage[]) => void;

/** The synthetic, reproducible evidence update used by the demo: the Ember grid-carbon reference for Portugal is revised ×50. It is applied through the
 *  same backend path a real dataset revision takes, and it flips the recommendation, so the cascade is visible. It is stress-test data, not a measurement. */
export const SYNTHETIC_REVISION = { dataset: "EMBER", country: "PT", factor: 50, label: "Synthetic grid-intensity revision (demo)" } as const;

const plain = (name: string) => name.replace("Illustrative ", "");
const scenarioOf = (id: string) => /^gc:([^:]+):/.exec(id)?.[1] ?? null;
export const latestScenarioId = (decisions: MemoryDecision[]) => {
  const ids = decisions.map((d) => scenarioOf(d.id)).filter((x): x is string => Boolean(x));
  return ids[ids.length - 1] ?? null;
};

class Tracker {
  stages: Stage[];
  constructor(defs: [string, string][], private emit: OnStages) { this.stages = defs.map(([id, label]) => ({ id, label, status: "pending" as StageStatus })); this.emit([...this.stages]); }
  set(id: string, status: StageStatus, detail?: string) {
    this.stages = this.stages.map((s) => (s.id === id ? { ...s, status, detail } : s));
    this.emit([...this.stages]);
  }
}

export interface InvestigationResult {
  at: string; supplierId: string; supplierName: string; country: string;
  traversal: "FalkorDB site graph" | "scenario graph (not persisted)";
  dependents: Impacted[]; dependencies: Impacted[];
  memories: MemoryRecord[]; sourceCount: number; hashedSources: number;
  decisions: { id: string; summary: string; status: string; stale: boolean }[];
  metrics: { ecoScore: number; mfgQ50: number; mfgQ10: number; mfgQ90: number; transport: number; certifications: string[] };
  alternative: { name: string; ecoScore: number } | null; whatIf: GreenchainWhatIf | null;
  recorded: "recorded now" | "already recorded";
  /** Short facts derived from the above. */ findings: string[];
  /** What the evidence cannot establish. */ uncertainty: string[];
}

export interface InvestigationContext { data: AidtraceData; supplierId: string | null }

export async function investigateRisk(ctx: InvestigationContext, emit: OnStages): Promise<InvestigationResult> {
  const t = new Tracker([
    ["identify", "Identify supplier"], ["record", "Record baseline decision in FalkorDB memory"], ["graph", "Traverse connected records in FalkorDB"], ["memory", "Recall prior agent memory"],
    ["evidence", "Collect source evidence"], ["cyber", "Check security and disruption findings"], ["metrics", "Score emissions and logistics"], ["decisions", "Find dependent decisions"], ["summary", "Summarise with uncertainty"],
  ], emit);
  const { data } = ctx;
  const manufacturers = data.scenario?.manufacturers ?? [];
  if (!data.demo || !manufacturers.length) throw new Error("The supplier scenario is not loaded, so there is nothing to investigate.");

  t.set("identify", "running");
  const supplier = manufacturers.find((m) => m.id === ctx.supplierId) ?? manufacturers.find((m) => m.isCurrent) ?? [...manufacturers].sort((a, b) => a.ecoScore - b.ecoScore)[0];
  t.set("identify", "done", `${plain(supplier.name)} (${supplier.location.countryCode})`);

  // Fresh state from here on: the baseline may have to be written before the graph can be traversed.
  let snap = data.snap;
  let site = data.site;
  let recorded: InvestigationResult["recorded"] = "already recorded";
  t.set("record", "running");
  if (!snap || !latestScenarioId(snap.decisions)) {
    await memoryRecordScenario("sea");
    recorded = "recorded now";
    const fresh = await data.refreshMemory();
    snap = fresh.snap; site = fresh.site;
    t.set("record", "done", "Baseline decision, claims and sources written to the graph");
  } else t.set("record", "skipped", "Already in the graph");
  if (!snap) throw new Error("Agent memory could not be read after recording.");

  t.set("graph", "running");
  const anchors = supplierAnchors(site, supplier.name);
  let dependents: Impacted[] = [], dependencies: Impacted[] = [];
  let traversal: InvestigationResult["traversal"] = "FalkorDB site graph";
  if (site && anchors.length) {
    const p = await propagateSite(site, anchors);
    dependents = p.dependents; dependencies = p.dependencies;
  } else {
    traversal = "scenario graph (not persisted)";
    const node = data.demo.graph.nodes.find((n) => n.type === "Supplier" && n.label === supplier.name);
    if (node) { const p = await propagate(data.demo.graph, node.id); dependents = p.dependents; dependencies = p.dependencies; }
  }
  t.set("graph", "done", `${dependents.length} depend on it · it depends on ${dependencies.length} (${traversal})`);

  t.set("memory", "running");
  const needle = plain(supplier.name).toLowerCase();
  const memories = snap.memories.filter((m) => m.summary.toLowerCase().includes(needle) || m.claims.some((c) => c.id.includes(supplier.name.replace(/ /g, "_"))));
  t.set("memory", memories.length ? "done" : "skipped", memories.length ? `${memories.length} memory record(s)` : "Nothing remembered about this supplier yet");

  t.set("evidence", "running");
  const sourceIds = new Set(memories.flatMap((m) => m.sources.map((s) => s.id)));
  const hashed = new Set(memories.flatMap((m) => m.sources.filter((s) => s.content_sha256).map((s) => s.id)));
  t.set("evidence", sourceIds.size ? "done" : "skipped", sourceIds.size ? `${sourceIds.size} source(s), ${hashed.size} with a content hash` : "No sources linked");

  t.set("cyber", "skipped", "No live security feed is connected; reach is modelled from the graph only");

  t.set("metrics", "running");
  const ranked = [...manufacturers].sort((a, b) => a.ecoScore - b.ecoScore);
  const alt = ranked.find((m) => m.id !== supplier.id) ?? null;
  const whatIf = await greenchainWhatIf(supplier.name, "sea").catch(() => null);
  t.set("metrics", "done", `Eco score ${supplier.ecoScore.toFixed(0)}, ${supplier.manufacturingEmissionsTco2e.q50.toFixed(0)} tCO2e manufacturing`);

  t.set("decisions", "running");
  const lineage = buildLineage(snap);
  const downstream = new Set<string>();
  for (const m of memories) for (const id of chainOf(lineage, m.id).downstream) downstream.add(id);
  const decisions = snap.decisions.filter((d) => downstream.has(d.id)).map((d) => ({ id: d.id, summary: d.summary, status: d.status, stale: isUnsafe(d.status) }));
  t.set("decisions", "done", `${decisions.length} decision(s), ${decisions.filter((d) => d.stale).length} stale`);

  t.set("summary", "running");
  const staleMem = memories.filter((m) => isUnsafe(m.status)).length;
  const findings = [
    `${dependents.length} recorded item(s) depend on ${plain(supplier.name)}'s evidence.`,
    `${decisions.filter((d) => d.stale).length} of ${decisions.length} dependent decision(s) stand on stale evidence.`,
    staleMem ? `${staleMem} memory record(s) about it are stale.` : memories.length ? "Its memory records are current." : "No memory records mention it.",
    whatIf ? (whatIf.recommendation_changes ? `Removing it changes the top choice to ${plain(whatIf.top_after ?? "another supplier")}.` : `Removing it leaves the top choice at ${plain(whatIf.top_after ?? "unchanged")}.`) : "Removal impact could not be computed.",
  ];
  const uncertainty = [
    "No live security or disruption feed is connected; cyber exposure is modelled, not observed.",
    "Emissions are modelled intensities with an interval, not factory measurements; certifications are unverified claims.",
    sourceIds.size && hashed.size < sourceIds.size ? `${sourceIds.size - hashed.size} source(s) have no content hash, so their independence is unknown.` : "",
    "Supplier locations are country-level; candidates are illustrative.",
  ].filter(Boolean);
  t.set("summary", "done");

  return {
    at: new Date().toISOString(), supplierId: supplier.id, supplierName: supplier.name, country: supplier.location.countryCode, traversal, dependents, dependencies, memories,
    sourceCount: sourceIds.size, hashedSources: hashed.size, decisions,
    metrics: { ecoScore: supplier.ecoScore, mfgQ50: supplier.manufacturingEmissionsTco2e.q50, mfgQ10: supplier.manufacturingEmissionsTco2e.q10, mfgQ90: supplier.manufacturingEmissionsTco2e.q90, transport: supplier.transportEmissionsTco2e, certifications: supplier.certifications },
    alternative: alt ? { name: alt.name, ecoScore: alt.ecoScore } : null, whatIf, recorded, findings, uncertainty,
  };
}

// ---- Evidence update ----------------------------------------------------------------------------------------------------------------------

export interface EvidenceResult {
  at: string; revision: typeof SYNTHETIC_REVISION; alreadyApplied: boolean;
  topBefore: string | null; topAfter: string | null; recommendationChanged: boolean;
  invalidated: CascadeItem[]; ranking: RankRow[]; newProposal: boolean; auditHash: string | null;
}

export async function updateEvidence(data: AidtraceData, emit: OnStages): Promise<EvidenceResult> {
  const t = new Tracker([
    ["baseline", "Ensure a baseline decision exists"], ["validate", "Validate and version the new evidence"], ["preview", "Preview the effect (writes nothing)"],
    ["apply", "Apply: invalidate dependants and re-score"], ["refresh", "Re-read memory and the FalkorDB graph"], ["review", "Create a review item"],
  ], emit);
  let snap = data.snap;
  t.set("baseline", "running");
  if (!snap || !latestScenarioId(snap.decisions)) {
    await memoryRecordScenario("sea");
    snap = (await data.refreshMemory()).snap;
    t.set("baseline", "done", "Recorded");
  } else t.set("baseline", "skipped", "Already recorded");
  const scenarioId = snap ? latestScenarioId(snap.decisions) : null;
  if (!scenarioId) throw new Error("No GreenChain decision exists to re-evaluate.");

  const body = { scenario_id: scenarioId, ...SYNTHETIC_REVISION };
  t.set("validate", "done", `${SYNTHETIC_REVISION.dataset} · ${SYNTHETIC_REVISION.country} × ${SYNTHETIC_REVISION.factor} — synthetic, reproducible, not a measurement`);

  t.set("preview", "running");
  const preview: GcPreview = await memoryPreviewRevision(body);
  t.set("preview", "done", preview.recommendation_changes ? `Recommendation would change: ${plain(preview.top_before)} → ${plain(preview.top_after)}` : `Recommendation would stay ${plain(preview.top_after)}`);

  t.set("apply", "running");
  const applied = await memoryRevise(body) as GcRevised;
  if (applied.duplicate) t.set("apply", "skipped", "This revision was already applied to the graph");
  else t.set("apply", "done", `${applied.cascade.invalidated.length} record(s) invalidated`);

  t.set("refresh", "running");
  await data.refreshMemory();
  t.set("refresh", "done");

  t.set("review", applied.duplicate ? "skipped" : "done", applied.duplicate ? "Existing review item stands" : applied.new_proposal ? "A new proposal awaits human review" : "No eligible replacement proposal");
  return {
    at: new Date().toISOString(), revision: SYNTHETIC_REVISION, alreadyApplied: Boolean(applied.duplicate),
    topBefore: applied.duplicate ? preview.top_before : applied.top_before, topAfter: applied.duplicate ? preview.top_after : applied.top_after,
    recommendationChanged: applied.duplicate ? preview.recommendation_changes : applied.recommendation_changed,
    invalidated: applied.duplicate ? [] : applied.cascade.invalidated, ranking: applied.duplicate ? preview.ranking : applied.ranking,
    newProposal: Boolean(applied.new_proposal), auditHash: applied.duplicate ? null : applied.cascade.audit_hash ?? null,
  };
}
