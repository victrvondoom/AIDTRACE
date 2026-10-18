// Source → claim → memory → decision → action provenance, derived only from the site's FalkorDB agent-memory snapshot
// (/agent-memory/snapshot). Nothing is synthesised: every node and edge below is a record or a dependency the graph returned.
import type { MemorySnapshot } from "@/lib/lab-api";

export type LineageKind = "source" | "claim" | "memory" | "decision" | "action";
export const LINEAGE_COLUMNS: LineageKind[] = ["source", "claim", "memory", "decision", "action"];
export const LINEAGE_LABELS: Record<LineageKind, string> = { source: "Sources", claim: "Claims", memory: "Agent memory", decision: "Decisions", action: "Actions" };

export interface LineageNode {
  id: string; kind: LineageKind; label: string; status: string; detail: string;
  /** Sources only: the content hash. Sources sharing one hash are copies of the same origin. */
  origin?: string;
  /** Sources only: how this source relates to the others. Never "independent" without a content hash. */
  trust?: SourceTrust;
}
export type SourceTrust = "Original source" | "Independent support" | "Repeated citation" | "Disputed" | "Unverified" | "Superseded";
export interface LineageEdge { from: string; to: string }
export interface Lineage { nodes: LineageNode[]; edges: LineageEdge[]; originCount: number; sourceCount: number; hashedCount: number }

const short = (s: string, n = 64) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

export function buildLineage(snap: MemorySnapshot): Lineage {
  const nodes = new Map<string, LineageNode>();
  const edges: LineageEdge[] = [];
  const add = (n: LineageNode) => { if (!nodes.has(n.id)) nodes.set(n.id, n); };

  for (const s of snap.sources) add({ id: s.id, kind: "source", label: s.title || s.id, status: s.status, detail: `${s.version_label} · authority ${s.authority_level}` });
  for (const m of snap.memories) {
    for (const s of m.sources) {
      const known = nodes.get(s.id);
      if (known) known.origin = s.content_sha256 ?? known.origin;
      else add({ id: s.id, kind: "source", label: s.id, status: s.status, detail: s.document_id ? `document ${s.document_id}` : "source version", origin: s.content_sha256 ?? undefined });
      edges.push({ from: s.id, to: m.id });
    }
    for (const c of m.claims) {
      add({ id: c.id, kind: "claim", label: `${c.fact_key} = ${String(c.fact_value)}`, status: c.status, detail: "claim supporting a memory" });
      edges.push({ from: c.id, to: m.id });
    }
    add({ id: m.id, kind: "memory", label: short(m.summary), status: m.status, detail: `${m.agent_id} · ${m.independent_sources} independent source(s) · ${m.verification_status.toLowerCase()}` });
  }
  for (const d of snap.decisions) {
    add({ id: d.id, kind: "decision", label: short(d.summary), status: d.status, detail: `revision ${d.revision_n}` });
    for (const dep of d.dependency_ids) if (nodes.has(dep)) edges.push({ from: dep, to: d.id });
  }
  for (const a of snap.actions) {
    add({ id: a.id, kind: "action", label: short(a.summary), status: a.status, detail: a.eligibility.eligible ? "eligible for approval" : `blocked: ${a.eligibility.reasons[0] ?? "not eligible"}` });
    if (a.eligibility.decision_id && nodes.has(a.eligibility.decision_id)) edges.push({ from: a.eligibility.decision_id, to: a.id });
  }

  const sources = [...nodes.values()].filter((n) => n.kind === "source");
  const seenOrigins = new Set<string>();
  for (const src of [...sources].sort((a, b) => a.id.localeCompare(b.id))) {
    if (/SUPERSEDED|RETRACT|REVOKED/i.test(src.status)) src.trust = "Superseded";
    else if (/DISPUT|CONFLICT/i.test(src.status)) src.trust = "Disputed";
    else if (!src.origin) src.trust = "Unverified";
    else if (seenOrigins.has(src.origin)) src.trust = "Repeated citation";
    else src.trust = seenOrigins.size === 0 ? "Original source" : "Independent support";
    if (src.origin) seenOrigins.add(src.origin);
  }
  const origins = new Set(sources.map((s) => s.origin ?? s.id));
  const hashedCount = sources.filter((s) => s.origin).length;
  const seen = new Set<string>();
  const unique = edges.filter((e) => { const k = `${e.from}>${e.to}`; if (seen.has(k) || !nodes.has(e.from) || !nodes.has(e.to)) return false; seen.add(k); return true; });
  return { nodes: [...nodes.values()], edges: unique, originCount: origins.size, sourceCount: sources.length, hashedCount };
}

/** Every node upstream (what this rests on) and downstream (what rests on it) of `id`. */
export function chainOf(lineage: Lineage, id: string): { upstream: Set<string>; downstream: Set<string> } {
  const walk = (start: string, next: (e: LineageEdge) => [string, string]) => {
    const out = new Set<string>(); const queue = [start];
    while (queue.length) {
      const cur = queue.pop()!;
      for (const e of lineage.edges) { const [a, b] = next(e); if (a === cur && !out.has(b) && b !== start) { out.add(b); queue.push(b); } }
    }
    return out;
  };
  return { upstream: walk(id, (e) => [e.to, e.from]), downstream: walk(id, (e) => [e.from, e.to]) };
}

/** Stale, invalidated or blocked states that must read as a warning rather than as current evidence. */
export const isUnsafe = (status: string) => /STALE|INVALID|SUPERSEDED|SUSPENDED|VOID|BLOCKED|REVOKED|RETRACT/i.test(status);

export type DecisionStateLabel = "Valid" | "Needs review" | "Stale evidence" | "Approval blocked" | "Re-evaluated";
export interface DecisionState { label: DecisionStateLabel; tone: "verified" | "caution" | "danger"; reason: string | null }

/** A decision's state is read from backend fields only: its own status, its action's eligibility and whether an approval still binds to its current revision. */
export function decisionState(
  decision: { status: string; revision_n: number },
  action: { eligibility: { eligible: boolean; reasons: string[]; approval_current: boolean } } | undefined,
): DecisionState {
  if (isUnsafe(decision.status)) return { label: "Stale evidence", tone: "danger", reason: `Decision is ${decision.status.toLowerCase()}` };
  if (action && !action.eligibility.eligible) return { label: "Approval blocked", tone: "danger", reason: action.eligibility.reasons[0] ?? "Not eligible" };
  if (action && !action.eligibility.approval_current) return { label: decision.revision_n > 1 ? "Re-evaluated" : "Needs review", tone: "caution", reason: "No approval binds to this revision yet" };
  return { label: "Valid", tone: "verified", reason: null };
}
