"use client";

import { useState } from "react";
import Link from "next/link";
import { Button, ButtonLink, PageHeader } from "@/components/ui";
import { Icon } from "@/components/icon";
import { getHealthDetailed } from "@/lib/api";
import { useFetch } from "@/lib/use-fetch";
import { ReasoningWorkspace } from "../overview/_components/reasoning-workspace";
import { DriftDemoPanel } from "./_components/drift-demo-panel";
import { EvidenceIntakeWorkspace } from "./_components/evidence-intake-workspace";

import dynamic from "next/dynamic";

const ConsumerWorkspace = dynamic(
  () => import("@/features/resolveai/consumer-workspace").then((m) => m.ConsumerWorkspace),
  { loading: () => <p role="status" className="p-6 text-caption text-muted">Loading remedy workspace…</p>, ssr: false }
);

const STEPS = [
  { title: "Observe", role: "Evidence collector", input: "A sensitive account-change request and its source records.", output: "Timestamped evidence with source identity and provenance.", check: "Missing or stale records leave the assessment UNKNOWN." },
  { title: "Recall", role: "Memory investigator", input: "Verified historical relationships, previous decisions and evidence expiry.", output: "Relevant prior patterns, including contradictions and missing context.", check: "A similar past event is a lead, never proof of fraud." },
  { title: "Investigate", role: "Hypothesis analyst", input: "Current request, historical context and independent corroboration.", output: "Competing explanations: legitimate change, compromised identity or insufficient evidence.", check: "Test benign explanations before escalating a fraud hypothesis." },
  { title: "Authorize", role: "Human decision owner", input: "Evidence references, impact analysis and a proposed scoped response.", output: "An explicit approval or rejection tied to the exact target.", check: "Model output and spoken intent cannot authorize privileged actions." },
  { title: "Verify", role: "Independent verifier", input: "Execution record and fresh observations from a separate check.", output: "Verified postconditions or an unresolved case with remaining evidence gaps.", check: "An API success response does not prove containment." },
] as const;

export default function ResolveAIPage() {
  const health = useFetch(getHealthDetailed);
  const [activeTab, setActiveTab] = useState<"remedy" | "drift" | "overview">("remedy");
  const [step, setStep] = useState(0);
  const selected = STEPS[step];
  return (
    <div className="mx-auto max-w-[1400px]">
      <PageHeader title="Resolve Intelligence" lede="AIDTRACE owns the workflow and the decision. Resolve contributes investigative intelligence, connected evidence and specialist reasoning on FALKOR DB." actions={<ButtonLink href="/workspace">All Features</ButtonLink>} />

      <div className="mt-6"><EvidenceIntakeWorkspace /></div>

      <nav aria-label="Resolve sub-modules" className="mt-6 flex flex-wrap gap-2 border-b border-line pb-3">
        <Button
          variant={activeTab === "remedy" ? "primary" : "ghost"}
          onClick={() => setActiveTab("remedy")}
          className="min-h-11"
        >
          Consumer Remedy Investigation
        </Button>
        <Button
          variant={activeTab === "drift" ? "primary" : "ghost"}
          onClick={() => setActiveTab("drift")}
          className="min-h-11"
        >
          Evidence Drift Cascade
        </Button>
        <Button
          variant={activeTab === "overview" ? "primary" : "ghost"}
          onClick={() => setActiveTab("overview")}
          className="min-h-11"
        >
          Architecture & System Map
        </Button>
      </nav>

      {activeTab === "remedy" && (
        <div className="mt-6">
          <ConsumerWorkspace />
        </div>
      )}

      {activeTab === "drift" && (
        <div className="mt-6 space-y-6">
          <DriftDemoPanel />
        </div>
      )}

      {activeTab === "overview" && (
        <div className="mt-6 space-y-6">
          <nav aria-label="Intelligence sections" className="flex flex-wrap gap-2 border-y border-line py-3">
            {[["agents", "Agent Map"], ["infrastructure", "Infrastructure"], ["memory", "Agent Memory"], ["curation", "Data Curation"], ["models", "Models & Fine-tuning"], ["cyber", "Cyber & Fraud"]].map(([id, title]) => <Link key={id} href={`#${id}`} className="inline-flex min-h-11 items-center px-3 text-caption font-medium text-ink hover:bg-surface-2 focus-visible:outline-2 focus-visible:outline-accent">{title}</Link>)}
          </nav>
          <div className="grid gap-3 sm:grid-cols-3">
            {[
              ["AIDTRACE", "Experience & governance", "Workspaces, approval boundaries and accountable decisions."],
              ["Resolve", "Investigation integration", "Specialist mapping is visible; powered by FALKOR DB."],
              ["FalkorDB", "Reasoning infrastructure", "Connection status is reported below from the health endpoint."],
            ].map(([title, subtitle, description]) => <article key={title} className="border border-line bg-surface p-5"><p className="text-caption text-muted">{subtitle}</p><h2 className="mt-2 text-title font-semibold text-ink">{title}</h2><p className="mt-2 text-caption leading-relaxed text-muted">{description}</p></article>)}
          </div>
          <ReasoningWorkspace health={health.status === "live" ? health.data : null} loading={health.status === "loading"} />
        </div>
      )}
      <section aria-label="Graph Lab" className="mt-4 flex flex-wrap items-center justify-between gap-3 border border-line bg-surface-2 p-4">
        <p className="max-w-3xl text-caption leading-relaxed text-muted">Explore this evidence graph beyond the single scenario: run blast-radius, decision-gate, containment-cut and other engines on it, and view the result as a network, layers, matrix or timeline.</p>
        <div className="flex gap-2"><ButtonLink href="/hub">Open the Intelligence Hub</ButtonLink></div>
      </section>
      <section id="memory" aria-labelledby="memory-heading" className="scroll-mt-6 border-b border-line py-8">
        <div className="flex items-center gap-3"><Icon name="graph" className="size-6 text-accent" /><h2 id="memory-heading" className="text-title font-semibold">Evidence Memory</h2></div>
        <p className="mt-2 max-w-3xl text-body leading-relaxed text-muted">The integration design connects what was observed, what must remain true, and which decisions depend on that evidence. This is the memory contract; a live memory inspector is not yet connected.</p>
        <ol className="mt-5 grid gap-3 md:grid-cols-4">
          {[
            ["Evidence", "Source, observation time, expiry and integrity."],
            ["Obligation", "The condition a control or asset must satisfy."],
            ["Decision", "Conclusion, reviewer and supporting evidence references."],
            ["Revalidation", "Reopen dependent conclusions when evidence changes."],
          ].map(([title, text], index) => <li key={title} className="border border-line bg-surface p-4"><span className="font-mono text-caption text-accent">0{index + 1}</span><h3 className="mt-3 text-body font-semibold">{title}</h3><p className="mt-2 text-caption leading-relaxed text-muted">{text}</p></li>)}
        </ol>
        <div className="mt-4 flex flex-wrap gap-3"><ButtonLink href="/graph">Explore Existing Evidence</ButtonLink><ButtonLink href="/governance/quarantine">Review Memory Candidates</ButtonLink></div>
      </section>
      <section id="cyber" aria-labelledby="cyber-heading" className="scroll-mt-6 py-8">
        <div className="flex flex-wrap items-center justify-between gap-3"><h2 id="cyber-heading" className="text-title font-semibold">Cyber Defense & Fraud Investigation</h2><span className="border border-line bg-surface-2 px-3 py-1 text-caption text-muted">Workflow preview</span></div>
        <p className="mt-2 max-w-3xl text-body leading-relaxed text-muted">Explore a proposed investigation of a suspicious account-change request. Select a stage to inspect its evidence, agent responsibility and decision boundary. No detection or response is executed here.</p>
        <div className="mt-5 grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
          <div aria-label="Investigation stages" className="flex flex-col gap-2">
            {STEPS.map((item, index) => <Button key={item.title} aria-pressed={step === index} aria-controls="cyber-stage" onClick={() => setStep(index)} variant={step === index ? "primary" : "ghost"} className="min-h-12 justify-start"><span className="font-mono text-caption">0{index + 1}</span>{item.title}</Button>)}
          </div>
          <div id="cyber-stage" aria-live="polite" className="border border-line bg-surface p-5 sm:p-7">
            <p className="text-caption text-muted">Stage {step + 1} of {STEPS.length}</p><h3 className="mt-2 text-title font-semibold">{selected.role}</h3>
            <dl className="mt-5 grid gap-5 sm:grid-cols-2"><div><dt className="text-label font-semibold uppercase tracking-wide text-muted">Input</dt><dd className="mt-2 text-body leading-relaxed">{selected.input}</dd></div><div><dt className="text-label font-semibold uppercase tracking-wide text-muted">Required output</dt><dd className="mt-2 text-body leading-relaxed">{selected.output}</dd></div></dl>
            <div className="mt-6 border-l-2 border-accent bg-surface-2 p-4"><p className="text-caption font-semibold">Decision boundary</p><p className="mt-1 text-caption leading-relaxed text-muted">{selected.check}</p></div>
          </div>
        </div>
        <p className="mt-4 text-caption leading-relaxed text-muted">Hidden-problem detectors, fraud case persistence, NetForensiq forensics and response adapters remain integration work. Existing graph, governance and audit workspaces are available from the feature directory.</p>
      </section>
    </div>
  );
}
