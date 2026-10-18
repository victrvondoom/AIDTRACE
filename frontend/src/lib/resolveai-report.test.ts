import { describe, expect, it } from "vitest";
import type { PlatformCase, PlatformInvestigation, PlatformRun } from "@/lib/lab-api";
import { buildCaseReport, isOfflineFallback } from "@/lib/resolveai-report";

const c: PlatformCase = { id: "c1", domain: "health_insurance", title: "Knee claim rejected", institution_name: "Acme Health", summary: "x", status: "intake" };
const investigation: PlatformInvestigation = {
  case_id: "c1", mode: "retrieval_only", llm_used: false, routing: [{ domain: "health_insurance", confidence: 1 }], domains_searched: ["health_insurance"],
  retrieval: [{ domain: "health_insurance", hits_considered: 24, collection: "proxy_health_insurance", indexed_points: 3541 }],
  evidence: [{ title: "Policy | wording", authority: "IRDAI", section: "policy_wording", url: null, domain: "health_insurance", retrieved_chunk: "Pre-existing disease\nwaiting period",
    confidence: 0.49, evidence_scores: {}, chunk_id: "k1", retrieval_score: 0.7, vector_score: 0.99, lexical_score: 1 }],
  graph_patterns: [], agent_trace: ["router:keyword_scored", "retrieve:health_insurance:24_hits"], limitations: ["Lexical re-rank blends with vectors."],
  synthesis: { status: "NOT_RUN", reason: "No model provider is configured." },
};

describe("case report", () => {
  it("states that no model ran and lists scored, escaped evidence", () => {
    const md = buildCaseReport(c, investigation, null, new Date("2026-10-18T00:00:00Z"));
    expect(md).toContain("# Case report: Knee claim rejected");
    expect(md).toContain("retrieval only (no model)");
    expect(md).toContain("model used: **no**");
    expect(md).toContain("Policy \\| wording");
    expect(md).not.toContain("\nwaiting period"); // newlines in excerpts are flattened so the table stays intact
    expect(md).toContain("Not run. No model provider is configured.");
    expect(md).toContain("Not legal advice");
  });

  it("never presents offline placeholder agent output as analysis", () => {
    const run: PlatformRun = { case_id: "c1", status: "ready_for_human_review", research_summary: "Offline fallback -- no LLM connectivity", strategy: "Offline fallback -- x", llm_call_count: 6 };
    const md = buildCaseReport(c, investigation, run);
    expect(md).toContain("agents returned offline placeholders");
    expect(md).not.toContain("Strategy and drafts");
    expect(isOfflineFallback(run.research_summary)).toBe(true);
  });

  it("includes strategy and drafts only for a genuine run", () => {
    const run: PlatformRun = { case_id: "c1", status: "ready", research_summary: "Clause 4.2 applies.", strategy: "Appeal within 30 days.", final_report: "Dear Sir", llm_call_count: 6 };
    const md = buildCaseReport(c, null, run);
    expect(md).toContain("Evidence investigation: not run.");
    expect(md).toContain("Strategy and drafts");
    expect(md).toContain("Appeal within 30 days.");
  });
});
