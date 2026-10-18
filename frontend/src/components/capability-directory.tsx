"use client";

import Link from "next/link";
import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { Icon } from "@/components/icon";
import { Button } from "@/components/ui";
import { routeAllowed, useRole } from "@/components/use-role";
import { CAPABILITIES, CAPABILITY_GROUPS, CAPABILITY_KIND_LABELS, type Capability } from "@/lib/capabilities";

export function CapabilityDirectory() {
  const params = useSearchParams();
  const initialGroup = params.get("group");
  const [group, setGroup] = useState(CAPABILITY_GROUPS.some((item) => item.id === initialGroup) ? initialGroup! : "all");
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState("all");
  const role = useRole();
  const filtered = CAPABILITIES.filter((feature) =>
    (group === "all" || feature.group === group) &&
    (kind === "all" || feature.kind === kind) &&
    `${feature.title} ${feature.description} ${feature.group}`.toLowerCase().includes(query.trim().toLowerCase()),
  );
  function reset() { setQuery(""); setGroup("all"); setKind("all"); }
  function card(feature: Capability) {
    const allowed = routeAllowed(feature.href.split("#")[0], role);
    return (
      <article key={feature.title} className="kairos-depth-card flex min-w-0 flex-col border border-line bg-surface p-5">
        <div className="flex flex-wrap items-center justify-between gap-2 text-micro text-muted">
          <span className={feature.kind === "preview" ? "text-caution-ink" : ""}>{CAPABILITY_KIND_LABELS[feature.kind]}</span>
          {!allowed && <span className="border border-line px-2 py-1">Role restricted</span>}
        </div>
        <h3 className="mt-3 text-body font-semibold text-ink">{feature.title}</h3>
        <p className="mt-2 flex-1 text-caption leading-relaxed text-muted">{feature.description}</p>
        {allowed ? <Link href={feature.href} className="mt-4 flex min-h-11 items-center justify-between border-t border-line pt-2 text-caption font-semibold text-accent hover:underline focus-visible:outline-2 focus-visible:outline-accent">
          {feature.kind === "preview" ? "Explore workflow" : "Open workspace"}<Icon name="caret-right" className="size-4" />
        </Link> : <p className="mt-4 border-t border-line pt-4 text-caption text-muted">Access depends on your assigned role.</p>}
      </article>
    );
  }
  return (
    <div className="mt-7">
      <div className="border border-line bg-surface p-4 sm:p-5">
        <div className="flex flex-col gap-3 sm:flex-row">
          <div className="relative flex-1">
            <Icon name="magnifying-glass" className="pointer-events-none absolute left-3 top-3.5 size-4 text-muted" />
            <input aria-label="Search all features" type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search agents, models, audit, voice, fraud…" className="h-11 w-full border border-line bg-canvas pl-10 pr-3 text-body text-ink placeholder:text-muted focus-visible:outline-2 focus-visible:outline-accent" />
          </div>
          <select aria-label="Feature availability" value={kind} onChange={(event) => setKind(event.target.value)} className="min-h-11 border border-line bg-canvas px-3 text-body text-ink">
            <option value="all">All capabilities</option>
            {Object.entries(CAPABILITY_KIND_LABELS).map(([value, title]) => <option key={value} value={value}>{title}</option>)}
          </select>
        </div>
        <div className="mt-4 flex flex-wrap gap-2" aria-label="Filter by workspace">
          {[{ id: "all", title: "All" }, ...CAPABILITY_GROUPS].map((item) => <Button key={item.id} aria-pressed={group === item.id} variant={group === item.id ? "primary" : "ghost"} onClick={() => setGroup(item.id)} className="min-h-11 text-caption">{item.title}</Button>)}
        </div>
      </div>
      <div className="my-4 flex flex-wrap items-center justify-between gap-2">
        <p role="status" className="text-caption text-muted">{filtered.length} of {CAPABILITIES.length} capabilities</p>
        <Button onClick={reset} className="text-caption">Reset filters</Button>
      </div>
      <p className="mb-6 max-w-3xl text-caption leading-relaxed text-muted">Workspaces open existing AIDTRACE tools. Integrations show their current connection state. Workflow previews describe capabilities still being built; they do not execute investigations or responses.</p>
      {filtered.length === 0 ? <div className="border border-line bg-surface-2 p-8 text-center"><h2 className="text-title font-semibold">No matching features</h2><p className="mt-2 text-body text-muted">Try another term or reset the filters.</p></div> : CAPABILITY_GROUPS.map((section) => {
        const items = filtered.filter((feature) => feature.group === section.id);
        return items.length > 0 && <section key={section.id} aria-labelledby={`group-${section.id}`} className="mb-8">
          <div className="mb-3 flex items-center gap-3"><Icon name={section.icon} className="size-5 text-accent" /><h2 id={`group-${section.id}`} className="text-title font-semibold text-ink">{section.title}</h2><span className="text-caption text-muted">{items.length}</span></div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{items.map(card)}</div>
        </section>;
      })}
    </div>
  );
}
