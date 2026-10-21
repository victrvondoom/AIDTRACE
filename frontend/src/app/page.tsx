"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";
import { dmSans, instrumentSans } from "./landing-fonts";
import { youTubeId } from "@/lib/youtube";

/**
 * Demo recording.
 *
 * Put a YouTube link in `DEMO_YOUTUBE_URL` — watch, youtu.be, /embed/ or /shorts/
 * form, all parse — and the player section appears on the page, the header grows a
 * "Demo" cell, and the hero CTA scrolls to it instead of leaving the site. Leave it
 * empty and none of that renders: the CTA falls back to `DEMO_FALLBACK_URL` and the
 * page is exactly as it is today. Nothing else needs editing either way.
 */
const DEMO_YOUTUBE_URL = "";
const DEMO_FALLBACK_URL = "/hub";

const demoVideoId = youTubeId(DEMO_YOUTUBE_URL);

// Every section on the page, in the order you meet them. The header is the only
// map a first-time reader gets, so a section missing from it is a section they
// never learn exists. Labels are the short form: eight cells have to share one row.
const navLinks = [
  ...(demoVideoId ? ([["Demo", "#demo"]] as const) : []),
  ["Problem", "#problem"],
  ["How it works", "#how"],
  ["Intelligence", "#capabilities"],
  ["Voice", "#voice"],
  ["Architecture", "#system"],
  ["Extensions", "#field"],
  ["Evaluation", "#evidence"],
  ["Evidence", "#provenance"],
  ["FAQ", "#faq"],
] as const;

/**
 * Four questions that frame the shared evidence and decision workflow.
 */
const problemStats: { figure: string; label: string; body: string; source: string }[] = [
  {
    figure: "01",
    label: "What is connected?",
    body: "Documents, suppliers, incidents, transactions and security findings often live in separate systems, hiding the relationships between them.",
    source: "Fragmented information",
  },
  {
    figure: "02",
    label: "What changed?",
    body: "A revised source can change a fact that earlier agent memory, recommendations and approvals relied on.",
    source: "Changing evidence",
  },
  {
    figure: "03",
    label: "What can we trust?",
    body: "A confident answer is not enough. People need to see its source, age, verification state and missing evidence.",
    source: "Evidence validity",
  },
  {
    figure: "04",
    label: "What happens next?",
    body: "Affected decisions need an explanation, a responsible reviewer and an audit trail before a proposed action proceeds.",
    source: "Human review",
  },
];

/**
 * The five shared workflow stages, illustrated with the synthetic supplier
 * evidence-change case where a source revision affects a prior decision.
 */
const scenario: { tag: string; title: string; body: string }[] = [
  {
    tag: "Connect",
    title: "Bring the evidence together",
    body: "The workflow starts with authorized source records. Each extension connects the document, supplier, incident or event data it supports while preserving source identity and history.",
  },
  {
    tag: "Understand",
    title: "Follow the FalkorDB relationships",
    body: "Source versions, claims, agent memory, decisions and proposed actions are linked. The graph records what each conclusion depends on.",
  },
  {
    tag: "Investigate",
    title: "Find the affected decisions",
    body: "In the synthetic supplier-audit example, a verified procedure changes an inspection interval from 180 to 90 days. AIDTRACE traces the old fact to the memory and decision that used it.",
  },
  {
    tag: "Verify",
    title: "Check the evidence and uncertainty",
    body: "The system shows the source change and the dependency path. It re-evaluates the old decision against the newer fact instead of treating remembered context as permanent truth.",
  },
  {
    tag: "Review",
    title: "Hold the action and retain the history",
    body: "The earlier approval belongs to an older decision revision, so the synthetic proposed action is suspended. A person can inspect what changed before making a new decision.",
  },
];

/**
 * Each capability drives the vertical tab list and a composite card: a gradient
 * media panel on top and a white text block underneath. Every capability gets
 * its OWN mock, because a shared template made the section read as one repeated card.
 */
const capabilities: {
  id: string;
  name: string;
  banner: string;
  Mock: () => React.JSX.Element;
  eyebrow: string;
  title: string;
  body: string;
}[] = [
  {
    id: "briefs",
    name: "Proactive context",
    banner: "The right context reaches the person responsible for the decision",
    Mock: BriefsMock,
    eyebrow: "AIDTRACE review queue",
    title: "Context arrives before a decision",
    body: "AIDTRACE brings the source change, affected claims and previous review together before someone decides what to do next.",
  },
  {
    id: "copilot",
    name: "Evidence answers",
    banner: "Answers show supporting sources, authority and uncertainty",
    Mock: CopilotMock,
    eyebrow: "Evidence-aware answers",
    title: "An answer you can check",
    body: "Questions about a supplier or decision are answered with the linked records in view. Missing or conflicting evidence stays visible instead of becoming a confident guess.",
  },
  {
    id: "rca",
    name: "Connected risk",
    banner: "Investigate causes and dependencies with their evidence in view",
    Mock: RcaMock,
    eyebrow: "Connected investigation",
    title: "Trace a risk back to the record",
    body: "Specialist investigations follow dependencies across suppliers, incidents and decisions. Each extension contributes its own analysis while the graph retains the supporting path.",
  },
  {
    id: "compliance",
    name: "Governed findings",
    banner: "A finding is useful when its scope and supporting evidence are visible",
    Mock: ComplianceMock,
    eyebrow: "Decision governance",
    title: "See what supports a finding",
    body: "A recommendation can be reviewed against its sources, policy checks and current decision revision. An older approval does not silently authorize a changed conclusion.",
  },
  {
    id: "ingestion",
    name: "Connected sources",
    banner: "Different source formats retain their identity and context",
    Mock: IngestionMock,
    eyebrow: "Source lineage",
    title: "Start with the source record",
    body: "AIDTRACE keeps source versions distinct and links claims to the exact version that supports them. The Evidence Drift case uses synthetic source records; real uploaded-evidence adapters remain integration work.",
  },
  {
    id: "assets",
    name: "Relationship history",
    banner: "Ask what a relationship meant at the time of a decision",
    Mock: AssetsMock,
    eyebrow: "Temporal relationships",
    title: "Preserve what was known then",
    body: "The FalkorDB graph retains source revisions and the memories, decisions and approvals that depended on them. A later change can be compared with what was previously reviewed.",
  },
  {
    id: "governance",
    name: "Evidence validity",
    banner: "Uncertain information remains visible without becoming verified fact",
    Mock: GovernanceMock,
    eyebrow: "Evidence validity",
    title: "Uncertainty stays explicit",
    body: "AIDTRACE distinguishes verified sources, stale memory, contested claims and missing information. A change can trigger review without treating uncertain context as proof.",
  },
  {
    id: "field",
    name: "New observations",
    banner: "A new observation can start a review of connected evidence",
    Mock: FieldMock,
    eyebrow: "New observations",
    title: "Capture what people observe",
    body: "New records can prompt another investigation. The connected decision workflow compares them with prior evidence before a reviewer approves a revised action.",
  },
];

/** System-design diagram. Rendered from `docs/DIAGRAMS.md` to static SVG in
 *  `public/diagrams/` by `tools/render_diagrams.sh`. Deliberately not a runtime
 *  mermaid dependency: seven fixed pictures that only change when that file changes
 *  do not justify shipping a renderer to every visitor. */
function SystemDiagramImage({ src, alt }: { src: string; alt: string }) {
  return (
    /* eslint-disable-next-line @next/next/no-img-element -- a static vector, which
       next/image can neither resize nor re-encode; it would add a wrapper and nothing else. */
    <img
      src={src}
      alt={alt}
      /* Width is the only cap, and it never upscales. A max-height would bind first on
         the tall diagrams and shrink them further while leaving the panel empty either
         side; scaling a narrow one up to fill would render its labels at twice the size
         of the next tab's. Each file carries an explicit width and height, so the box is
         reserved before the SVG arrives.

         Below lg the card is only a few hundred px wide, narrow enough that fitting a
         plant architecture into it does not make it readable, only small. So the diagram
         keeps its natural width there and the panel scrolls instead.
         Not lazy: only the active tab's diagram is ever in the DOM. */
      decoding="async"
      className="mx-auto h-auto w-auto max-w-none object-contain lg:max-h-full lg:max-w-full"
    />
  );
}

/**
 * The system-design tabs. The card shows the diagram alone, so `alt` is its only
 * accessible representation, so it states what the picture shows rather than naming
 * the file, and is the one place a screen reader gets this content at all.
 */
const systemDesign: {
  id: string;
  name: string;
  src: string;
  alt: string;
}[] = [
  {
    id: "overview",
    name: "Overview",
    src: "/diagrams/overview.svg",
    alt: "End-to-end architecture: point of action, application core, async orchestration, intelligence services, knowledge stores and the model plane, with the human-authority gate.",
  },
  {
    id: "client",
    name: "Point of action",
    src: "/diagrams/client.svg",
    alt: "Point of action: a role-gated app shell over 44 routes, field surfaces with an offline write queue, and the desktop workspace.",
  },
  {
    id: "core",
    name: "Application core",
    src: "/diagrams/core.svg",
    alt: "Application core: rate limit, fail-closed OPA authorization and telemetry middleware, then token and site-scope dependencies, then 12 routers.",
  },
  {
    id: "orch",
    name: "Async orchestration",
    src: "/diagrams/orch.svg",
    alt: "Async orchestration: the durable Temporal ingestion pipeline, six Celery queues, the Go OT connector, and Redis Streams feeding the EEMUA push governor.",
  },
  {
    id: "svc",
    name: "Intelligence services",
    src: "/diagrams/svc.svg",
    alt: "Intelligence services: perception feeding hybrid retrieval, a two-pass safety gate that either answers with citations or refuses with sources, and a governance layer gated on human authority.",
  },
  {
    id: "data",
    name: "Knowledge & data",
    src: "/diagrams/data.svg",
    alt: "Knowledge and data stores: the Neo4j temporal graph, Qdrant vectors, Elasticsearch exact match and Supabase as the system of record.",
  },
  {
    id: "ext",
    name: "Model plane",
    src: "/diagrams/ext.svg",
    alt: "Model plane: the NIM to OpenRouter to Gemini to Ollama synthesis cascade, plus the OCR, NER, speech and embedding task models.",
  },
];

const audiences = [
  { name: "GreenChain", title: "Supply chain intelligence", shot: "workspace", body: "Explore supplier networks, facility dependencies, routes and alternative sourcing with the evidence behind each recommendation. The AIDTRACE globe shows connected entities in one workspace." },
  { name: "CyberFlow", title: "Cybersecurity intelligence", shot: "reliability", body: "Investigate connected findings, vulnerabilities and potential operational consequences. A graph relationship is a lead for review, not proof of compromise." },
  { name: "Operations", title: "Industrial intelligence", shot: "field", body: "Connect equipment, maintenance records, procedures, events and observations to support governed operational decisions. Inspect their lineage in the shared workspace." },
  { name: "Resolve", title: "Investigation intelligence with FALKOR DB", shot: "compliance", body: "Compare explanations, inspect evidence lineage and prepare recommendations for human review on FALKOR DB. The shared timeline makes changes visible across investigations." },
  { name: "Track 01", title: "Connected risk agents", shot: "turnaround", body: "Trace multi-hop relationships and preserve investigation steps before proposing a controlled action. The shared workspace exposes affected entities and dependencies." },
  { name: "Evidence", title: "Evidence and decision intelligence", shot: "offboarding", body: "Inspect source history, stale memory and decision dependencies when supporting information changes. Review the evidence before approving a revised action." },
] as const;

// Measured 2026-08-24 on the live stack, per benchmark/RESULTS.md.
type EvalBar = {
  label: string;
  note: string;
  value: number;
  display: string;
  /** Raw count behind the percentage. */
  badge: string;
  /** Small qualifier under the headline number. */
  sub: string;
  hero: boolean;
};
const evalBars: EvalBar[] = [
  { label: "Retrieval", note: "The fact reaches the model", value: 100, display: "100%", badge: "46/46", sub: "graded by fixed rules", hero: false },
  { label: "Provenance", note: "Sources cited", value: 100, display: "100%", badge: "46/46", sub: "every answer cited", hero: true },
  { label: "Answer quality", note: "One valid run", value: 87, display: "87%", badge: "40/46", sub: "95% confidence: 74 to 94", hero: false },
];

// The five harnesses beyond the Q&A grading, all from benchmark/RESULTS.md.
const evalSuites: {
  name: string;
  headline: string;
  headlineNote: string;
  rows: [string, string][];
}[] = [
  {
    name: "Adversarial safety",
    headline: "0 unsafe",
    headlineNote: "15 questions written to make it guess",
    rows: [["Unsafe answers", "0"], ["Refusals", "12"], ["Answerable ones answered", "yes"], ["Prompt injection held", "yes"]],
  },
  {
    // The PS names "knowledge graph linkage completeness" as an evaluation
    // focus, so it belongs on the page as its own figure rather than implied.
    // Document-centric (run_kg_completeness.py), not the raw asset count —
    // that query has no test-artifact filter, see status.md.
    name: "Knowledge graph linkage",
    headline: "18 / 20",
    headlineNote: "Active vault documents with a verified knowledge edge",
    rows: [["Documents linked", "90%"], ["Dangling provenance", "0"], ["Alias resolution", "2/2"], ["MDM identity", "2/2"]],
  },
  {
    name: "Proactive briefs · Layer 8",
    headline: "6 / 6",
    headlineNote: "All graded checks pass. Soft targets are reported, not scored",
    rows: [["Work order raised", "2/2"], ["Permit to work", "2/2"], ["Tag-out · inspection", "1/1 · 1/1"], ["Soft targets unmet", "7, disclosed"]],
  },
  {
    name: "Compliance gap detection",
    headline: "F1 0.912",
    headlineNote: "Zero false positives across 52 pairs",
    rows: [["Precision", "1.000"], ["Recall", "0.838"], ["True / false positives", "31 / 0"], ["Full status agreement", "46 / 52"]],
  },
  {
    name: "Entity extraction · Layer 0",
    headline: "F1 0.805",
    headlineNote: "40 labels, 15 extractions, no fallback model used",
    rows: [["Precision", "0.786"], ["Recall", "0.825"], ["ASSET_TAG F1", "0.889 (n=30)"], ["PERSON F1", "1.000 (n=7)"]],
  },
  {
    name: "Per-layer smoke",
    headline: "13 / 13",
    headlineNote: "Every layer answered on the live stack",
    rows: [["Slowest read", "search 3.7 s"], ["Assets", "1.7 s"], ["Graph / Vault", "212 / 163 ms"], ["Failures", "0"]],
  },
  {
    name: "Time to a trusted answer",
    headline: "−19.9%",
    headlineNote: "Modelled, compared against BM25 keyword search",
    rows: [["Traditional", "124.0 min / 46 q"], ["Industrial extension", "99.4 min / 46 q"], ["Docs opened", "1.00 vs 1.35"], ["Raw machine time", "loses: 9.6 s vs 28 ms"]],
  },
  {
    name: "Concurrency sweep",
    headline: "0% errors",
    headlineNote: "2275 requests across 9 read endpoints, up to 50 users",
    rows: [["p50 · 1 → 50 VU", "136 → 500 ms"], ["p95 at 50 VU", "1840 ms"], ["Throughput", "5.8 → 74.5 rps"], ["Knee of the curve", "50 users"]],
  },
  {
    name: "Soak · 60 minutes",
    headline: "No leak signal",
    headlineNote: "Steady load against cloud stores, reads only",
    rows: [["Memory slope", "+8.6 MB/h"], ["Connections", "+4.2/h"], ["Errors", "0.11% of 37,842"], ["Idle recovery", "4 / 4 endpoints"]],
  },
  {
    // Every row here is the same 2026-10-17 run the chart above reports, taken
    // from one `run_benchmark.py` output. Quoting the percentiles from one run
    // beside another run's provider mix is the mistake this card is arranged to
    // prevent — figures from earlier sweeps had drifted into the docs.
    name: "Synthesis latency",
    headline: "p50 2.6 s",
    headlineNote: "Nemotron 3 Super on NVIDIA NIM at the 60 second cap, quoted with its slowest cases",
    rows: [["p95", "5.3 s"], ["Mean", "2.8 s"], ["Graded questions", "46"], ["Answered by", "nim 40 · refused 6"]],
  },
];

/**
 * The technology under the eight capability screens, plus the cross-cutting work
 * that never gets a screen of its own. NOT a superset of the tabs and not a
 * subset either — a different axis, which is why the counts differ and why the
 * block states that above itself. Seven of the eight tabs have no row here (the
 * governor, refusals, quarantine, offline capture, root-cause ranking, temporal
 * supersession), and four rows here have no tab (blast radius, PII redaction,
 * Management of Change, the drift stop).
 *
 * One array rather than two: the page used to split these into "what the brief
 * asked for" and "what it did not", which is a fact about the assignment rather
 * than about the product, and a reader has no way to check it. Ten across two
 * columns fills five rows exactly, so the grid closes with no cell left over.
 */
const capabilityList: [string, string][] = [
  // search_service.hybrid_search: ES + Qdrant always, the graph too once the
  // question names an asset; _fuse does reciprocal-rank fusion, then orders by
  // authority_level ASC before relevance.
  ["Connect authorized information", "Documents, suppliers, incidents, transactions and findings enter the shared investigation workflow."],
  // 6 labels in db/neo4j/init_schema.cypher; the 6 edge properties are the
  // non-negotiable write contract in CLAUDE.md.
  ["FalkorDB relationship graph", "Source versions, claims, memories, decisions and approvals form inspectable dependency paths."],
  // /compliance/nonconformance reads conflicts + quarantine; moc_items runs
  // draft → pending_approval → approved, with approved_by and approved_at.
  ["Evidence verification", "Conflicts, missing support and uncertain claims stay visible for review."],
  ["Decision governance", "A changed recommendation waits for a current human approval before action."],
  // document_pipeline.py: every activity carries DEFAULT_RETRY, maximum_attempts 5.
  ["Persistent agent memory", "Agents can retrieve previous findings with the source evidence and validity state that supports them."],
  // GraphService.get_blast_radius, surfaced by /governance.
  ["Impact analysis", "Follow a changed source through dependent claims, memories, decisions and proposed actions."],
  // services/pii.py — export boundary only, and the patterns are bounded so
  // equipment tags and part numbers never match.
  ["Source lineage", "Each important conclusion points back to its source version, with uncertainty kept explicit."],
  // circuit_breaker.check: z > 2.0 on 7-day overrides vs the prior three weeks;
  // link_to_graph then writes zero edges and raises review_required.
  ["Evidence Drift", "When support changes, affected memory and decisions are marked for re-evaluation and stale approvals are blocked."],
];


/** Six illustrated checkpoints in the synthetic Evidence Drift dependency path. */
const edgeProperties: { name: string; value: string; note: string }[] = [
  { name: "source_version", value: "version 2", note: "The revised audit procedure is recorded as a new source version." },
  { name: "changed_claim", value: "90 days", note: "The newer evidence changes the supplier audit interval from 180 days." },
  { name: "dependent_memory", value: "stale", note: "An agent memory based on the previous interval needs re-evaluation." },
  { name: "decision_revision", value: "revision 2", note: "The decision records which evidence revision it evaluated." },
  { name: "prior_approval", value: "revision 1", note: "Approval for an older decision revision cannot authorize a revised action." },
  { name: "action_state", value: "suspended", note: "The proposed action waits for a current human review." },
];

const faqGroups = [
  {
    name: "Basics",
    items: [
      ["What does AIDTRACE do?", "AIDTRACE connects evidence, relationships, agent memory and decisions across specialized workflows. It helps people inspect what changed, what is affected and which conclusions need review."],
      ["Why use FalkorDB?", "FalkorDB stores connected source versions, claims, memories, decisions and approvals. Following those links makes a dependency path inspectable when evidence changes."],
      ["Is this one workflow or several products?", "The shared process connects, investigates, verifies and reviews evidence. GreenChain, CyberFlow, Operations, Resolve and Track 01 contribute specialized algorithms and interfaces with FALKOR DB."],
    ],
  },
  {
    name: "Decisions",
    items: [
      ["What happens when evidence changes?", "The Evidence Drift workflow follows the recorded dependency links, re-evaluates affected conclusions and can suspend a proposed action whose approval belongs to an earlier decision revision."],
      ["What if the evidence is uncertain?", "AIDTRACE keeps missing, conflicting or unverified evidence explicit. Low-confidence extractions are held for human review rather than silently promoted."],
      ["Does AI make the final decision?", "Recommendations support human judgment. A proposed action that requires approval remains subject to the relevant review and authorization checks."],
      ["Can I see why a recommendation changed?", "The evidence path shows the source version and the claims, memories or decisions that depended on it. The synthetic drift demonstration also records the previous and current decision revisions."],
    ],
  },
  {
    name: "Evidence",
    items: [
      ["Can I trace a conclusion to its source?", "The decision graph links claims to source versions and links derived memories and decisions to the claims they used. The available lineage view exposes those relationships."],
      ["What is persistent agent memory?", "It is a stored finding with a source and a validity state that can be recalled later. A stale or unverified memory should not silently become current evidence."],
      ["Is every source connected today?", "No. The current Evidence Drift case uses synthetic source records. Real uploaded-evidence ingestion and adapters for other channels remain separate integration work."],
    ],
  },
  {
    name: "Access",
    items: [
      ["Who can see a site's graph?", "Graph routes derive site scope from the authenticated user and apply role checks. A site's evidence is queried within its own graph."],
      ["Who can approve an action?", "Approval is a human-governed decision. In the synthetic drift flow, an approval is tied to the exact decision revision it reviewed."],
      ["Can I explore the workspace?", "Open the workspace to inspect the connected views and specialist entry points. The Evidence Drift run is marked as a synthetic demonstration."],
    ],
  },
  {
    name: "Evaluation",
    items: [
      ["What do the figures on this page measure?", "The displayed numeric benchmark belongs to the industrial question-answering extension. It does not measure the full AIDTRACE platform or every FalkorDB workflow."],
      ["How should graph intelligence be evaluated?", "Use reproducible tests for dependency paths, source lineage, memory persistence, stale-information detection, decision consistency, authorization and site isolation."],
      ["Are the examples real-world deployment evidence?", "No. The supplier-audit Evidence Drift case is deterministic and synthetic. Local tests show the bounded mechanism; they do not establish production performance or real-world decision quality."],
      ["Does the demo execute an external action?", "No. It can suspend a synthetic proposed action when the approval no longer matches the current revision, but it does not carry out procurement or operational changes."],
      ["Where can I check the implementation?", "The repository includes the graph contracts, tests, implementation reports and known limits. The workspace exposes the connected views and labels synthetic scenarios."],
    ],
  },
] as const;

// Footer links point only at real destinations: page anchors.
const footerColumns: { heading: string; links: [string, string][] }[] = [
  { heading: "Product", links: [["The problem", "#problem"], ["Intelligence engine", "#capabilities"], ["Extensions", "#field"]] },
  { heading: "How it works", links: [["Shared workflow", "#how"], ["Architecture", "#system"], ["Evidence", "#provenance"], ["Evaluation", "#evidence"]] },
  { heading: "Resources", links: [["FAQ", "#faq"]] },
];
/* ── Capability mocks, one bespoke composition each ─────────────────────
   Shared atoms only; the layouts deliberately differ so the tab list reveals a
   genuinely different picture each time rather than the same card retitled. */

/** White chip used across the mocks. */
function Slab({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`lp-mock-sm bg-white px-3 py-2 text-[12px] text-(--lp-ink) ${className}`}>{children}</div>;
}

/** Briefs: an illustrative alert queue alongside the approval review gate. */
function BriefsMock() {
  return (
    <div>
      <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-white/75">Governor · this hour</p>
      <div className="mt-3 flex gap-1.5">
        {[true, true, true, true, false, false].map((used, i) => (
          <span key={i} className={`h-8 flex-1 ${used ? "bg-white" : "border border-white/45 bg-white/10"}`} />
        ))}
      </div>
      <div className="mt-2 flex justify-between text-[11px] text-white/80">
        <span>4 of 6 delivered</span>
        <span>2 remaining</span>
      </div>

      <div className="mt-6 grid gap-2 sm:grid-cols-2">
        <Slab>
          <p className="text-[9px] font-semibold uppercase tracking-[0.08em] text-(--lp-accent-text)">Dispatched 07:41</p>
          <p className="mt-1 font-semibold">Supplier audit rule changed</p>
          <p className="mt-1 text-[11px] text-(--lp-muted)">Priority 1 · to the decision owner</p>
        </Slab>
        <Slab className="border-l-4 border-(--lp-accent)">
          <p className="text-[9px] font-semibold uppercase tracking-[0.08em] text-(--lp-accent-text)">Approval gate</p>
          <p className="mt-1 font-semibold">Requires fresh review</p>
          <p className="mt-1 text-[11px] text-(--lp-muted)">Stale approval cannot authorize action</p>
        </Slab>
      </div>

      <div className="mt-4 flex items-center gap-2 bg-black/45 px-3 py-2">
        <span aria-hidden="true" className="size-2 shrink-0 bg-(--lp-accent)" />
        <span className="text-[11px] text-white/85">Next routine alert held; decision review remains visible</span>
      </div>
    </div>
  );
}

/** Copilot: question, governed answer, and the refusal path beside it. */
function CopilotMock() {
  return (
    <div>
      <div className="ml-auto w-fit max-w-[85%] bg-black/55 px-3 py-2 text-[12px] text-white">
        What changed in the supplier audit evidence?
      </div>

      <div className="mt-3 max-w-[92%] border-l-2 border-(--lp-accent) bg-white p-3">
        <p className="text-[9px] font-semibold uppercase tracking-[0.08em] text-(--lp-accent-text)">Checked answer</p>
        <div className="mt-2 space-y-1.5" aria-hidden="true">
          <span className="block h-1.5 bg-(--lp-band)" />
          <span className="block h-1.5 w-5/6 bg-(--lp-band)" />
          <span className="block h-1.5 w-2/3 bg-(--lp-band)" />
        </div>
        <div className="mt-3 flex flex-wrap gap-1.5 text-[10px]">
          <span className="bg-(--lp-accent-strong) px-2 py-1 font-medium text-white">Source path</span>
          <span className="border border-(--lp-line) px-2 py-1 text-(--lp-muted)">Version: current</span>
        </div>
        <div className="mt-3">
          <div className="flex justify-between text-[10px] text-(--lp-muted)"><span>Decision state</span><span className="font-semibold text-(--lp-ink)">Review</span></div>
          <div className="mt-1 h-1.5 bg-(--lp-band)"><span className="block h-full w-[91%] bg-(--lp-accent)" /></div>
        </div>
      </div>

      <div className="mt-3 flex items-start gap-2 border border-dashed border-white/50 px-3 py-2">
        <span aria-hidden="true" className="mt-0.5 size-2 shrink-0 bg-white" />
        <span className="text-[11px] leading-4 text-white/85">
          Missing or conflicting support returns an <strong className="font-semibold text-white">uncertainty notice</strong> with the available sources.
        </span>
      </div>
    </div>
  );
}

/** An illustrative time slider over the source-version change and dependent claim. */
function AssetsMock() {
  return (
    <div>
      <div className="flex items-center justify-between">
        <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-white/75">Graph as of</p>
        <span className="bg-black/60 px-2 py-1 text-[11px] font-semibold text-white">2025-05-15</span>
      </div>

      <div className="relative mt-3 h-1 bg-white/30">
        <span aria-hidden="true" className="absolute left-[62%] top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 bg-(--lp-accent)" />
      </div>
      <div className="mt-1.5 flex justify-between text-[10px] uppercase tracking-[0.06em] text-white/70">
        <span>Earlier source</span><span>Current source</span>
      </div>

      <div className="mt-6 grid grid-cols-[1fr_auto_1fr] items-center gap-2">
        <Slab className="text-center font-semibold">Source v2</Slab>
        <div className="text-center">
          <p className="text-[9px] uppercase tracking-[0.06em] text-white/80">supports</p>
          <div aria-hidden="true" className="my-1 h-px bg-(--lp-accent)" />
          <p className="text-[9px] text-white/70">verified</p>
        </div>
        <Slab className="text-center font-semibold">Claim</Slab>
      </div>

      <div className="mt-3 grid grid-cols-[1fr_auto_1fr] items-center gap-2 opacity-55">
        <Slab className="text-center line-through">180-day rule</Slab>
        <div className="text-center">
          <p className="text-[9px] uppercase tracking-[0.06em] text-white/80">superseded</p>
          <div aria-hidden="true" className="my-1 h-px border-t border-dashed border-white/70" />
          <p className="text-[9px] text-white/70">valid_to closed</p>
        </div>
        <Slab className="text-center font-semibold">90-day rule</Slab>
      </div>

      <p className="mt-4 bg-black/45 px-3 py-2 text-[11px] text-white/85">
        The prior version remains in the history so the earlier decision can be traced and re-evaluated.
      </p>
    </div>
  );
}

/** Governance: a one-way gate splitting the stream by confidence. */
function GovernanceMock() {
  const rows = [
    ["Current audit procedure", "0.94", true],
    ["Supplier risk note", "0.61", false],
    ["Unattributed attachment", "0.42", false],
  ] as const;
  return (
    <div>
      <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-white/75">Illustrative evidence review gate</p>
      <div className="mt-3 space-y-1.5">
        {rows.map(([name, score, promoted]) => (
          <div key={name} className="grid grid-cols-[1fr_auto_auto] items-center gap-2 bg-white px-3 py-2">
            <span className="truncate text-[12px] text-(--lp-ink)">{name}</span>
            <span className={`text-[12px] font-semibold ${promoted ? "text-(--lp-ink)" : "text-(--lp-accent-text)"}`}>{score}</span>
            <span className={`px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.06em] ${promoted ? "bg-(--lp-band) text-(--lp-muted)" : "bg-(--lp-accent-strong) text-white"}`}>
              {promoted ? "Graph" : "Held"}
            </span>
          </div>
        ))}
      </div>

      {/* Counted off the rows above rather than typed in: a tile that disagreed
          with the three lines directly over it is the one thing this panel
          cannot afford to get wrong. */}
      <div className="mt-4 grid grid-cols-2 gap-2">
        <div className="border border-white/40 px-3 py-2.5 text-center">
          <p className="lp-display text-[24px] text-white">{rows.filter(([, , promoted]) => promoted).length}</p>
          <p className="mt-1 text-[10px] uppercase tracking-[0.06em] text-white/75">Into the graph</p>
        </div>
        <div className="bg-white px-3 py-2.5 text-center">
          <p className="lp-display text-[24px] text-(--lp-accent-text)">{rows.filter(([, , promoted]) => !promoted).length}</p>
          <p className="mt-1 text-[10px] uppercase tracking-[0.06em] text-(--lp-muted)">Held for review</p>
        </div>
      </div>
      <p className="mt-3 text-center text-[11px] text-white/85">Promotion is a human decision. There is no auto-promote.</p>
    </div>
  );
}

/** Field capture: a device with a mic and an offline write queue. */
function FieldMock() {
  const queue = [
    ["Supplier incident note", "Sent"],
    ["Audit document update", "Queued"],
    ["Photo · source evidence", "Queued"],
  ] as const;
  return (
    <div className="grid gap-5 sm:grid-cols-[auto_1fr] sm:items-start">
      <div className="mx-auto w-[132px] border-2 border-white/60 bg-black/55 p-3 sm:mx-0">
        <p className="text-center text-[9px] uppercase tracking-[0.08em] text-(--lp-accent)">● Offline</p>
        <div className="mt-4 grid place-items-center">
          <span className="grid size-14 place-items-center rounded-full bg-(--lp-accent) text-white">
            <svg width="18" height="22" viewBox="0 0 20 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <rect x="6" y="1" width="8" height="14" rx="4" />
              <path d="M3 11a7 7 0 0 0 14 0M10 18v5" />
            </svg>
          </span>
        </div>
        <p className="mt-3 text-center text-[10px] font-medium text-white">Hold to record</p>
      </div>

      <div>
        <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-white/75">Write queue · on device</p>
        <div className="mt-3 space-y-1.5">
          {queue.map(([text, state]) => (
            <div key={text} className="flex items-center justify-between gap-2 bg-white px-3 py-2">
              <span className="truncate text-[12px] text-(--lp-ink)">{text}</span>
              <span className={`shrink-0 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.06em] ${state === "Sent" ? "bg-(--lp-band) text-(--lp-muted)" : "bg-(--lp-accent-strong) text-white"}`}>
                {state}
              </span>
            </div>
          ))}
        </div>
        <p className="mt-4 bg-black/45 px-3 py-2 text-[11px] text-white/85">
          Multilingual field notes with language selection or auto-detection, routed for engineering review.
        </p>
      </div>
    </div>
  );
}

/** Ingestion: the heterogeneous-input claim, shown as six formats into one graph. */
function IngestionMock() {
  // The PS names six input classes. All six are handled, so all six are shown:
  // spreadsheets and email archives are the two people assume you skipped.
  const inputs = [
    ["Native PDF", "Parsed direct · no API cost"],
    ["Scanned form", "OCR, multi-script"],
    ["Security finding", "Connected record"],
    ["Spreadsheet", "xlsx · xls · ods"],
    ["Email archive", "eml · mbox + attachments"],
    ["Multilingual voice", "Speech to text"],
  ] as const;
  return (
    <div>
      <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-white/75">One pipeline · six kinds of source</p>
      <div className="mt-3 grid gap-1.5 sm:grid-cols-2">
        {inputs.map(([name, how]) => (
          <Slab key={name}>
            <p className="font-semibold">{name}</p>
            <p className="mt-0.5 text-[11px] text-(--lp-muted)">{how}</p>
          </Slab>
        ))}
      </div>

      <div className="mt-4 flex items-center gap-2 text-[10px] uppercase tracking-[0.06em] text-white/80">
        <span aria-hidden="true" className="h-px flex-1 bg-(--lp-accent)" />
        <span>extract · link · index</span>
        <span aria-hidden="true" className="h-px flex-1 bg-(--lp-accent)" />
      </div>

      <div className="mt-4 grid grid-cols-3 gap-1.5 text-center">
        {[["FalkorDB", "relationships"], ["Sources", "provenance"], ["Memory", "context"]].map(([store, role]) => (
          <div key={store} className="border border-white/40 px-2 py-2.5">
            <p className="text-[12px] font-semibold text-white">{store}</p>
            <p className="mt-0.5 text-[10px] text-white/70">{role}</p>
          </div>
        ))}
      </div>

      <p className="mt-4 bg-black/45 px-3 py-2 text-[11px] text-white/85">
        Different records enter one connected workflow. Relationships and source history explain what each claim depends on.
      </p>
    </div>
  );
}

/** RCA: hypotheses ranked by evidence weight, with the timeline behind them. */
function RcaMock() {
  const hypotheses = [
    ["Audit interval revised", 82, "Current procedure · source version 2"],
    ["Earlier decision affected", 61, "Linked claim · memory · approval"],
    ["Unverified supplier note", 28, "Source still requires review"],
  ] as const;
  return (
    <div>
      <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-white/75">Illustrative evidence comparison</p>
      <div className="mt-3 space-y-2">
        {hypotheses.map(([name, weight, basis]) => (
          <div key={name} className="bg-white px-3 py-2">
            <div className="flex items-baseline justify-between gap-2">
              <span className="truncate text-[12px] font-semibold text-(--lp-ink)">{name}</span>
              <span className="text-[12px] font-semibold text-(--lp-accent-text)">{weight}</span>
            </div>
            <div className="mt-1.5 h-1.5 bg-(--lp-band)">
              <span className="block h-full bg-(--lp-accent)" style={{ width: `${weight}%` }} />
            </div>
            <p className="mt-1.5 text-[10px] text-(--lp-muted)">{basis}</p>
          </div>
        ))}
      </div>
      <p className="mt-4 bg-black/45 px-3 py-2 text-[11px] text-white/85">
        Each explanation carries its supporting source. Unverified evidence stays visible for review.
      </p>
    </div>
  );
}

/** Illustrative evidence and approval states for a decision review. */
function ComplianceMock() {
  const clauses = [
    ["Source lineage", "Claim", "Covered"],
    ["Decision approval", "Action", "Gap"],
    ["Supplier note", "Memory", "Unverified"],
  ] as const;
  return (
    <div>
      <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-white/75">Evidence × decision · review state</p>
      <div className="mt-3 space-y-1.5">
        {clauses.map(([clause, asset, state]) => (
          <div key={clause} className="grid grid-cols-[1fr_auto_auto] items-center gap-2 bg-white px-3 py-2">
            <span className="truncate text-[12px] text-(--lp-ink)">{clause}</span>
            <span className="text-[11px] text-(--lp-muted)">{asset}</span>
            <span
              className={`px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.06em] ${state === "Gap"
                ? "bg-(--lp-accent-strong) text-white"
                : state === "Unverified"
                  ? "border border-(--lp-accent) text-(--lp-accent-text)"
                  : "bg-(--lp-band) text-(--lp-muted)"
                }`}
            >
              {state}
            </span>
          </div>
        ))}
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2">
        <div className="bg-white px-3 py-2.5 text-center">
          <p className="lp-display text-[24px] text-(--lp-ink)">1</p>
          <p className="mt-1 text-[10px] uppercase tracking-[0.06em] text-(--lp-muted)">Approval gap shown</p>
        </div>
        <div className="border border-white/40 px-3 py-2.5 text-center">
          <p className="lp-display text-[24px] text-white">0</p>
          <p className="mt-1 text-[10px] uppercase tracking-[0.06em] text-white/75">Actions executed</p>
        </div>
      </div>
      <p className="mt-3 text-center text-[11px] text-white/85">A missing approval blocks a proposed action. Unverified evidence stays visible and cannot be counted as confirmed support.</p>
    </div>
  );
}

/* ── Tech logos ───────────────────────────────────────────────────────────
   Real brand marks, inlined as path data at build time: simple-icons (CC0) for
   the single-colour ones and devicon for the two-tone ones. Nothing is fetched
   at runtime and nothing is hand-traced.

   Colours are each brand's own, lifted only where the true colour would vanish
   against the dark band (Next.js and GitHub are black; Elasticsearch's charcoal
   becomes a light grey).

   Qdrant is absent: neither icon set carries its mark. Drop the real SVG into
   public/logos/ and add an entry here. */

const LOGO = "size-7 shrink-0";

type Tech = { name: string; viewBox: string; paths: { d: string; fill: string }[] };

const techStack: Tech[] = [
  { name: "Next.js", viewBox: "0 0 24 24", paths: [{ d: "M18.665 21.978C16.758 23.255 14.465 24 12 24 5.377 24 0 18.623 0 12S5.377 0 12 0s12 5.377 12 12c0 3.583-1.574 6.801-4.067 9.001L9.219 7.2H7.2v9.596h1.615V9.251l9.85 12.727Zm-3.332-8.533 1.6 2.061V7.2h-1.6v6.245Z", fill: "#ffffff" }] },
  { name: "React", viewBox: "0 0 24 24", paths: [{ d: "M14.23 12.004a2.236 2.236 0 0 1-2.235 2.236 2.236 2.236 0 0 1-2.236-2.236 2.236 2.236 0 0 1 2.235-2.236 2.236 2.236 0 0 1 2.236 2.236zm2.648-10.69c-1.346 0-3.107.96-4.888 2.622-1.78-1.653-3.542-2.602-4.887-2.602-.41 0-.783.093-1.106.278-1.375.793-1.683 3.264-.973 6.365C1.98 8.917 0 10.42 0 12.004c0 1.59 1.99 3.097 5.043 4.03-.704 3.113-.39 5.588.988 6.38.32.187.69.275 1.102.275 1.345 0 3.107-.96 4.888-2.624 1.78 1.654 3.542 2.603 4.887 2.603.41 0 .783-.09 1.106-.275 1.374-.792 1.683-3.263.973-6.365C22.02 15.096 24 13.59 24 12.004c0-1.59-1.99-3.097-5.043-4.032.704-3.11.39-5.587-.988-6.38-.318-.184-.688-.277-1.092-.278zm-.005 1.09v.006c.225 0 .406.044.558.127.666.382.955 1.835.73 3.704-.054.46-.142.945-.25 1.44-.96-.236-2.006-.417-3.107-.534-.66-.905-1.345-1.727-2.035-2.447 1.592-1.48 3.087-2.292 4.105-2.295zm-9.77.02c1.012 0 2.514.808 4.11 2.28-.686.72-1.37 1.537-2.02 2.442-1.107.117-2.154.298-3.113.538-.112-.49-.195-.964-.254-1.42-.23-1.868.054-3.32.714-3.707.19-.09.4-.127.563-.132zm4.882 3.05c.455.468.91.992 1.36 1.564-.44-.02-.89-.034-1.345-.034-.46 0-.915.01-1.36.034.44-.572.895-1.096 1.345-1.565zM12 8.1c.74 0 1.477.034 2.202.093.406.582.802 1.203 1.183 1.86.372.64.71 1.29 1.018 1.946-.308.655-.646 1.31-1.013 1.95-.38.66-.773 1.288-1.18 1.87-.728.063-1.466.098-2.21.098-.74 0-1.477-.035-2.202-.093-.406-.582-.802-1.204-1.183-1.86-.372-.64-.71-1.29-1.018-1.946.303-.657.646-1.313 1.013-1.954.38-.66.773-1.286 1.18-1.868.728-.064 1.466-.098 2.21-.098zm-3.635.254c-.24.377-.48.763-.704 1.16-.225.39-.435.782-.635 1.174-.265-.656-.49-1.31-.676-1.947.64-.15 1.315-.283 2.015-.386zm7.26 0c.695.103 1.365.23 2.006.387-.18.632-.405 1.282-.66 1.933-.2-.39-.41-.783-.64-1.174-.225-.392-.465-.774-.705-1.146zm3.063.675c.484.15.944.317 1.375.498 1.732.74 2.852 1.708 2.852 2.476-.005.768-1.125 1.74-2.857 2.475-.42.18-.88.342-1.355.493-.28-.958-.646-1.956-1.1-2.98.45-1.017.81-2.01 1.085-2.964zm-13.395.004c.278.96.645 1.957 1.1 2.98-.45 1.017-.812 2.01-1.086 2.964-.484-.15-.944-.318-1.37-.5-1.732-.737-2.852-1.706-2.852-2.474 0-.768 1.12-1.742 2.852-2.476.42-.18.88-.342 1.356-.494zm11.678 4.28c.265.657.49 1.312.676 1.948-.64.157-1.316.29-2.016.39.24-.375.48-.762.705-1.158.225-.39.435-.788.636-1.18zm-9.945.02c.2.392.41.783.64 1.175.23.39.465.772.705 1.143-.695-.102-1.365-.23-2.006-.386.18-.63.406-1.282.66-1.933zM17.92 16.32c.112.493.2.968.254 1.423.23 1.868-.054 3.32-.714 3.708-.147.09-.338.128-.563.128-1.012 0-2.514-.807-4.11-2.28.686-.72 1.37-1.536 2.02-2.44 1.107-.118 2.154-.3 3.113-.54zm-11.83.01c.96.234 2.006.415 3.107.532.66.905 1.345 1.727 2.035 2.446-1.595 1.483-3.092 2.295-4.11 2.295-.22-.005-.406-.05-.553-.132-.666-.38-.955-1.834-.73-3.703.054-.46.142-.944.25-1.438zm4.56.64c.44.02.89.034 1.345.034.46 0 .915-.01 1.36-.034-.44.572-.895 1.095-1.345 1.565-.455-.47-.91-.993-1.36-1.565z", fill: "#61dafb" }] },
  { name: "TypeScript", viewBox: "0 0 24 24", paths: [{ d: "M1.125 0C.502 0 0 .502 0 1.125v21.75C0 23.498.502 24 1.125 24h21.75c.623 0 1.125-.502 1.125-1.125V1.125C24 .502 23.498 0 22.875 0zm17.363 9.75c.612 0 1.154.037 1.627.111a6.38 6.38 0 0 1 1.306.34v2.458a3.95 3.95 0 0 0-.643-.361 5.093 5.093 0 0 0-.717-.26 5.453 5.453 0 0 0-1.426-.2c-.3 0-.573.028-.819.086a2.1 2.1 0 0 0-.623.242c-.17.104-.3.229-.393.374a.888.888 0 0 0-.14.49c0 .196.053.373.156.529.104.156.252.304.443.444s.423.276.696.41c.273.135.582.274.926.416.47.197.892.407 1.266.628.374.222.695.473.963.753.268.279.472.598.614.957.142.359.214.776.214 1.253 0 .657-.125 1.21-.373 1.656a3.033 3.033 0 0 1-1.012 1.085 4.38 4.38 0 0 1-1.487.596c-.566.12-1.163.18-1.79.18a9.916 9.916 0 0 1-1.84-.164 5.544 5.544 0 0 1-1.512-.493v-2.63a5.033 5.033 0 0 0 3.237 1.2c.333 0 .624-.03.872-.09.249-.06.456-.144.623-.25.166-.108.29-.234.373-.38a1.023 1.023 0 0 0-.074-1.089 2.12 2.12 0 0 0-.537-.5 5.597 5.597 0 0 0-.807-.444 27.72 27.72 0 0 0-1.007-.436c-.918-.383-1.602-.852-2.053-1.405-.45-.553-.676-1.222-.676-2.005 0-.614.123-1.141.369-1.582.246-.441.58-.804 1.004-1.089a4.494 4.494 0 0 1 1.47-.629 7.536 7.536 0 0 1 1.77-.201zm-15.113.188h9.563v2.166H9.506v9.646H6.789v-9.646H3.375z", fill: "#3178c6" }] },
  { name: "Tailwind CSS", viewBox: "0 0 24 24", paths: [{ d: "M12.001,4.8c-3.2,0-5.2,1.6-6,4.8c1.2-1.6,2.6-2.2,4.2-1.8c0.913,0.228,1.565,0.89,2.288,1.624 C13.666,10.618,15.027,12,18.001,12c3.2,0,5.2-1.6,6-4.8c-1.2,1.6-2.6,2.2-4.2,1.8c-0.913-0.228-1.565-0.89-2.288-1.624 C16.337,6.182,14.976,4.8,12.001,4.8z M6.001,12c-3.2,0-5.2,1.6-6,4.8c1.2-1.6,2.6-2.2,4.2-1.8c0.913,0.228,1.565,0.89,2.288,1.624 c1.177,1.194,2.538,2.576,5.512,2.576c3.2,0,5.2-1.6,6-4.8c-1.2,1.6-2.6,2.2-4.2,1.8c-0.913-0.228-1.565-0.89-2.288-1.624 C10.337,13.382,8.976,12,6.001,12z", fill: "#38bdf8" }] },
  { name: "Python", viewBox: "0 0 128 128", paths: [{ d: "M63.391 1.988c-4.222.02-8.252.379-11.8 1.007-10.45 1.846-12.346 5.71-12.346 12.837v9.411h24.693v3.137H29.977c-7.176 0-13.46 4.313-15.426 12.521-2.268 9.405-2.368 15.275 0 25.096 1.755 7.311 5.947 12.519 13.124 12.519h8.491V67.234c0-8.151 7.051-15.34 15.426-15.34h24.665c6.866 0 12.346-5.654 12.346-12.548V15.833c0-6.693-5.646-11.72-12.346-12.837-4.244-.706-8.645-1.027-12.866-1.008zM50.037 9.557c2.55 0 4.634 2.117 4.634 4.721 0 2.593-2.083 4.69-4.634 4.69-2.56 0-4.633-2.097-4.633-4.69-.001-2.604 2.073-4.721 4.633-4.721z", fill: "#3776ab" }, { d: "M91.682 28.38v10.966c0 8.5-7.208 15.655-15.426 15.655H51.591c-6.756 0-12.346 5.783-12.346 12.549v23.515c0 6.691 5.818 10.628 12.346 12.547 7.816 2.297 15.312 2.713 24.665 0 6.216-1.801 12.346-5.423 12.346-12.547v-9.412H63.938v-3.138h37.012c7.176 0 9.852-5.005 12.348-12.519 2.578-7.735 2.467-15.174 0-25.096-1.774-7.145-5.161-12.521-12.348-12.521h-9.268zM77.809 87.927c2.561 0 4.634 2.097 4.634 4.692 0 2.602-2.074 4.719-4.634 4.719-2.55 0-4.633-2.117-4.633-4.719 0-2.595 2.083-4.692 4.633-4.692z", fill: "#ffd43b" }] },
  { name: "FastAPI", viewBox: "0 0 24 24", paths: [{ d: "M12 .0387C5.3729.0384.0003 5.3931 0 11.9988c-.001 6.6066 5.372 11.9628 12 11.9625 6.628.0003 12.001-5.3559 12-11.9625-.0003-6.6057-5.3729-11.9604-12-11.96m-.829 5.4153h7.55l-7.5805 5.3284h5.1828L5.279 18.5436q2.9466-6.5444 5.892-13.0896", fill: "#0aa89e" }] },
  { name: "Go", viewBox: "0 0 24 24", paths: [{ d: "M1.811 10.231c-.047 0-.058-.023-.035-.059l.246-.315c.023-.035.081-.058.128-.058h4.172c.046 0 .058.035.035.07l-.199.303c-.023.036-.082.07-.117.07zM.047 11.306c-.047 0-.059-.023-.035-.058l.245-.316c.023-.035.082-.058.129-.058h5.328c.047 0 .07.035.058.07l-.093.28c-.012.047-.058.07-.105.07zm2.828 1.075c-.047 0-.059-.035-.035-.07l.163-.292c.023-.035.07-.07.117-.07h2.337c.047 0 .07.035.07.082l-.023.28c0 .047-.047.082-.082.082zm12.129-2.36c-.736.187-1.239.327-1.963.514-.176.046-.187.058-.34-.117-.174-.199-.303-.327-.548-.444-.737-.362-1.45-.257-2.115.175-.795.514-1.204 1.274-1.192 2.22.011.935.654 1.706 1.577 1.835.795.105 1.46-.175 1.987-.77.105-.13.198-.27.315-.434H10.47c-.245 0-.304-.152-.222-.35.152-.362.432-.97.596-1.274a.315.315 0 01.292-.187h4.253c-.023.316-.023.631-.07.947a4.983 4.983 0 01-.958 2.29c-.841 1.11-1.94 1.8-3.33 1.986-1.145.152-2.209-.07-3.143-.77-.865-.655-1.356-1.52-1.484-2.595-.152-1.274.222-2.419.993-3.424.83-1.086 1.928-1.776 3.272-2.02 1.098-.2 2.15-.07 3.096.571.62.41 1.063.97 1.356 1.648.07.105.023.164-.117.2m3.868 6.461c-1.064-.024-2.034-.328-2.852-1.029a3.665 3.665 0 01-1.262-2.255c-.21-1.32.152-2.489.947-3.529.853-1.122 1.881-1.706 3.272-1.95 1.192-.21 2.314-.095 3.33.595.923.63 1.496 1.484 1.648 2.605.198 1.578-.257 2.863-1.344 3.962-.771.783-1.718 1.273-2.805 1.495-.315.06-.63.07-.934.106zm2.78-4.72c-.011-.153-.011-.27-.034-.387-.21-1.157-1.274-1.81-2.384-1.554-1.087.245-1.788.935-2.045 2.033-.21.912.234 1.835 1.075 2.21.643.28 1.285.244 1.905-.07.923-.48 1.425-1.228 1.484-2.233z", fill: "#00add8" }] },
  { name: "Celery", viewBox: "0 0 24 24", paths: [{ d: "M2.303 0A2.298 2.298 0 0 0 0 2.303v19.394A2.298 2.298 0 0 0 2.303 24h19.394A2.298 2.298 0 0 0 24 21.697V2.303A2.298 2.298 0 0 0 21.697 0zm8.177 3.072c4.098 0 7.028 1.438 7.68 1.764l-1.194 2.55c-2.442-1.057-4.993-1.41-5.672-1.41-1.574 0-2.17.922-2.17 1.763v8.494c0 .869.596 1.791 2.17 1.791.679 0 3.23-.38 5.672-1.41l1.194 2.496c-.435.271-3.637 1.818-7.68 1.818-1.112 0-4.64-.244-4.64-4.64V7.713c0-4.397 3.528-4.64 4.64-4.64z", fill: "#4caf50" }] },
  { name: "Neo4j", viewBox: "0 0 24 24", paths: [{ d: "M9.629 13.227c-.593 0-1.139.2-1.58.533l-2.892-1.976a2.61 2.61 0 0 0 .101-.711 2.633 2.633 0 0 0-2.629-2.629A2.632 2.632 0 0 0 0 11.073a2.632 2.632 0 0 0 2.629 2.629c.593 0 1.139-.2 1.579-.533L7.1 15.145c-.063.226-.1.465-.1.711 0 .247.037.484.1.711l-2.892 1.976a2.608 2.608 0 0 0-1.579-.533A2.632 2.632 0 0 0 0 20.639a2.632 2.632 0 0 0 2.629 2.629 2.632 2.632 0 0 0 2.629-2.629c0-.247-.037-.485-.101-.711l2.892-1.976c.441.333.987.533 1.58.533a2.633 2.633 0 0 0 2.629-2.629c0-1.45-1.18-2.629-2.629-2.629ZM16.112.732c-4.72 0-7.888 2.748-7.888 8.082v3.802a3.525 3.525 0 0 1 3.071.008v-3.81c0-3.459 1.907-5.237 4.817-5.237s4.817 1.778 4.817 5.237v8.309H24V8.814C24 3.448 20.832.732 16.112.732Z", fill: "#4581c3" }] },
  { name: "Elasticsearch", viewBox: "0 0 128 128", paths: [{ d: "M4 64c0 5.535.777 10.879 2.098 16H84c8.836 0 16-7.164 16-16s-7.164-16-16-16H6.098A63.738 63.738 0 0 0 4 64", fill: "#cfd3d8" }, { d: "M111.695 30.648A61.485 61.485 0 0 0 117.922 24C106.188 9.379 88.199 0 68 0 42.715 0 20.957 14.71 10.574 36H98.04a20.123 20.123 0 0 0 13.652-5.352", fill: "#fec514" }, { d: "M98.04 92H10.577C20.961 113.29 42.715 128 68 128c20.2 0 38.188-9.383 49.922-24a61.1 61.1 0 0 0-6.227-6.648A20.133 20.133 0 0 0 98.04 92", fill: "#00bfb3" }] },
  { name: "Redis", viewBox: "0 0 24 24", paths: [{ d: "M22.71 13.145c-1.66 2.092-3.452 4.483-7.038 4.483-3.203 0-4.397-2.825-4.48-5.12.701 1.484 2.073 2.685 4.214 2.63 4.117-.133 6.94-3.852 6.94-7.239 0-4.05-3.022-6.972-8.268-6.972-3.752 0-8.4 1.428-11.455 3.685C2.59 6.937 3.885 9.958 4.35 9.626c2.648-1.904 4.748-3.13 6.784-3.744C8.12 9.244.886 17.05 0 18.425c.1 1.261 1.66 4.648 2.424 4.648.232 0 .431-.133.664-.365a100.49 100.49 0 0 0 5.54-6.765c.222 3.104 1.748 6.898 6.014 6.898 3.819 0 7.604-2.756 9.33-8.965.2-.764-.73-1.361-1.261-.73zm-4.349-5.013c0 1.959-1.926 2.922-3.685 2.922-.941 0-1.664-.247-2.235-.568 1.051-1.592 2.092-3.225 3.21-4.973 1.972.334 2.71 1.43 2.71 2.619z", fill: "#ff4438" }] },
  { name: "Supabase", viewBox: "0 0 24 24", paths: [{ d: "M11.9 1.036c-.015-.986-1.26-1.41-1.874-.637L.764 12.05C-.33 13.427.65 15.455 2.409 15.455h9.579l.113 7.51c.014.985 1.259 1.408 1.873.636l9.262-11.653c1.093-1.375.113-3.403-1.645-3.403h-9.642z", fill: "#3fcf8e" }] },
  { name: "Docker", viewBox: "0 0 24 24", paths: [{ d: "M13.983 11.078h2.119a.186.186 0 00.186-.185V9.006a.186.186 0 00-.186-.186h-2.119a.185.185 0 00-.185.185v1.888c0 .102.083.185.185.185m-2.954-5.43h2.118a.186.186 0 00.186-.186V3.574a.186.186 0 00-.186-.185h-2.118a.185.185 0 00-.185.185v1.888c0 .102.082.185.185.185m0 2.716h2.118a.187.187 0 00.186-.186V6.29a.186.186 0 00-.186-.185h-2.118a.185.185 0 00-.185.185v1.887c0 .102.082.185.185.186m-2.93 0h2.12a.186.186 0 00.184-.186V6.29a.185.185 0 00-.185-.185H8.1a.185.185 0 00-.185.185v1.887c0 .102.083.185.185.186m-2.964 0h2.119a.186.186 0 00.185-.186V6.29a.185.185 0 00-.185-.185H5.136a.186.186 0 00-.186.185v1.887c0 .102.084.185.186.186m5.893 2.715h2.118a.186.186 0 00.186-.185V9.006a.186.186 0 00-.186-.186h-2.118a.185.185 0 00-.185.185v1.888c0 .102.082.185.185.185m-2.93 0h2.12a.185.185 0 00.184-.185V9.006a.185.185 0 00-.184-.186h-2.12a.185.185 0 00-.184.185v1.888c0 .102.083.185.185.185m-2.964 0h2.119a.185.185 0 00.185-.185V9.006a.185.185 0 00-.184-.186h-2.12a.186.186 0 00-.186.186v1.887c0 .102.084.185.186.185m-2.92 0h2.12a.185.185 0 00.184-.185V9.006a.185.185 0 00-.184-.186h-2.12a.185.185 0 00-.184.185v1.888c0 .102.082.185.185.185M23.763 9.89c-.065-.051-.672-.51-1.954-.51-.338.001-.676.03-1.01.087-.248-1.7-1.653-2.53-1.716-2.566l-.344-.199-.226.327c-.284.438-.49.922-.612 1.43-.23.97-.09 1.882.403 2.661-.595.332-1.55.413-1.744.42H.751a.751.751 0 00-.75.748 11.376 11.376 0 00.692 4.062c.545 1.428 1.355 2.48 2.41 3.124 1.18.723 3.1 1.137 5.275 1.137.983.003 1.963-.086 2.93-.266a12.248 12.248 0 003.823-1.389c.98-.567 1.86-1.288 2.61-2.136 1.252-1.418 1.998-2.997 2.553-4.4h.221c1.372 0 2.215-.549 2.68-1.009.309-.293.55-.65.707-1.046l.098-.288Z", fill: "#2496ed" }] },
  { name: "NVIDIA", viewBox: "0 0 24 24", paths: [{ d: "M8.948 8.798v-1.43a6.7 6.7 0 0 1 .424-.018c3.922-.124 6.493 3.374 6.493 3.374s-2.774 3.851-5.75 3.851c-.398 0-.787-.062-1.158-.185v-4.346c1.528.185 1.837.857 2.747 2.385l2.04-1.714s-1.492-1.952-4-1.952a6.016 6.016 0 0 0-.796.035m0-4.735v2.138l.424-.027c5.45-.185 9.01 4.47 9.01 4.47s-4.08 4.964-8.33 4.964c-.37 0-.733-.035-1.095-.097v1.325c.3.035.61.062.91.062 3.957 0 6.82-2.023 9.593-4.408.459.371 2.34 1.263 2.73 1.652-2.633 2.208-8.772 3.984-12.253 3.984-.335 0-.653-.018-.971-.053v1.864H24V4.063zm0 10.326v1.131c-3.657-.654-4.673-4.46-4.673-4.46s1.758-1.944 4.673-2.262v1.237H8.94c-1.528-.186-2.73 1.245-2.73 1.245s.68 2.412 2.739 3.11M2.456 10.9s2.164-3.197 6.5-3.533V6.201C4.153 6.59 0 10.653 0 10.653s2.35 6.802 8.948 7.42v-1.237c-4.84-.6-6.492-5.936-6.492-5.936z", fill: "#76b900" }] },
  { name: "OpenTelemetry", viewBox: "0 0 24 24", paths: [{ d: "M12.6974 13.1173c-1.0224 1.0224-1.0224 2.68 0 3.7024 1.0224 1.0224 2.68 1.0224 3.7024 0 1.0224-1.0223 1.0224-2.68 0-3.7024-1.0223-1.0223-2.68-1.0223-3.7024 0zm2.7677 2.7701c-.5063.5063-1.3267.5063-1.833 0s-.5063-1.3266 0-1.833c.5063-.5062 1.3267-.5062 1.833 0 .5063.504.5063 1.3267 0 1.833zM16.356.2355l-1.6041 1.6042c-.314.314-.314.83 0 1.144L21.015 9.247c.314.314.83.314 1.144 0l1.6042-1.6041c.314-.314.314-.83 0-1.144L17.4976.2354c-.314-.314-.8276-.314-1.1416 0zM5.1173 20.734c.2848-.2848.2848-.7497 0-1.0345l-.8155-.8155c-.2848-.2848-.7497-.2848-1.0345 0l-1.6845 1.6845-.0024.0024-.4625-.4625c-.2556-.2556-.6718-.2556-.925 0-.2556.2556-.2556.6718 0 .925l2.775 2.775c.2556.2556.6718.2556.925 0 .2532-.2556.2556-.6718 0-.925l-.4625-.4625.0024-.0024zm8.4856-15.893-3.5637 3.5637c-.3164.3164-.3164.8374 0 1.1538l2.2006 2.2005c1.5554-1.1197 3.7365-.981 5.1361.4187l1.7819-1.7818c.3164-.3165.3164-.8374 0-1.1538l-4.401-4.401c-.3165-.319-.8374-.319-1.1539 0zm-2.2881 7.8455-1.2999-1.2999c-.3043-.3043-.8033-.3043-1.1076 0l-4.5836 4.586c-.3042.3043-.3042.8033 0 1.1076l2.5973 2.5973c.3043.3043.8033.3043 1.1076 0l2.9478-2.9527c-.6231-1.2877-.5112-2.8431.3384-4.0383z", fill: "#f5a800" }] },
  { name: "Grafana", viewBox: "0 0 24 24", paths: [{ d: "M23.02 10.59a8.578 8.578 0 0 0-.862-3.034 8.911 8.911 0 0 0-1.789-2.445c.337-1.342-.413-2.505-.413-2.505-1.292-.08-2.113.4-2.416.62-.052-.02-.102-.044-.154-.064-.22-.089-.446-.172-.677-.247-.231-.073-.47-.14-.711-.197a9.867 9.867 0 0 0-.875-.161C14.557.753 12.94 0 12.94 0c-1.804 1.145-2.147 2.744-2.147 2.744l-.018.093c-.098.029-.2.057-.298.088-.138.042-.275.094-.413.143-.138.055-.275.107-.41.166a8.869 8.869 0 0 0-1.557.87l-.063-.029c-2.497-.955-4.716.195-4.716.195-.203 2.658.996 4.33 1.235 4.636a11.608 11.608 0 0 0-.607 2.635C1.636 12.677.953 15.014.953 15.014c1.926 2.214 4.171 2.351 4.171 2.351.003-.002.006-.002.006-.005.285.509.615.994.986 1.446.156.19.32.371.488.548-.704 2.009.099 3.68.099 3.68 2.144.08 3.553-.937 3.849-1.173a9.784 9.784 0 0 0 3.164.501h.08l.055-.003.107-.002.103-.005.003.002c1.01 1.44 2.788 1.646 2.788 1.646 1.264-1.332 1.337-2.653 1.337-2.94v-.058c0-.02-.003-.039-.003-.06.265-.187.52-.387.758-.6a7.875 7.875 0 0 0 1.415-1.7c1.43.083 2.437-.885 2.437-.885-.236-1.49-1.085-2.216-1.264-2.354l-.018-.013-.016-.013a.217.217 0 0 1-.031-.02c.008-.092.016-.18.02-.27.011-.162.016-.323.016-.48v-.253l-.005-.098-.008-.135a1.891 1.891 0 0 0-.01-.13c-.003-.042-.008-.083-.013-.125l-.016-.124-.018-.122a6.215 6.215 0 0 0-2.032-3.73 6.015 6.015 0 0 0-3.222-1.46 6.292 6.292 0 0 0-.85-.048l-.107.002h-.063l-.044.003-.104.008a4.777 4.777 0 0 0-3.335 1.695c-.332.4-.592.84-.768 1.297a4.594 4.594 0 0 0-.312 1.817l.003.091c.005.055.007.11.013.164a3.615 3.615 0 0 0 .698 1.82 3.53 3.53 0 0 0 1.827 1.282c.33.098.66.14.971.137.039 0 .078 0 .114-.002l.063-.003c.02 0 .041-.003.062-.003.034-.002.065-.007.099-.01.007 0 .018-.003.028-.003l.031-.005.06-.008a1.18 1.18 0 0 0 .112-.02c.036-.008.072-.013.109-.024a2.634 2.634 0 0 0 .914-.415c.028-.02.056-.041.085-.065a.248.248 0 0 0 .039-.35.244.244 0 0 0-.309-.06l-.078.042c-.09.044-.184.083-.283.116a2.476 2.476 0 0 1-.475.096c-.028.003-.054.006-.083.006l-.083.002c-.026 0-.054 0-.08-.002l-.102-.006h-.012l-.024.006c-.016-.003-.031-.003-.044-.006-.031-.002-.06-.007-.091-.01a2.59 2.59 0 0 1-.724-.213 2.557 2.557 0 0 1-.667-.438 2.52 2.52 0 0 1-.805-1.475 2.306 2.306 0 0 1-.029-.444l.006-.122v-.023l.002-.031c.003-.021.003-.04.005-.06a3.163 3.163 0 0 1 1.352-2.29 3.12 3.12 0 0 1 .937-.43 2.946 2.946 0 0 1 .776-.101h.06l.07.002.045.003h.026l.07.005a4.041 4.041 0 0 1 1.635.49 3.94 3.94 0 0 1 1.602 1.662 3.77 3.77 0 0 1 .397 1.414l.005.076.003.075c.002.026.002.05.002.075 0 .024.003.052 0 .07v.065l-.002.073-.008.174a6.195 6.195 0 0 1-.08.639 5.1 5.1 0 0 1-.267.927 5.31 5.31 0 0 1-.624 1.13 5.052 5.052 0 0 1-3.237 2.014 4.82 4.82 0 0 1-.649.066l-.039.003h-.287a6.607 6.607 0 0 1-1.716-.265 6.776 6.776 0 0 1-3.4-2.274 6.75 6.75 0 0 1-.746-1.15 6.616 6.616 0 0 1-.714-2.596l-.005-.083-.002-.02v-.056l-.003-.073v-.096l-.003-.104v-.07l.003-.163c.008-.22.026-.45.054-.678a8.707 8.707 0 0 1 .28-1.355c.128-.444.286-.872.473-1.277a7.04 7.04 0 0 1 1.456-2.1 5.925 5.925 0 0 1 .953-.763c.169-.111.343-.213.524-.306.089-.05.182-.091.273-.135.047-.02.093-.042.138-.062a7.177 7.177 0 0 1 .714-.267l.145-.045c.049-.015.098-.026.148-.041.098-.029.197-.052.296-.076.049-.013.1-.02.15-.033l.15-.032.151-.028.076-.013.075-.01.153-.024c.057-.01.114-.013.171-.023l.169-.021c.036-.003.073-.008.106-.01l.073-.008.036-.003.042-.002c.057-.003.114-.008.171-.01l.086-.006h.023l.037-.003.145-.007a7.999 7.999 0 0 1 1.708.125 7.917 7.917 0 0 1 2.048.68 8.253 8.253 0 0 1 1.672 1.09l.09.077.089.078c.06.052.114.107.171.159.057.052.112.106.166.16.052.055.107.107.159.164a8.671 8.671 0 0 1 1.41 1.978c.012.026.028.052.04.078l.04.078.075.156c.023.051.05.1.07.153l.065.15a8.848 8.848 0 0 1 .45 1.34.19.19 0 0 0 .201.142.186.186 0 0 0 .172-.184c.01-.246.002-.532-.024-.856z", fill: "#f46800" }] },
  { name: "GitHub", viewBox: "0 0 24 24", paths: [{ d: "M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12", fill: "#ffffff" }] },
];

function TechLogo({ tech }: { tech: Tech }) {
  return (
    <svg className={LOGO} viewBox={tech.viewBox} aria-hidden="true">
      {tech.paths.map((p, i) => (
        <path key={i} d={p.d} fill={p.fill} />
      ))}
    </svg>
  );
}

function GraphHacksIcon() {
  return (
    <svg className="size-7 shrink-0 text-[#38bdf8]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="6" cy="6" r="3" fill="#38bdf8" fillOpacity="0.25" />
      <circle cx="18" cy="6" r="3" fill="#38bdf8" fillOpacity="0.25" />
      <circle cx="18" cy="18" r="3" fill="#38bdf8" fillOpacity="0.25" />
      <circle cx="6" cy="18" r="3" fill="#38bdf8" fillOpacity="0.25" />
      <circle cx="12" cy="12" r="2.5" fill="#38bdf8" />
      <line x1="8.5" y1="7.5" x2="10" y2="10.5" />
      <line x1="15.5" y1="7.5" x2="14" y2="10.5" />
      <line x1="14" y1="13.5" x2="15.5" y2="16.5" />
      <line x1="10" y1="13.5" x2="8.5" y2="16.5" />
      <line x1="9" y1="6" x2="15" y2="6" />
      <line x1="6" y1="9" x2="6" y2="15" />
    </svg>
  );
}

function WeMakeDevsIcon() {
  return (
    <svg className="size-7 shrink-0 text-[#34d399]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="16 18 22 12 16 6" />
      <polyline points="8 6 2 12 8 18" />
      <path d="M12 4v16" strokeDasharray="2 2" />
      <circle cx="12" cy="12" r="2" fill="#34d399" />
    </svg>
  );
}

function FalkorDBIcon() {
  return (
    <svg className="size-7 shrink-0 text-[#ff6b4a]" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 2C6.48 2 2 4.02 2 6.5v11C2 19.98 6.48 22 12 22s10-2.02 10-4.5v-11C22 4.02 17.52 2 12 2zm0 2.2c4.85 0 7.8 1.63 7.8 2.3 0 .67-2.95 2.3-7.8 2.3S4.2 7.17 4.2 6.5c0-.67 2.95-2.3 7.8-2.3zm8 6.8c-.61.76-2.6 1.84-5.8 2.16v2.06c4.68-.43 7.8-1.92 7.8-2.72v-1.5zm-16 0v1.5c0 .8 3.12 2.29 7.8 2.72v-2.06C8.6 12.84 6.61 11.76 6 11zm0 5.5v1.5c0 .67 2.95 2.3 7.8 2.3s7.8-1.63 7.8-2.3v-1.5c-.61.76-2.6 1.84-5.8 2.16v2.06c4.68-.43 7.8-1.92 7.8-2.72z" />
      <path d="M12 11.5l2.5 2.5-2.5 2.5-2.5-2.5 2.5-2.5z" fill="#ffb74d" />
    </svg>
  );
}

/** Adds .lp-anim, then reveals each [data-reveal] block as it scrolls in. */
function useReveal() {
  useEffect(() => {
    const root = document.querySelector<HTMLElement>("main.landing");
    if (!root) return;
    // Gated on JS so a failed hydrate never leaves the page invisible.
    root.classList.add("lp-anim");

    const targets = root.querySelectorAll("[data-reveal]");
    const io = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          entry.target.classList.add("is-in");
          io.unobserve(entry.target);
        }
      },
      { rootMargin: "0px 0px -12% 0px", threshold: 0.05 },
    );
    targets.forEach((t) => io.observe(t));
    return () => io.disconnect();
  }, []);
}

/**
 * Surveyor marks pinned to the corners of a framed block.
 *
 * Returns a fragment, deliberately, because a wrapper element would be a static child
 * and so claim a cell in the grid containers these sit inside. The ticks
 * themselves are position:absolute (.lp-tick), which keeps them out of flow.
 */
function Ticks({ solid = false, bottom = false }: { solid?: boolean; bottom?: boolean }) {
  const cls = `${solid ? "lp-tick lp-tick--solid" : "lp-tick"} pointer-events-none`;
  return (
    <>
      <span aria-hidden="true" className={`${cls} left-0 top-0 -translate-x-1/2 -translate-y-1/2`} />
      <span aria-hidden="true" className={`${cls} right-0 top-0 translate-x-1/2 -translate-y-1/2`} />
      {bottom ? (
        <>
          <span aria-hidden="true" className={`${cls} bottom-0 left-0 -translate-x-1/2 translate-y-1/2`} />
          <span aria-hidden="true" className={`${cls} bottom-0 right-0 translate-x-1/2 translate-y-1/2`} />
        </>
      ) : null}
    </>
  );
}

/**
 * Demo player. A facade, not a bare iframe: the poster is the page's own media
 * panel, so YouTube is contacted only once someone presses play. That keeps the
 * third-party script (and its cookies) off first load, which is the difference
 * between a fast landing page and a slow one. `youtube-nocookie` on top.
 */
function DemoPlayer({ videoId }: { videoId: string }) {
  const [playing, setPlaying] = useState(false);
  return (
    <div className="lp-card lp-media lp-dither relative mt-10 border border-transparent p-3 sm:p-6">
      <div className="relative aspect-video overflow-hidden border border-white/20">
        {playing ? (
          <iframe
            className="absolute inset-0 size-full"
            src={`https://www.youtube-nocookie.com/embed/${videoId}?autoplay=1&rel=0&modestbranding=1`}
            title="AIDTRACE demo"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
          />
        ) : (
          <button
            type="button"
            onClick={() => setPlaying(true)}
            aria-label="Play the AIDTRACE demo"
            className="group absolute inset-0 grid place-items-center"
          >
            <span className="grid size-16 place-items-center bg-(--lp-accent-strong) text-white transition-transform duration-150 ease-out group-hover:scale-105 group-active:scale-95 sm:size-20">
              <svg width="22" height="24" viewBox="0 0 22 24" fill="currentColor" aria-hidden="true">
                <path d="M21 12 0 24V0z" />
              </svg>
            </span>
            <span className="absolute bottom-4 left-4 text-[12px] uppercase tracking-[0.08em] text-white/80 sm:bottom-6 sm:left-6">
              Play the demo
            </span>
          </button>
        )}
      </div>
    </div>
  );
}

/**
 * The reference's primary button does not simply darken: it dissolves to black
 * cell by cell. An 18x4 grid of squares fades in with a stepped 90ms
 * transition and a staggered delay, giving a pixel-wipe.
 *
 * Delays are derived from the index, never Math.random(): a random value would
 * differ between server and client render and break hydration.
 */
const PIXEL_COLS = 18;
const PIXEL_ROWS = 4;

function pixelDelay(index: number) {
  const col = index % PIXEL_COLS;
  const jitter = (index * 1103515245 + 12345) % 45;
  return col * 5 + jitter;
}

function PixelFill() {
  return (
    <span
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 z-0 grid"
      style={{ gridTemplateColumns: `repeat(${PIXEL_COLS}, 1fr)`, gridTemplateRows: `repeat(${PIXEL_ROWS}, 1fr)` }}
    >
      {Array.from({ length: PIXEL_COLS * PIXEL_ROWS }).map((_, i) => (
        <span
          key={i}
          className="bg-(--lp-ink) opacity-0 [transition:opacity_90ms_steps(1)] group-hover:opacity-100"
          style={{ transitionDelay: `${pixelDelay(i)}ms` }}
        />
      ))}
    </span>
  );
}

function Eyebrow({ children }: { children: string }) {
  return (
    <span className="inline-flex items-center rounded-[1px] bg-(--lp-accent-strong) px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-white">
      {children}
    </span>
  );
}

/** Heading highlight block: charcoal by default, solid accent when `fill`. */
function Box({ children, fill = false }: { children: React.ReactNode; fill?: boolean }) {
  return (
    <span
      className={`inline-block px-3 py-[5px] font-semibold tracking-normal text-white ${fill ? "bg-(--lp-accent-strong)" : "bg-(--lp-charcoal)"}`}
    >
      {children}
    </span>
  );
}

/**
 * Hero artwork. Designed rather than a screenshot, mirroring how the reference
 * leads with a rendered scene and saves product captures for the use-case
 * panels. It shows the actual claim: every source system the plant owns, wired
 * into one governed answer that carries its evidence on its face.
 *
 * The geometry is computed, never eyeballed. One ellipse defines everything —
 * where a chip sits, where its wire starts, where the rings are drawn — so a
 * chip can never drift off the orbit or a wire end up connected to nothing.
 * `ORBIT` is in the SVG's user units; the chips read the same points back as
 * percentages, and `preserveAspectRatio="none"` maps the viewBox onto the field
 * exactly, so the two coordinate systems stay locked together at any width.
 *
 * Layout is one tree, two shapes. Below `lg` the chips are a wrapped row above
 * the card; from `lg` up the wrapper becomes `display: contents` and each chip
 * takes its place on the ring from `--orbit-x` / `--orbit-y`. Same DOM, so the
 * card's text is never duplicated for a screen reader. The break is `lg` and
 * not `sm` because the orbit needs a chip's width clear either side of the
 * card: below roughly 1000px of panel the two collide.
 */
const ORBIT = {
  cx: 500,
  cy: 265,
  /* The chip ring. rx is capped near 41% of the field: any wider and the
     outermost chip's own width pushes it past the panel edge. */
  rx: 400,
  /* Tall enough that the 120°/60° pair clears the top of the answer card. The
     field is short, so this is the measurement the whole composition turns on. */
  ry: 256,
  /* Where the wires terminate: the same ellipse scaled down, which is what makes
     every spoke exactly radial. A third of the way in puts it well inside the
     answer card at every breakpoint, so all ten vanish beneath the card rather
     than stopping in mid-air against its edge. */
  hub: 0.33,
} as const;

/** A point on an ellipse concentric with the orbit. Degrees, 0° = due right. */
function orbitPoint(deg: number, rx: number, ry: number): [number, number] {
  const rad = (deg * Math.PI) / 180;
  return [ORBIT.cx + rx * Math.cos(rad), ORBIT.cy - ry * Math.sin(rad)];
}

/**
 * The spoke from a chip in to the hub. Start and end sit on concentric copies of
 * the same ellipse, so the line is exactly radial: ten spokes on one centre read
 * as a system converging, where ten curves crossing four rings read as clutter.
 */
function orbitWire(deg: number): string {
  const [x0, y0] = orbitPoint(deg, ORBIT.rx, ORBIT.ry);
  const [x1, y1] = orbitPoint(deg, ORBIT.rx * ORBIT.hub, ORBIT.ry * ORBIT.hub);
  return `M ${x0.toFixed(1)} ${y0.toFixed(1)} L ${x1.toFixed(1)} ${y1.toFixed(1)}`;
}

/**
 * Five sources a side, mirrored across the vertical, which is what makes the ring
 * read as deliberate. They span 60° either side of horizontal rather than the
 * full 90°: the field is twice as wide as it is tall, so equal angles bunch the
 * top and bottom pairs against the card while leaving the flanks empty. `cited` marks the three the
 * answer card actually stands on: those get the accent wire and the pulse, the
 * other seven stay connected but quiet. Array order is the phone reading order,
 * where the ring collapses to a wrapped row.
 */
const heroSources: { tag: string; label: string; deg: number; cited?: boolean }[] = [
  { tag: "DOC", label: "Documents", deg: 120 },
  { tag: "SRC", label: "Source versions", deg: 150, cited: true },
  { tag: "SUP", label: "Suppliers", deg: 180 },
  { tag: "INC", label: "Incidents", deg: 210 },
  { tag: "MEM", label: "Agent memory", deg: 240, cited: true },
  { tag: "CLM", label: "Evidence claims", deg: 60, cited: true },
  { tag: "SEC", label: "Security findings", deg: 30 },
  { tag: "TXN", label: "Transactions", deg: 0 },
  { tag: "DEC", label: "Decisions", deg: -30 },
  { tag: "REV", label: "Human review", deg: -60 },
];

/** Synthetic Evidence Drift records: two source versions and an approval requiring review. */
const heroEvidence: { doc: string; tier: string; date: string; unverified?: boolean }[] = [
  { doc: "Audit procedure · version 1", tier: "Superseded", date: "180 days" },
  { doc: "Audit procedure · version 2", tier: "Current", date: "90 days" },
  { doc: "Prior approval · revision 1", tier: "Review", date: "Stale", unverified: true },
];

/* Ring radii as multiples of the orbit. 1 is the chip ring itself; the wider one
   frames it, and the inner one shows only as slivers either side of the card,
   which is what gives the field depth rather than a single flat hoop. */
/* Graduations around the chip ring, every 7.5°. Chip angles are all multiples of
   30, so a tick lands under every chip and the ring reads as one dial rather
   than a hoop with labels stuck to it. Radial, so they stay true on an ellipse
   this eccentric. */
const heroTicks = Array.from({ length: 48 }, (_, i) => i * 7.5);

const heroRings: { scale: number; opacity: number }[] = [
  { scale: 1.18, opacity: 0.1 },
  { scale: 1, opacity: 0.3 },
  { scale: 0.62, opacity: 0.14 },
];

function HeroVisual() {
  return (
    <div>
      {/* Reads as an instrument panel legend: what goes in, what comes out. */}
      <div className="flex items-center justify-between gap-3 text-[9px] font-semibold uppercase tracking-[0.1em] text-white/60 lg:text-[10px] lg:tracking-[0.14em]">
        <span className="whitespace-nowrap">AIDTRACE · synthetic</span>
        <span className="flex items-center gap-2 whitespace-nowrap">
          <span aria-hidden="true" className="size-1.5 bg-(--lp-accent)" />
          Decision trace
        </span>
      </div>

      <div className="mt-5 flex flex-col gap-4 lg:relative lg:mt-6 lg:block lg:aspect-[16/9] xl:aspect-[16/7.8]">
        <svg
          viewBox="0 0 1000 530"
          className="pointer-events-none absolute inset-0 hidden size-full lg:block"
          aria-hidden="true"
          preserveAspectRatio="none"
        >
          {/* Every pale stroke is drawn twice: a wider dark pass underneath, then
              the light one over it. The panel runs from near-black in one corner
              to bright orange in the other, and a single white hairline simply
              disappears into the bright half. */}
          {heroRings.map((ring) => (
            <g key={ring.scale}>
              <ellipse
                cx={ORBIT.cx}
                cy={ORBIT.cy}
                rx={ORBIT.rx * ring.scale}
                ry={ORBIT.ry * ring.scale}
                fill="none"
                stroke="#000000"
                strokeWidth="2.5"
                opacity={ring.opacity * 0.6}
              />
              <ellipse
                cx={ORBIT.cx}
                cy={ORBIT.cy}
                rx={ORBIT.rx * ring.scale}
                ry={ORBIT.ry * ring.scale}
                fill="none"
                stroke="#ffffff"
                opacity={ring.opacity}
              />
            </g>
          ))}

          {heroTicks.map((deg) => {
            const [x1, y1] = orbitPoint(deg, ORBIT.rx, ORBIT.ry);
            const [x2, y2] = orbitPoint(deg, ORBIT.rx * 1.035, ORBIT.ry * 1.035);
            return (
              <g key={deg}>
                <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="#000000" strokeWidth="2.5" opacity="0.12" />
                <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="#ffffff" opacity="0.22" />
              </g>
            );
          })}

          {heroSources.map((source) => (
            <g key={source.tag}>
              {!source.cited && (
                <path d={orbitWire(source.deg)} fill="none" stroke="#000000" strokeWidth="2.5" opacity="0.18" />
              )}
              <path
                d={orbitWire(source.deg)}
                fill="none"
                strokeWidth={source.cited ? 1.5 : 1}
                stroke={source.cited ? "var(--lp-accent)" : "#ffffff"}
                opacity={source.cited ? 0.75 : 0.34}
              />
            </g>
          ))}

          {/* A pulse on every wire, so the whole ring reads as live. The cited
              three run brighter and faster; the rest are ambient. */}
          {heroSources.map((source, i) => (
            <circle
              key={source.tag}
              className={`lp-orbit-pulse${source.cited ? " lp-orbit-pulse--cited" : ""}`}
              r={source.cited ? 3.5 : 2.2}
              fill={source.cited ? "var(--lp-accent)" : "#ffffff"}
              style={{ offsetPath: `path("${orbitWire(source.deg)}")`, animationDelay: `${(i % 5) * 0.9 + (i > 4 ? 0.45 : 0)}s` }}
            />
          ))}
        </svg>

        {/* `lg:contents` hands each chip straight to the orbit field, so one
            element can be a flow chip on a phone and a ring node on a laptop. */}
        <div className="flex flex-wrap gap-1.5 lg:contents">
          {heroSources.map((source) => {
            const [x, y] = orbitPoint(source.deg, ORBIT.rx, ORBIT.ry);
            return (
              <span
                key={source.tag}
                className={`lp-orbit-node inline-flex items-center gap-2 border bg-(--lp-dark)/78 px-2.5 py-1.5 text-[11px] text-white shadow-lg backdrop-blur-md xl:px-3 xl:py-2 xl:text-[12px] ${source.cited ? "border-(--lp-accent)/70" : "border-white/12"
                  }`}
                style={
                  {
                    "--orbit-x": `${((x / 1000) * 100).toFixed(2)}%`,
                    "--orbit-y": `${((y / 530) * 100).toFixed(2)}%`,
                  } as React.CSSProperties
                }
              >
                <span
                  className={`shrink-0 text-[9px] font-semibold tracking-[0.08em] ${source.cited ? "text-(--lp-accent)" : "text-white/50"
                    }`}
                >
                  {source.tag}
                </span>
                <span className="whitespace-nowrap">{source.label}</span>
              </span>
            );
          })}
        </div>

        {/* The governed answer, and the evidence it stands on. */}
        <div className="lg:absolute lg:left-1/2 lg:top-1/2 lg:w-[44%] lg:-translate-x-1/2 lg:-translate-y-1/2 xl:w-[min(42%,450px)]">
          <div className="lp-mock border border-white/15 bg-(--lp-surface) p-4 sm:p-5">
            <div className="flex items-center justify-between border-b border-(--lp-line) pb-3">
              <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-(--lp-accent-text)">
                Evidence change detected
              </span>
              <span className="text-[11px] tabular-nums text-(--lp-muted)">Review required</span>
            </div>

            <p className="lp-display mt-3 text-[17px] leading-tight text-pretty text-(--lp-ink) sm:text-[19px]">
              A supplier audit interval changed from 180 to 90 days. The earlier decision and its approval need another review.
            </p>

            <div className="mt-4 border-t border-(--lp-line) pt-3">
              <p className="text-[9px] font-semibold uppercase tracking-[0.1em] text-(--lp-muted)">Evidence</p>
              <ul className="mt-2 space-y-1.5">
                {heroEvidence.map((item) => (
                  <li key={item.doc} className="flex items-baseline gap-2 text-[11px]">
                    <span
                      aria-hidden="true"
                      className={`size-1.5 shrink-0 ${item.unverified ? "border border-(--lp-accent)" : "bg-(--lp-accent)"}`}
                    />
                    <span className="min-w-0 flex-1 truncate text-(--lp-ink)">{item.doc}</span>
                    <span
                      className={`shrink-0 ${item.unverified ? "font-semibold text-(--lp-accent-text)" : "text-(--lp-muted)"}`}
                    >
                      {item.tier}
                    </span>
                    <span className="hidden shrink-0 tabular-nums text-(--lp-muted) min-[420px]:inline">{item.date}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="mt-4 flex flex-wrap gap-1.5 text-[11px]">
              <span className="bg-(--lp-accent-strong) px-2 py-1 font-medium text-white">3 linked records</span>
              <span className="border border-(--lp-line) px-2 py-1 text-(--lp-muted)">Source version changed</span>
              <span className="border border-(--lp-line) px-2 py-1 text-(--lp-muted)">Approval stale</span>
            </div>

            <div className="mt-4">
              <div className="flex justify-between text-[11px] text-(--lp-muted)">
                <span>Evidence path</span>
                <span className="font-semibold tabular-nums text-(--lp-ink)">Review before action</span>
              </div>
              <div className="mt-1.5 h-1.5 bg-(--lp-band)">
                <span className="block h-full w-[91%] bg-(--lp-accent)" />
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="mt-5 flex flex-wrap items-center justify-between gap-x-6 gap-y-2 border-t border-white/15 pt-4 text-[11px] text-white/70 lg:mt-6">
        <span>No claim without its source</span>
        <span>Changed evidence triggers human review before action</span>
      </div>
    </div>
  );
}

/**
 * A real screenshot of the running app, captured by
 * tools/capture_landing_shots.sh. Re-run that script after UI changes so the
 * marketing page never drifts from the product.
 */
function Shot({ src, alt }: { src: string; alt: string }) {
  return (
    <Image
      src={`/shots/${src}.png?rev=aidtrace-workspace-v2`}
      alt={alt}
      width={2880}
      height={1620}
      unoptimized
      sizes="(max-width: 1024px) 100vw, 900px"
      className="lp-mock h-auto w-full"
    />
  );
}

export default function Home() {
  const [capability, setCapability] = useState(0);
  const [systemTab, setSystemTab] = useState(0);
  const [audience, setAudience] = useState(0);
  const [faqGroup, setFaqGroup] = useState(0);
  useReveal();

  const active = capabilities[capability];
  const activeSystem = systemDesign[systemTab];

  return (
    <main className={`landing ${instrumentSans.variable} ${dmSans.variable} min-h-dvh`}>
      {/* ── Nav: segmented cells, not a plain row ──────────────────────── */}
      {/* Solid, no backdrop blur: the reference header is opaque #f8f8f8. */}
      <header className="sticky top-0 z-30 border-b border-(--lp-line) bg-(--lp-band)">
        <nav className="lp-frame flex h-[49px] items-stretch">
          <Link href="/" aria-label="AIDTRACE home" className="flex items-center gap-2.5 border-r border-(--lp-line) px-4 sm:px-5">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo.png" alt="" width={24} height={24} className="object-cover" />
            <span className="lp-display text-[18px] text-(--lp-ink)">AIDTRACE</span>
          </Link>

          <div className="hidden items-stretch lg:flex">
            {navLinks.map(([label, href]) => (
              <a
                key={href}
                href={href}
                className="flex items-center whitespace-nowrap border-r border-(--lp-line) px-4 text-[13px] text-(--lp-muted) transition-colors duration-150 hover:bg-(--lp-ink) hover:text-white xl:px-5"
              >
                {label}
              </a>
            ))}
          </div>

          <div className="ml-auto flex items-stretch">
            <Link
              href="/login"
              className="group relative flex items-center gap-2 overflow-hidden border-l border-(--lp-line) bg-(--lp-accent-strong) px-5 text-[14px] font-medium text-white sm:px-7 transition-transform duration-150 ease-out active:scale-[0.98]"
            >
              <PixelFill />
              <span className="relative z-10">Open workspace</span>
              <span aria-hidden="true" className="relative z-10">›</span>
            </Link>
          </div>
        </nav>
      </header>

      {/* ── Hero ────────────────────────────────────────────────────────── */}
      <section className="lp-frame relative px-4 pb-14 pt-16 sm:px-6 sm:pt-24">
        <div data-reveal className="grid gap-10 lg:grid-cols-[1.1fr_0.9fr] lg:items-start">
          {/* The {" "} before each <br /> is load-bearing: <br> contributes no
              whitespace, so without it the accessible name runs the lines
              together ("Plant knowledge,at the moment…"). Same pattern below. */}
          <div>
            <Eyebrow>Graph-native AI intelligence</Eyebrow>
            <h1 className="mt-6 text-[40px] text-(--lp-ink) sm:text-[54px] lg:text-[64px]">
              Connected{" "}<br />
              intelligence.{" "}<br />
              <span className="text-(--lp-accent)">Verifiable{" "}<br />
                decisions.</span>
            </h1>
          </div>

          <div className="lg:pt-4">
            <p className="max-w-md text-[18px] leading-7 text-(--lp-muted)">
              <strong className="font-semibold text-(--lp-ink)">One graph. Every relationship. A clearer decision.</strong>{" "}
              AIDTRACE connects evidence, persistent agent memory and decisions across specialized
              workflows, powered by FalkorDB.
            </p>
            <div className="mt-7 flex flex-wrap gap-3">
              <a
                href={demoVideoId ? "#demo" : DEMO_FALLBACK_URL}
                target={demoVideoId ? undefined : "_blank"}
                rel={demoVideoId ? undefined : "noreferrer noopener"}
                className="group relative inline-flex min-h-11 min-w-[207px] items-center justify-center gap-2 overflow-hidden bg-(--lp-accent-strong) px-3 py-[15px] text-[14px] font-medium text-white transition-transform duration-150 ease-out active:scale-[0.98]"
              >
                <PixelFill />
                <span className="relative z-10">{demoVideoId ? "Watch AIDTRACE demo" : "Open AIDTRACE workspace"}</span>
                <span aria-hidden="true" className="relative z-10">›</span>
              </a>
              <a
                href="#how"
                className="inline-flex min-h-11 min-w-[207px] items-center justify-center gap-2 bg-(--lp-ink) px-3 py-[15px] text-[14px] font-medium text-white transition-[background-color,transform] duration-150 ease-out hover:bg-(--lp-accent-strong) active:scale-[0.98]"
              >
                Explore how it works <span aria-hidden="true" className="text-(--lp-accent)">▶</span>
              </a>
            </div>
          </div>
        </div>

        <div data-reveal className="lp-card lp-media lp-dither relative mt-12 border border-transparent p-3 sm:p-6">
          <div className="relative border border-white/20 p-4 sm:p-8">
            <HeroVisual />
          </div>
        </div>
      </section>

      {/* A prominent entry point for field capture, placed directly below the hero. */}
      <section id="voice" aria-labelledby="voice-feature-title" className="lp-band border-y border-(--lp-line)">
        <div className="lp-frame relative grid gap-10 px-4 py-14 sm:px-6 sm:py-20 lg:grid-cols-[1fr_0.85fr] lg:items-center">
          <div data-reveal>
            <Eyebrow>Multilingual field capture</Eyebrow>
            <h2 id="voice-feature-title" className="mt-5 max-w-2xl text-[32px] text-(--lp-ink) sm:text-[46px]">
              Speak the observation.{" "}<br />
              <Box>Keep the evidence intact.</Box>
            </h2>
            <p className="mt-5 max-w-xl text-[16px] leading-6 text-(--lp-muted)">
              Capture a site note in 18 selectable languages or let transcription detect the language.
              Check your mic signal, pause when you need to, and send the recording into engineering review.
              Work-order and asset tags guide equipment-name spelling.
            </p>
            <div className="mt-7 flex flex-wrap gap-3">
              <Link
                href="/login?next=field-voice"
                className="group relative inline-flex min-h-11 items-center justify-center gap-2 overflow-hidden bg-(--lp-accent-strong) px-5 py-3 text-[14px] font-medium text-white transition-transform duration-150 ease-out active:scale-[0.98]"
              >
                <PixelFill />
                <span className="relative z-10">Open field voice capture</span>
                <span aria-hidden="true" className="relative z-10">›</span>
              </Link>
              <a href="#field" className="inline-flex min-h-11 items-center justify-center border border-(--lp-line) px-5 py-3 text-[14px] font-medium text-(--lp-ink) transition-colors hover:border-(--lp-accent)">
                Explore the workflow
              </a>
            </div>
          </div>
          <div data-reveal className="lp-card lp-media lp-dither relative border border-transparent p-5 sm:p-7">
            <div className="border border-white/20 bg-black/20 p-5 sm:p-7">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-white/70">Voice note · field workflow</p>
                  <p className="lp-display mt-2 text-[22px] text-white sm:text-[26px]">Hindi · Auto-detect available</p>
                </div>
                <span className="shrink-0 border border-white/30 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-white/85">Review required</span>
              </div>
              <div className="mt-8 flex h-16 items-center justify-center gap-1.5" role="img" aria-label="Illustration of microphone signal levels">
                {[18, 28, 42, 26, 58, 38, 72, 46, 32, 64, 42, 24, 52, 34, 18, 40, 60, 30, 20].map((height, index) => (
                  <span key={index} className="w-1.5 rounded-full bg-(--lp-accent)" style={{ height: height + "px" }} />
                ))}
              </div>
              <div className="mt-7 grid grid-cols-3 border-t border-white/20 pt-4 text-center">
                {[["01", "Choose language"], ["02", "Capture + sound check"], ["03", "Engineer review"]].map(([number, label]) => (
                  <div key={number} className="px-1">
                    <span className="block text-[10px] font-semibold text-(--lp-accent)">{number}</span>
                    <span className="mt-1 block text-[10px] leading-4 text-white/80 sm:text-[12px]">{label}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Graph Hacks banner: its link goes to the Track 01 section below. */}
      <section aria-label="Built for Graph Hacks" className="lp-frame relative px-4 pb-14 sm:px-6">
        <div data-reveal className="lp-card border border-(--lp-line) bg-(--lp-surface)">
          <div className="border-b border-(--lp-line) bg-(--lp-accent-strong) px-5 py-4 sm:px-7">
            <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-white">
              Built for Graph Hacks · Track 01
            </p>
            <p className="lp-display mt-2 text-[19px] leading-tight text-white sm:text-[22px]">
              Agents that act on connected data.
            </p>
          </div>

          <div className="flex flex-col gap-6 px-5 py-6 sm:flex-row sm:items-center sm:justify-between sm:gap-10 sm:px-7">
            <p className="max-w-2xl text-[15px] leading-6 text-(--lp-muted)">
              The Track 01 extension traces multi-hop relationships and preserves each investigation step before
              a controlled action is proposed. Affected entities and dependencies stay visible in the shared workspace.
            </p>
            <a
              href="#field"
              className="inline-flex min-h-11 shrink-0 items-center justify-center gap-2 bg-(--lp-ink) px-5 py-[11px] text-[14px] font-medium text-white transition-[background-color,transform] duration-150 ease-out hover:bg-(--lp-accent-strong) active:scale-[0.98]"
            >
              See the Track 01 extension <span aria-hidden="true" className="text-(--lp-accent)">▶</span>
            </a>
          </div>
        </div>
      </section>

      {/* ── Demo: the product running, straight after the claim it makes ──
          Renders only when DEMO_YOUTUBE_URL is set. Placed here on purpose: the
          hero's primary CTA is "Watch demo", and a visitor who presses it should
          arrive in one scroll, before the argument starts. */}
      {demoVideoId && (
        <section id="demo" className="lp-band">
          <div className="lp-frame relative px-4 py-16 sm:px-6 sm:py-24">
            <Ticks />
            <Eyebrow>Demo</Eyebrow>
            <h2 className="mt-5 max-w-3xl text-[36px] sm:text-[48px]">
              The connected workflow, in action.
            </h2>
            <p className="mt-5 max-w-xl text-[16px] leading-6 text-(--lp-muted)">
              See the connected AIDTRACE workflow with source-backed answers and governed
              decisions. The FalkorDB Evidence Drift case is labeled synthetic in the workspace.
            </p>
            <DemoPlayer videoId={demoVideoId} />
          </div>
        </section>
      )}

      {/* ── The problem: stated before any product claim ────────────────── */}
      <section id="problem" className="bg-(--lp-dark) text-white">
        <div className="lp-frame lp-frame--dark px-4 py-16 sm:px-6 sm:py-24">
          <div data-reveal>
            <Eyebrow>The problem</Eyebrow>
            <h2 className="mt-6 max-w-3xl text-[30px] sm:text-[44px]">
              The information exists.{" "}<br />
              <Box fill>The connections are missing.</Box>
            </h2>
            <p className="mt-6 max-w-2xl text-[16px] leading-6 text-(--lp-dark-muted)">
              A supplier disruption affects a facility. A security finding exposes a dependency.
              A revised document changes an earlier recommendation. When these records stay apart,
              people cannot see which decisions need another look.
            </p>
          </div>

          <div data-reveal className="mt-14 grid gap-px bg-(--lp-dark-line) sm:grid-cols-2 lg:grid-cols-4">
            {problemStats.map((stat) => (
              <div key={stat.figure} data-stagger className="lp-cell lp-cell--dark bg-(--lp-dark) flex h-full flex-col p-5">
                <p className="lp-display text-[40px] leading-none text-(--lp-accent) sm:text-[48px]">{stat.figure}</p>
                <p className="mt-3 text-[14px] font-semibold text-white">{stat.label}</p>
                <p className="mt-3 text-[13px] leading-5 text-(--lp-dark-muted)">{stat.body}</p>
                <p className="mt-auto border-t border-(--lp-dark-line) pt-3 text-[11px] uppercase tracking-[0.08em] text-(--lp-dark-muted)">
                  {stat.source}
                </p>
              </div>
            ))}
          </div>

          <p data-reveal className="mt-12 max-w-3xl text-[16px] leading-6 text-white">
            AIDTRACE connects evidence and traces the consequences when information changes.{" "}
            <span className="text-(--lp-accent)">The question is what the change means for decisions already made.</span>
          </p>
        </div>
      </section>

      {/* ── How it works: one scenario, followed end to end ──────────────── */}
      <section id="how" className="border-t border-(--lp-line)">
        <div className="lp-frame relative px-4 py-16 sm:px-6 sm:py-24">
          <Ticks />
          <div data-reveal>
            <Eyebrow>How it works</Eyebrow>
            <h2 className="mt-6 max-w-3xl text-[30px] text-(--lp-ink) sm:text-[44px]">
              One intelligence workflow.{" "}<br />
              <Box>Multiple applications.</Box>
            </h2>
            <p className="mt-6 max-w-xl text-[16px] leading-6 text-(--lp-muted)">
              Connect information, investigate its relationships, verify the evidence and bring
              recommendations to a person. Each extension keeps its specialized algorithms.
            </p>
          </div>

          {/* A rail, not a mesh of cells. This content is ordered, and five equal
              boxes say "five categories" where a numbered rail says "five steps,
              in this direction". The last node is filled because the copy below
              turns on it. */}
          <ol data-reveal className="mt-12 grid gap-x-8 gap-y-10 sm:grid-cols-2 lg:grid-cols-5">
            {scenario.map((item, index) => {
              const last = index === scenario.length - 1;
              return (
                <li key={item.tag} data-stagger className="relative">
                  {!last && (
                    <span
                      aria-hidden="true"
                      className="absolute left-9 -right-4 top-4 hidden h-px bg-(--lp-line) lg:block"
                    />
                  )}
                  <div className="relative z-10 inline-flex items-center gap-3 bg-(--lp-bg) pr-3">
                    <span
                      className={`lp-display grid size-8 shrink-0 place-items-center rounded-full text-[15px] ${last ? "bg-(--lp-accent-strong) text-white" : "border border-(--lp-accent) bg-(--lp-bg) text-(--lp-accent-text)"}`}
                    >
                      {index + 1}
                    </span>
                    <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-(--lp-accent-text)">
                      {item.tag}
                    </span>
                  </div>
                  <p className="lp-display mt-4 text-[18px] leading-tight text-(--lp-ink)">{item.title}</p>
                  <p className="mt-3 text-[14px] leading-5 text-(--lp-muted)">{item.body}</p>
                </li>
              );
            })}
          </ol>

          <p data-reveal className="mt-10 max-w-3xl text-[15px] leading-6 text-(--lp-muted)">
            The last step matters: a recommendation is only as current as the evidence and approval
            behind it.{" "}
            <strong className="font-semibold text-(--lp-ink)">When evidence changes, the decision
              must be checked again.</strong>
          </p>
        </div>
      </section>

      {/* ── Capabilities: split layout with a composite media card ─────── */}
      <section id="capabilities" className="lp-band border-t border-(--lp-line)">
        <div className="lp-frame relative px-4 py-16 sm:px-6 sm:py-24">
          <Ticks />
          <div className="grid gap-10 sm:gap-14 lg:grid-cols-[1fr_1.35fr]">
            <div data-reveal>
              <Eyebrow>The intelligence engine</Eyebrow>
              <h2 className="mt-6 text-[30px] text-(--lp-ink) sm:text-[44px]">
                Connected evidence.{" "}<br /><Box>Inspectable decisions.</Box>
              </h2>
              <p className="mt-6 max-w-md text-[16px] leading-6 text-(--lp-muted)">
                FalkorDB links source versions, claims, agent memory, decisions and approvals. The
                workspace offers Globe, Graph, Lineage and Timeline views; the screens below illustrate
                specialized capabilities in the AIDTRACE workspace.
              </p>

              <div className="mt-10">
                {capabilities.map((item, index) => {
                  const on = index === capability;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      aria-pressed={on}
                      aria-controls="capability-panel"
                      onClick={() => setCapability(index)}
                      className="relative block w-full border-b border-(--lp-line) py-4 pl-3 text-left"
                    >
                      {/* 20px / 500-on-active, matching the reference's own tab
                        metrics and its 0.24s colour easing. Light-section tokens:
                        this list sits on --lp-band, so --lp-accent-text and
                        --lp-tab-idle are the pair that clears 4.5:1 here. At 20px
                        these are not "large text", so --lp-accent (3.35:1) and the
                        dark-band tokens do not qualify. */}
                      <span
                        className={`lp-display text-[20px] transition-colors duration-[240ms] ease-[cubic-bezier(0.4,0,0.2,1)] ${on ? "font-medium text-(--lp-accent-text)" : "text-(--lp-tab-idle) hover:font-medium hover:text-(--lp-ink)"}`}
                      >
                        {item.name}
                      </span>
                      <span
                        aria-hidden="true"
                        className={`absolute -bottom-px left-0 h-0.5 bg-(--lp-accent) transition-all duration-[240ms] ease-[cubic-bezier(0.4,0,0.2,1)] ${on ? "w-4/5" : "w-0"}`}
                      />
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Composite card: gradient media on top, white text block beneath. */}
            {/* Stretches to the tab list's full height rather than sitting short of
              it. The slack goes to the media panel, not the copy: a taller mock
              is the point of the card, a taller paragraph is just white space. */}
            <div id="capability-panel" data-reveal className="lp-card relative flex flex-col border border-(--lp-accent) bg-(--lp-surface)">
              <Ticks solid bottom />
              <div key={active.id} className="lp-swap flex flex-1 flex-col">
                {/* Both regions grow but neither shrinks (`flex: N 0 auto`), and the
                  slack is split 2:1 so a stretched card gives its extra height to
                  the mock rather than to the paragraph.

                  `flex-1` plus an explicit `min-h` is what clipped this panel
                  before: the card is a grid item stretched to the tab list's
                  height, so when a mock needed more room than that the flex line
                  was over-constrained, and an explicit `min-height` replaces the
                  automatic minimum size — so the panel shrank to its floor and cut
                  the last rows off Ingestion and Root cause. `shrink-0` restores
                  content as the floor and lets the card grow instead. */}
                <div className="lp-media lp-dither relative flex min-h-[340px] flex-[2_0_auto] flex-col p-5 sm:min-h-[350px] sm:p-6">
                  <p className="inline-block self-start bg-(--lp-accent-strong) px-3 py-1.5 text-[10px] font-semibold uppercase leading-4 tracking-[0.06em] text-white sm:text-[11px]">
                    {active.banner}
                  </p>
                  <div className="mt-5 flex flex-1 flex-col justify-center">
                    <active.Mock />
                  </div>
                </div>

                <div className="flex min-h-[208px] flex-[1_0_auto] flex-col justify-center p-5 sm:p-7">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-(--lp-accent-text)">{active.eyebrow}</p>
                  <h3 className="mt-3 text-[24px] text-(--lp-ink) sm:text-[32px]">{active.title}</h3>
                  <p className="mt-4 max-w-xl text-[15px] leading-6 text-(--lp-muted)">{active.body}</p>
                </div>
              </div>
            </div>
          </div>

          {/* The same subject at a different altitude: eight screens above, the ten
              things behind them here. It used to sit in its own section further down
              the page, which read as a second, flatter capabilities list and repeated
              claims the Ingestion and Provenance panels already make. Cell borders
              rather than a gap mesh — a mesh paints its container colour into
              whatever cells the last row leaves over. */}
          <div data-reveal className="mt-16">
            <div className="border-b border-(--lp-line) pb-4">
              <p className="lp-display text-[20px] text-(--lp-ink) sm:text-[24px]">
                What connects those eight examples
              </p>
              {/* The counts differ because the axes differ, and a reader who is not
                  told that reads "ten" as the complete set and the eight tabs as a
                  subset of it. The tabs are screens; these are the technology beneath
                  them plus the work that never gets a screen of its own. */}
              <p className="mt-2 max-w-2xl text-[14px] leading-5 text-(--lp-muted)">
                AIDTRACE connects specialized analysis to a shared evidence and decision graph,
                so relationships can be inspected across workflows.
              </p>
            </div>
            <dl className="grid border-l border-(--lp-line) sm:grid-cols-2">
              {capabilityList.map(([name, how]) => (
                <div
                  key={name}
                  data-stagger
                  className="lp-cell flex gap-3.5 border-b border-r border-(--lp-line) p-4 sm:p-5"
                >
                  <span aria-hidden="true" className="mt-[7px] size-2 shrink-0 bg-(--lp-accent)" />
                  <div className="min-w-0">
                    <dt className="text-[15px] font-semibold leading-snug text-(--lp-ink)">{name}</dt>
                    <dd className="mt-1.5 text-[13px] leading-5 text-(--lp-muted)">{how}</dd>
                  </div>
                </div>
              ))}
            </dl>
          </div>
        </div>
      </section>

      {/* ── System design: the capabilities layout, mirrored ─────────────── */}
      {/* Same split as Capabilities, a tab list beside a composite card whose
          media panel sits above its copy, but flipped so that the card is on the
          left and the heading, intro and tabs are right-aligned on the right.
          A dark section, so lp-frame--dark: without it the side rails render in
          the light hairline colour against black. */}
      <section id="system" className="bg-(--lp-dark) text-white">
        <div className="lp-frame lp-frame--dark relative grid gap-10 px-4 py-16 sm:gap-14 sm:px-6 sm:py-24 lg:grid-cols-[1.35fr_1fr]">
          {/* The card is the diagram, nothing else. White edge to edge, padding
              included: these diagrams are drawn in a palette built for a white
              ground, and a white plate floating inside a dark panel framed them
              twice. The border is kept only so lp-card's hover can turn it accent. */}
          {/* From lg the white panel is taken out of flow (absolute inset-0), which
              is what keeps the card the same height as the tab list beside it. In
              flow, a tall diagram would drive the grid row and the card would run
              past the last tab; out of flow it contributes no height, so the row is
              sized by the tabs alone, and the card, being a grid item and so stretched
              by default, fills exactly that. The diagram then fits inside via
              max-h-full rather than setting the height itself.

              Below lg the columns stack, there is no sibling to match, and the panel
              goes back in flow on its own min-height. */}
          <div id="system-panel" data-reveal className="lp-card relative flex flex-col border border-(--lp-dark-line)">
            <Ticks solid bottom />
            <div
              key={activeSystem.id}
              className="lp-swap flex min-h-[420px] flex-1 items-center justify-center overflow-x-auto bg-white p-4 sm:min-h-[520px] sm:p-6 lg:absolute lg:inset-0 lg:min-h-0"
            >
              <SystemDiagramImage src={activeSystem.src} alt={activeSystem.alt} />
            </div>
          </div>

          {/* order-first below lg so the heading still introduces the card on a
              phone, rather than arriving underneath it. */}
          <div data-reveal className="order-first flex flex-col items-end text-right lg:order-last">
            <Eyebrow>System architecture</Eyebrow>
            <h2 className="mt-6 text-[30px] text-white sm:text-[44px]">
              One connected foundation.{" "}<br /><Box fill>Traceable decisions.</Box>
            </h2>
            <p className="mt-6 max-w-md text-[16px] leading-6 text-(--lp-dark-muted)">
              These diagrams show the existing application services and specialist data stores.
              The shared FalkorDB graph connects evidence, memory, decisions and approvals across them.
              Open a block to inspect each layer.
            </p>

            <div className="mt-10 w-full">
              {systemDesign.map((item, index) => {
                const on = index === systemTab;
                return (
                  <button
                    key={item.id}
                    type="button"
                    aria-pressed={on}
                    aria-controls="system-panel"
                    onClick={() => setSystemTab(index)}
                    className="relative block w-full border-b border-(--lp-dark-line) py-4 pr-3 text-right"
                  >
                    {/* Mirror of the Capabilities tab, on dark tokens: at 20px
                        this is not "large text", but --lp-accent clears 4.5:1
                        against --lp-dark, so it qualifies here where it would
                        not on the light band. */}
                    <span
                      className={`lp-display text-[20px] transition-colors duration-[240ms] ease-[cubic-bezier(0.4,0,0.2,1)] ${on ? "font-medium text-(--lp-accent)" : "text-(--lp-dark-muted) hover:font-medium hover:text-white"}`}
                    >
                      {item.name}
                    </span>
                    <span
                      aria-hidden="true"
                      className={`absolute -bottom-px right-0 h-0.5 bg-(--lp-accent) transition-all duration-[240ms] ease-[cubic-bezier(0.4,0,0.2,1)] ${on ? "w-4/5" : "w-0"}`}
                    />
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </section>

      {/* ── Use cases: full-bleed tab bar over a media panel ───────────── */}
      <section id="field" className="border-t border-(--lp-line)">
        <div className="lp-frame relative px-4 py-16 sm:px-6 sm:py-24">
          <Ticks />
          <div data-reveal>
            <Eyebrow>Specialized intelligence extensions</Eyebrow>
            <h2 className="mt-6 text-[30px] text-(--lp-ink) sm:text-[44px]">
              One platform.{" "}<Box>Different problems. <span className="text-(--lp-accent)">Shared evidence.</span></Box>
            </h2>
          </div>

          <div data-reveal className="mt-10">
            <div className="grid grid-cols-2 gap-px bg-(--lp-tab-line) sm:grid-cols-3 lg:grid-cols-6">
              {audiences.map((item, index) => {
                const on = index === audience;
                return (
                  <button
                    key={item.name}
                    type="button"
                    aria-pressed={on}
                    aria-controls="audience-panel"
                    onClick={() => setAudience(index)}
                    className={`min-h-16 px-4 py-5 text-center text-[15px] font-medium transition-colors ${on ? "bg-(--lp-accent-strong) text-white" : "bg-(--lp-tab) text-(--lp-ink) hover:bg-(--lp-tab-hover)"}`}
                  >
                    {item.name}
                  </button>
                );
              })}
            </div>

            <div id="audience-panel" className="lp-media lp-dither relative p-4 sm:p-8">
              <div key={audiences[audience].name} className="lp-swap">
                <div className="max-w-2xl">
                  <h3 className="text-[24px] text-white sm:text-[32px]">{audiences[audience].title}</h3>
                  <p className="mt-3 text-[15px] leading-6 text-white/85">{audiences[audience].body}</p>
                </div>
                <div className="mt-6 border border-white/20 p-2 sm:p-3">
                  <Shot src={audiences[audience].shot} alt="AIDTRACE workspace showing connected evidence and decisions" />
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Evals: a real chart, on dark ───────────────────────────────── */}
      <section id="evidence" className="bg-(--lp-dark) text-white">
        <div className="lp-frame lp-frame--dark px-4 py-16 sm:px-6 sm:py-24">
          <div data-reveal>
            <Eyebrow>Evaluation</Eyebrow>
            <h2 className="mt-6 max-w-3xl text-[30px] sm:text-[44px]">
              Measure the function.{" "}<br />
              <Box fill>Name the scope.</Box>
            </h2>
            <p className="mt-6 max-w-xl text-[16px] leading-6 text-(--lp-dark-muted)">
              The figures below come from an industrial question-answering benchmark on a
              synthetic dataset. They do not measure all AIDTRACE extensions or FalkorDB graph reasoning.
            </p>
          </div>

          <div data-reveal className="mt-14">
            <p className="text-[11px] uppercase tracking-[0.12em] text-(--lp-dark-muted)">Industrial extension benchmark · 46 questions</p>

            {/* pt-24 reserves room for the badge, value and sub-line stacked
                above each bar; a 100% bar would otherwise push them off. */}
            <div className="mt-6 flex gap-3 pt-24 sm:gap-5">
              {/* y axis every 10, labels centred on their gridline */}
              <div className="relative h-[460px] w-7 shrink-0" aria-hidden="true">
                {[100, 90, 80, 70, 60, 50, 40, 30, 20, 10, 0].map((n) => (
                  <span
                    key={n}
                    className="absolute right-0 translate-y-1/2 text-[11px] leading-none text-(--lp-dark-muted)"
                    style={{ bottom: `${n}%` }}
                  >
                    {n}
                  </span>
                ))}
              </div>

              <div className="relative min-w-0 flex-1">
                <div
                  aria-hidden="true"
                  className="absolute inset-0 border-b border-l border-(--lp-dark-line)"
                  style={{
                    backgroundImage: "linear-gradient(to top, var(--lp-dark-line) 1px, rgb(0 0 0 / 0) 1px)",
                    backgroundSize: "100% 10%",
                  }}
                />
                <ul className="relative grid h-[460px] grid-cols-3">
                  {evalBars.map((bar) => (
                    <li key={bar.label} className="relative">
                      <div
                        className={`lp-bar absolute inset-x-[24%] bottom-0 ${bar.hero ? "lp-bar--hero lp-dither" : "bg-(--lp-bar-idle)"}`}
                        style={{ height: `${bar.value}%` }}
                      />

                      <div className="absolute inset-x-0 text-center" style={{ bottom: `calc(${bar.value}% + 14px)` }}>
                        <span className={`inline-block px-2 py-0.5 text-[10px] font-semibold tracking-[0.04em] ${bar.hero ? "bg-(--lp-accent-strong) text-white" : "text-(--lp-dark-muted)"}`}>
                          {bar.badge}
                        </span>
                        <p className={`lp-display mt-1.5 text-[26px] sm:text-[32px] ${bar.hero ? "text-white" : "text-(--lp-dark-muted)"}`}>
                          {bar.display}
                        </p>
                        <p className="mt-1 text-[11px] text-(--lp-dark-muted)">{bar.sub}</p>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            {/* x axis */}
            <div className="ml-10 grid grid-cols-3 pt-4">
              {evalBars.map((bar) => (
                <div key={bar.label} className="text-center">
                  <p className={`text-[14px] font-semibold ${bar.hero ? "text-(--lp-accent)" : "text-white"}`}>{bar.label}</p>
                  <p className="mt-1 text-[12px] text-(--lp-dark-muted)">{bar.note}</p>
                </div>
              ))}
            </div>
            <p className="mt-8 max-w-2xl text-[13px] leading-5 text-(--lp-dark-muted)">
              One run: all 40 answers came from the pinned Nemotron 3 Super model on NVIDIA NIM, with
              no fallback provider. Six safety-critical questions were refused because no authoritative source
              covers them, and a correct refusal is graded as correct. All six misses retrieved
              the right evidence — the gap is in how the answer is written, not in what the system
              found.
            </p>
          </div>

          {/* The rest of the harness. Hairlines are drawn per cell rather than by a
              gap-px mesh over a tinted container: the suite count is data and does not
              divide evenly into two or three columns, and a mesh paints its container
              colour into whatever cells the last row leaves over, leaving a grey block
              where a card should be. Per-cell borders leave that space as section ground. */}
          <div data-reveal className="mt-16">
            <p className="text-[11px] uppercase tracking-[0.12em] text-(--lp-dark-muted)">Other industrial extension checks</p>
            <div className="mt-6 grid border-t border-l border-(--lp-dark-line) sm:grid-cols-2 lg:grid-cols-3">
              {evalSuites.map((suite) => (
                <div key={suite.name} data-stagger className="lp-cell lp-cell--dark border-b border-r border-(--lp-dark-line) bg-(--lp-dark) p-5">
                  <p className="text-[11px] uppercase tracking-[0.08em] text-(--lp-dark-muted)">{suite.name}</p>
                  <p className="lp-display mt-3 text-[32px] text-white">
                    {suite.headline}
                  </p>
                  <p className="mt-1 text-[12px] text-(--lp-accent)">{suite.headlineNote}</p>
                  <dl className="mt-4 space-y-1.5 border-t border-(--lp-dark-line) pt-3 text-[12px]">
                    {suite.rows.map(([term, value]) => (
                      <div key={term} className="flex justify-between gap-3">
                        <dt className="text-(--lp-dark-muted)">{term}</dt>
                        <dd className="text-right font-semibold text-white">{value}</dd>
                      </div>
                    ))}
                  </dl>
                </div>
              ))}

              {/* Ten suites into three columns leaves one card alone with two dead
                  cells beside it. This is one cell spanning both of them, so the last
                  row closes. It is filled rather than another stat card on purpose:
                  the grid states ten results, and the one thing none of them say is
                  how a result is decided, which is the claim the whole section rests on.

                  sm:col-span-2 covers lg too: at two columns it takes the last row,
                  at three it takes the two cells the tenth card leaves over. */}
              <div
                data-stagger
                className="border-b border-r border-(--lp-dark-line) bg-(--lp-accent-strong) p-5 sm:col-span-2"
              >
                <p className="text-[11px] uppercase tracking-[0.08em] text-white">How every one of these is graded</p>
                <p className="lp-display mt-3 text-[26px] leading-tight text-white sm:text-[30px]">
                  Fixed rules, never another model.
                </p>
                <p className="mt-3 max-w-2xl text-[13px] leading-5 text-white">
                  An answer has to contain the facts the question requires, avoid the ones it rules
                  out, and cite a source. Miss any of the three and it counts as wrong. The same rules
                  run every time, so two runs of the same question are always scored the same way.
                </p>
              </div>
            </div>
          </div>


        </div>
      </section>

      {/* ── Provenance ──────────────────────────────────────────────────── */}
      <section id="provenance" className="lp-band border-t border-(--lp-line)">
        <div className="lp-frame relative px-4 py-16 sm:px-6 sm:py-24">
          <Ticks />
          <div data-reveal>
            <Eyebrow>Trust and evidence</Eyebrow>
            <h2 className="mt-6 max-w-4xl text-[30px] text-(--lp-ink) sm:text-[44px]">
              No <Box>important conclusion</Box> without a <Box fill>traceable source.</Box>
            </h2>
            <p className="mt-6 max-w-xl text-[16px] leading-6 text-(--lp-muted)">
              AIDTRACE links claims, memory and decisions to the evidence they depend on. The
              graph screenshot and record below show the evidence path through source versions,
              claims, memory, decisions and approval revisions.
            </p>
          </div>

          <div data-reveal className="lp-media lp-dither relative mt-12 p-3 sm:p-6">
            <div className="border border-white/20 p-2 sm:p-3">
              <Shot src="graph" alt="AIDTRACE scenario graph showing suppliers, evidence estimates and a connected sourcing decision." />
            </div>
          </div>

          {/* The six properties against one real fact rather than in the abstract.
              A bare name-and-definition list asks the reader to imagine what a
              stored fact looks like; this shows them one, so "checkable" stops
              being a claim and becomes something they can read off the page.

              The fact sits in the accent header of the same panel, so the six rows
              below are visibly properties OF it rather than six loose definitions. */}
          <div data-reveal className="lp-card mt-12 border border-(--lp-line) bg-(--lp-surface)">
            <div className="border-b border-(--lp-line) bg-(--lp-accent-strong) px-5 py-4 sm:px-7">
              {/* Full white, not white/80: at 11px this is small text, and 80% over
                  --lp-accent-strong lands at 3.7:1 where it needs 4.5. The hierarchy
                  against the line below comes from size and weight instead. */}
              <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-white">
                One changed source, and its decision impact
              </p>
              <p className="lp-display mt-2 text-[19px] leading-tight text-white sm:text-[22px]">
                A supplier audit interval changed from 180 to 90 days; the earlier approval is stale.
              </p>
            </div>

            <dl className="grid sm:grid-cols-2">
              {edgeProperties.map(({ name, value, note }) => (
                <div
                  key={name}
                  /* Every cell keeps its bottom rule and the footer keeps none, so the
                     divider above the footer is one hairline at every breakpoint rather
                     than two stacked ones once the grid drops to a single column. */
                  className="border-b border-(--lp-line) px-5 py-5 sm:px-7 sm:[&:nth-child(odd)]:border-r"
                >
                  <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                    <dt>
                      {/* The code style distinguishes workflow field names from their example values. */}
                      <code className="text-[13px] font-semibold tracking-tight text-(--lp-accent-text)">{name}</code>
                    </dt>
                    {/* tabular-nums so the dates and scores line up down the column. */}
                    <dd className="lp-display text-[15px] tabular-nums text-(--lp-ink)">{value}</dd>
                  </div>
                  <dd className="mt-2 text-[13px] leading-5 text-(--lp-muted)">{note}</dd>
                </div>
              ))}
            </dl>

            <p className="bg-(--lp-band) px-5 py-3 text-[12px] text-(--lp-muted) sm:px-7">
              A synthetic Evidence Drift example. Source versions and decision revisions keep the change traceable for human review.
            </p>
          </div>
        </div>
      </section>
      {/* ── FAQ: two columns, category rail then the answers ──────────── */}
      <section id="faq" className="bg-(--lp-dark) text-white">
        <div className="lp-frame lp-frame--dark px-4 py-16 sm:px-6 sm:py-24">
          <div data-reveal>
            <Eyebrow>FAQ</Eyebrow>
            <h2 className="mt-6 max-w-2xl text-[30px] sm:text-[44px]">
              Your questions,{" "}<br /><Box fill>answered.</Box>
            </h2>
            <p className="mt-6 max-w-md text-[15px] leading-6 text-(--lp-dark-muted)">
              How connected evidence, agent memory, human review and specialized extensions fit
              together. Explore the workspace for more detail.
            </p>
          </div>

          <div data-reveal className="mt-12 grid gap-10 lg:grid-cols-[0.8fr_1.4fr]">
            <div className="lp-dashed border-t">
              {faqGroups.map((group, index) => {
                const on = index === faqGroup;
                return (
                  <button
                    key={group.name}
                    type="button"
                    aria-pressed={on}
                    aria-controls="faq-answers"
                    onClick={() => setFaqGroup(index)}
                    className="lp-dashed flex w-full items-center justify-between border-b py-6 text-left"
                  >
                    <span className={`lp-display text-[26px] transition-colors sm:text-[32px] ${on ? "text-white" : "text-(--lp-dark-muted) hover:text-white"}`}>
                      {group.name}
                    </span>
                    <span aria-hidden="true" className={`text-[18px] transition-transform ${on ? "rotate-90 text-(--lp-accent)" : "text-(--lp-dark-muted)"}`}>›</span>
                  </button>
                );
              })}
            </div>

            <div id="faq-answers" className="lp-dashed border-t">
              <div key={faqGroups[faqGroup].name} className="lp-swap">
                {faqGroups[faqGroup].items.map(([question, answer], index) => (
                  <details key={question} className="lp-dashed group border-b" open={index === 0}>
                    <summary className="flex cursor-pointer list-none items-center justify-between gap-6 py-5 text-[17px] font-medium text-white marker:hidden hover:text-(--lp-accent)">
                      {question}
                      <span aria-hidden="true" className="shrink-0 text-[20px] text-(--lp-accent) transition-transform group-open:rotate-45">+</span>
                    </summary>
                    <p className="max-w-2xl pb-6 text-[15px] leading-6 text-(--lp-dark-muted)">{answer}</p>
                  </details>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Scrolling pad: Built for Graph Hacks · Backed by We Make Devs · Memory is FALKOR DB */}
      <div aria-hidden="true" className="overflow-hidden bg-(--lp-band) py-2">
        <div className="overflow-hidden bg-(--lp-dark) py-3">
          {/* Each half must be at least as wide as the viewport or the -50%
              slide opens a gap at the right edge. */}
          <div className="lp-marquee-track flex w-max whitespace-nowrap items-center">
            {Array.from({ length: 8 }, () => [
              { title: "Built for Graph Hacks", icon: GraphHacksIcon, pill: "Track 01", pillCls: "bg-[#38bdf8]/15 text-[#38bdf8] border-[#38bdf8]/40" },
              { title: "Backed by We Make Devs", icon: WeMakeDevsIcon, pill: "Community", pillCls: "bg-[#34d399]/15 text-[#34d399] border-[#34d399]/40" },
              { title: "Memory is FALKOR DB", icon: FalkorDBIcon, pill: "GraphBLAS", pillCls: "bg-[#ff6b4a]/15 text-[#ff6b4a] border-[#ff6b4a]/40" },
            ]).flat().map((item, i) => (
              <span key={`${item.title}-${i}`} className="mx-8 flex items-center gap-4 text-[22px] font-semibold tracking-wide text-white sm:text-[28px]">
                <item.icon />
                <span className="tracking-tight">{item.title}</span>
                <span className={`rounded-full border px-2.5 py-0.5 font-mono text-[11px] font-medium uppercase tracking-widest ${item.pillCls}`}>
                  {item.pill}
                </span>
                <span aria-hidden="true" className="ml-4 text-white/20 select-none text-lg">✦</span>
              </span>
            ))}
          </div>
        </div>
      </div>
      <p className="sr-only">Built for Graph Hacks, backed by We Make Devs, memory is FALKOR DB.</p>

      {/* ── Footer ──────────────────────────────────────────────────────── */}
      <footer className="bg-(--lp-bg)">
        <div className="lp-frame px-4 py-14 sm:px-6">
          <div className="grid gap-10 sm:grid-cols-2 lg:grid-cols-[2fr_repeat(3,0.6fr)]">
            <div>
              <div className="flex items-center gap-2.5">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src="/logo.png" alt="" width={26} height={26} className="object-cover" />
                <span className="lp-display text-[22px] text-(--lp-ink)">AIDTRACE</span>
              </div>
              <p className="mt-4 max-w-xs text-[14px] leading-5 text-(--lp-muted)">
                Understand the connections. Trust the evidence. Improve the decision.
              </p>
            </div>

            {footerColumns.map(({ heading, links }) => (
              <div key={heading}>
                <p className="lp-display text-[18px] text-(--lp-ink)">{heading}</p>
                <ul className="mt-4 space-y-2.5">
                  {links.map(([label, href]) => (
                    <li key={href}>
                      {href.startsWith("/") ? (
                        <Link href={href} className="text-[14px] text-(--lp-muted) transition-colors hover:text-(--lp-accent-text)">{label}</Link>
                      ) : (
                        <a
                          href={href}
                          {...(href.startsWith("http") ? { target: "_blank", rel: "noreferrer noopener" } : {})}
                          className="text-[14px] text-(--lp-muted) transition-colors hover:text-(--lp-accent-text)"
                        >
                          {label}
                        </a>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            ))}

          </div>
        </div>

        {/* Full-width divider — lives outside lp-frame so it runs edge-to-edge */}
        <div className="border-t border-(--lp-line)" />

        <div className="lp-frame px-4 pb-8 pt-6 sm:px-6">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <p className="text-[12px] uppercase tracking-[0.08em] text-(--lp-muted)">
              © 2026 AIDTRACE
            </p>
          </div>
        </div>
      </footer>
    </main>
  );
}
