// Builds the exportable case report for a ResolveAI investigation. Pure: it states only what the worker returned and says
// plainly when a stage did not run, so an exported report can never imply model reasoning that did not happen.
import type { PlatformCase, PlatformInvestigation, PlatformRun } from "@/lib/lab-api";

export const isOfflineFallback = (text: string | undefined | null): boolean => /offline fallback|offline placeholder/i.test(text ?? "");

const cell = (s: string) => s.replace(/\|/g, "\\|").replace(/\s+/g, " ").trim();

export function buildCaseReport(c: PlatformCase, investigation: PlatformInvestigation | null, run: PlatformRun | null, generatedAt = new Date()): string {
  const lines: string[] = [];
  lines.push(`# Case report: ${c.title}`, "");
  lines.push(`- **Domain pack:** ${c.domain}`, `- **Institution:** ${c.institution_name}`, `- **Case status:** ${c.status ?? "unknown"}`, `- **Generated:** ${generatedAt.toISOString()}`, "");
  lines.push("> Reference material and drafts for human review. Not legal advice. Nothing in this report was submitted anywhere.", "");

  lines.push("## What was run", "");
  if (investigation) {
    lines.push(`- Evidence investigation: **${investigation.mode === "retrieval_only" ? "retrieval only (no model)" : "retrieval plus model synthesis"}**; model used: **${investigation.llm_used ? "yes" : "no"}**.`);
    lines.push(`- Domains searched: ${(investigation.domains_searched ?? []).join(", ")}.`);
    lines.push(`- Steps: ${(investigation.agent_trace ?? []).join(" → ")}.`, "");
  } else lines.push("- Evidence investigation: not run.", "");
  if (run) {
    lines.push(`- Multi-agent workflow: ${run.llm_call_count ?? 0} model call(s) counted; ${isOfflineFallback(run.research_summary) ? "**agents returned offline placeholders (no model provider), so no analysis or drafts were produced**" : "completed"}.`, "");
  }

  if (investigation) {
    lines.push("## Evidence", "");
    if (investigation.evidence.length === 0) lines.push("No indexed material matched this case.", "");
    else {
      lines.push("| # | Source | Authority | Confidence | Vector | Lexical | Excerpt |", "|---|---|---|---|---|---|---|");
      investigation.evidence.forEach((e, i) => {
        lines.push(`| ${i + 1} | ${cell(e.title)} | ${cell(e.authority)} | ${e.confidence.toFixed(2)} | ${e.vector_score?.toFixed(2) ?? "–"} | ${e.lexical_score?.toFixed(2) ?? "–"} | ${cell(e.retrieved_chunk).slice(0, 220)} |`);
      });
      lines.push("");
    }
    if (investigation.synthesis.status === "COMPLETED") {
      lines.push("## Model synthesis", "", investigation.synthesis.research_summary ?? "", "", investigation.synthesis.strategy ?? "", "");
    } else lines.push("## Model synthesis", "", `Not run. ${investigation.synthesis.reason ?? ""}`, "");
  }

  if (run && !isOfflineFallback(run.research_summary)) {
    lines.push("## Strategy and drafts", "");
    if (run.strategy) lines.push(`**Strategy.** ${run.strategy}`, "");
    if (run.evidence_summary) lines.push(`**Evidence summary.** ${run.evidence_summary}`, "");
    if (run.final_report) lines.push("```", run.final_report, "```", "");
  }

  if (investigation?.limitations?.length) {
    lines.push("## Limitations", "", ...(investigation.limitations ?? []).map((l) => `- ${l}`), "");
  }
  return lines.join("\n");
}
