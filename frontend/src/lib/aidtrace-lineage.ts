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
}
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
