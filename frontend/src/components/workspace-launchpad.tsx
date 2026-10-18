"use client";

import Link from "next/link";
import Image from "next/image";
import { Icon } from "@/components/icon";
import { ButtonLink } from "@/components/ui";
import { routeAllowed, useRole } from "@/components/use-role";
import { CAPABILITIES, CAPABILITY_GROUPS } from "@/lib/capabilities";

const FEATURED: Record<string, string[]> = {
  operations: ["Supplier & Asset Inventory", "Decision Briefs", "Supply Events"],
  investigation: ["Root Cause Analysis", "Evidence Graph", "AIDTRACE Copilot"],
  intelligence: ["Agent Map", "Agent Memory & FalkorDB", "System Health"],
  knowledge: ["Document Vault", "Evidence Curation", "Models & Fine-tuning"],
  governance: ["Conflict Resolution", "Management of Change", "Audit Trail"],
  cyber: ["Dependency Risk Discovery", "Evidence Drift & Memory", "Response & Verification"],
};

export function WorkspaceLaunchpad() {
  const role = useRole();
  return (
    <section aria-labelledby="workspace-heading" className="mt-7" data-testid="workspace-launchpad">
      <div className="kairos-depth-hero sidebar-scope overflow-hidden border border-line bg-surface p-5 sm:p-7">
        <div className="kairos-depth-scene">
          <Image
            src="/art/aidtrace-platform.webp"
            alt="AIDTRACE connecting supplier evidence to a reviewed decision and verified outcome"
            fill
            sizes="(max-width: 900px) 100vw, 560px"
            className="object-contain"
            loading="eager"
            fetchPriority="high"
          />
        </div>
        <div className="kairos-depth-copy relative z-10 flex flex-wrap items-start justify-between gap-5">
          <div className="max-w-2xl">
            <p className="text-label font-medium uppercase tracking-widest text-muted">AIDTRACE · supply-chain risk intelligence</p>
            <h2 id="workspace-heading" className="mt-2 text-title font-semibold text-ink sm:text-display">Know when a supplier decision is no longer safe.</h2>
            <p className="mt-3 max-w-xl text-body leading-relaxed text-muted">Supplier risk, cyber exposure and FalkorDB agent memory, connected. Start with a question or open the tools behind every decision.</p>
          </div>
          <ButtonLink href="/workspace" variant="primary" className="min-h-11">Explore All Features <Icon name="caret-right" className="size-4" /></ButtonLink>
        </div>
        <ol aria-label="AIDTRACE decision workflow" className="relative z-10 mt-7 grid grid-cols-2 border-t border-line sm:grid-cols-4">
          {[
            ["01", "Understand", "Suppliers & source evidence", "/assets"],
            ["02", "Investigate", "FalkorDB graph reasoning & agent memory", "/resolveai"],
            ["03", "Decide", "Evidence drift & human approval", "/governance"],
            ["04", "Verify", "Re-evaluation & audit evidence", "/compliance"],
          ].map(([step, title, description, href]) => (
            <li key={step} className="min-w-0 border-b border-line sm:border-b-0">
              <Link href={href} className="group block py-4 pr-3 focus-visible:outline-2 focus-visible:outline-accent">
                <span className="text-micro font-semibold text-accent">{step}</span>
                <span className="ml-2 text-body font-semibold text-ink group-hover:underline">{title}</span>
                <span className="mt-1 block text-caption text-muted">{description}</span>
              </Link>
            </li>
          ))}
        </ol>
      </div>
      <div className="mt-5 flex flex-wrap items-end justify-between gap-2">
        <h3 className="text-body font-semibold text-ink">AIDTRACE Workspaces</h3>
        <span className="text-caption text-muted">Tools and workflows, always within reach</span>
      </div>
      <div className="kairos-depth-grid mt-3 grid gap-5 md:grid-cols-2 xl:grid-cols-3">
        {CAPABILITY_GROUPS.map((group, index) => (
          <article key={group.id} className="kairos-depth-card group flex min-w-0 flex-col border border-line bg-surface p-5">
            <div className="flex items-center justify-between">
              <span className="kairos-depth-icon grid size-10 place-items-center bg-accent-soft text-accent"><Icon name={group.icon} className="size-5" /></span>
              <span className="font-mono text-caption text-muted">0{index + 1}</span>
            </div>
            <Link href={group.href} className="mt-4 inline-flex min-h-9 items-center justify-between gap-2 text-lg font-semibold text-ink hover:text-accent focus-visible:outline-2 focus-visible:outline-accent">
              {group.title}<Icon name="caret-right" className="size-4 shrink-0 text-muted" />
            </Link>
            <p className="mt-1 min-h-10 text-caption leading-relaxed text-muted">{group.description}</p>
            <div className="mt-4 flex-1 border-t border-line pt-2">
              {FEATURED[group.id].map((title) => {
                const feature = CAPABILITIES.find((item) => item.title === title)!;
                const allowed = routeAllowed(feature.href.split("#")[0], role);
                return allowed ? (
                  <Link key={title} href={feature.href} className="flex min-h-10 items-center justify-between gap-2 text-caption text-ink hover:text-accent focus-visible:outline-2 focus-visible:outline-accent">
                    {title}<Icon name="caret-right" className="size-3 text-muted" />
                  </Link>
                ) : <p key={title} className="flex min-h-10 items-center justify-between gap-2 text-caption text-muted">{title}<span className="text-micro">Restricted</span></p>;
              })}
            </div>
            <div className="mt-3 flex items-center justify-between gap-2 border-t border-line pt-3 text-micro text-muted">
              <span>{group.id === "cyber" ? "Workflow preview" : group.id === "intelligence" ? "Integration in progress" : "AIDTRACE workflows"}</span>
              <Link href={`/workspace?group=${group.id}`} className="inline-flex min-h-8 items-center text-caption font-medium text-accent hover:underline">View all</Link>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
