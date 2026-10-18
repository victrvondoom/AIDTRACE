import Link from "next/link";
import { Icon } from "@/components/icon";
import { getAnnotationStats, getFalkorHealth, getModelCatalog, getValidationCorpusStats } from "@/lib/api";
import type { HealthDetailed, ServiceHealth } from "@/lib/types";
import { useFetch } from "@/lib/use-fetch";

const AGENTS = [
  { name: "Investigation supervisor", purpose: "Routes work to the smallest relevant specialist team", href: "/rca", icon: "magnifying-glass", state: "Workflow entry" },
  { name: "Evidence extraction", purpose: "Extracts candidate facts for human review", href: "/documents", icon: "file-text", state: "Workflow entry" },
  { name: "Entity resolution", purpose: "Review asset identity and canonical records", href: "/assets", icon: "cube", state: "Kairos workflow" },
  { name: "Graph investigation", purpose: "Explore connected assets, documents, and events", href: "/graph", icon: "graph", state: "Kairos workflow" },
  { name: "Temporal reasoning", purpose: "Inspect when evidence became valid or changed", href: "/graph", icon: "clock-counter-clockwise", state: "Kairos workflow" },
  { name: "Evidence drift", purpose: "Trace conclusions affected by changed evidence", href: "/resolveai#memory", icon: "warning-circle", state: "Engine in progress" },
  { name: "Contradiction analyst", purpose: "Surface competing claims for resolution", href: "/governance/conflicts", icon: "warning-circle", state: "Kairos workflow" },
  { name: "Memory curator", purpose: "Review low-confidence knowledge before promotion", href: "/governance/quarantine", icon: "clipboard-text", state: "Human-led" },
  { name: "Action coordinator", purpose: "Prepare governed change and work-order decisions", href: "/governance/moc", icon: "scales", state: "Human-led" },
  { name: "Human review", purpose: "Keep material decisions under authorized approval", href: "/governance", icon: "shield-check", state: "Required" },
] as const;

function ServiceMark({ service, loading }: { service?: ServiceHealth; loading: boolean }) {
  const state = loading ? "Checking" : service?.status === "healthy" ? "Healthy" : service?.status === "degraded" ? "Degraded" : service?.status === "down" ? "Unavailable" : "Not reported";
  const tone = service?.status === "healthy" ? "bg-verified" : service?.status === "down" ? "bg-danger" : service?.status === "degraded" ? "bg-caution" : "bg-muted";
  return <span className="inline-flex items-center gap-2 text-caption text-muted"><span className={`size-2 rounded-full ${tone}`} aria-hidden="true" />{state}</span>;
}

export function ReasoningWorkspace({ health, loading }: { health: HealthDetailed | null; loading: boolean }) {
  const falkorState = useFetch(getFalkorHealth, [], 60000);
  const modelState = useFetch(getModelCatalog, [], 60000);
  const corpusState = useFetch(getValidationCorpusStats, [], 60000);
  const annotationState = useFetch(getAnnotationStats, [], 60000);
  const services = health?.services ?? [];
  const graph = services.find((item) => /neo4j|graph/i.test(item.name));
  const vector = services.find((item) => /qdrant/i.test(item.name));
  const catalog = modelState.status === "live" ? modelState.data : null;
  const corpus = corpusState.status === "live" ? corpusState.data : null;
  const annotations = annotationState.status === "live" ? annotationState.data : null;
  const falkorLabel = falkorState.status === "loading"
    ? "Checking"
    : falkorState.status === "error"
      ? "Check unavailable"
      : falkorState.data.reachable
        ? falkorState.data.site_graph_exists ? "Connected" : "Connected, no site graph yet"
        : "Unavailable";

  return (
    <section aria-labelledby="rds-heading" data-testid="overview-rds" className="mt-8 border-y border-line py-7">
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
        <div>
          <p className="text-micro font-bold uppercase tracking-[0.1em] text-muted">Kairos intelligence</p>
          <h2 id="rds-heading" className="mt-1 text-title font-semibold text-ink">Reasoning &amp; Decision System</h2>
          <p className="mt-1 max-w-3xl text-caption leading-relaxed text-muted">Investigative agents connect plant evidence to governed decisions. Each conclusion stays traceable to its sources and requires the right human approval.</p>
        </div>
        <Link href="/graph" className="inline-flex min-h-11 items-center gap-2 text-caption font-semibold text-accent hover:underline focus-visible:outline-2 focus-visible:outline-accent">
          Explore evidence graph <span aria-hidden="true">&rarr;</span>
        </Link>
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,3fr)_minmax(260px,2fr)]">
        <div id="agents" className="min-w-0 scroll-mt-6">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-2">
            <h3 className="text-label font-semibold text-ink">Agent map</h3>
            <span className="text-micro text-muted">Mapped to Kairos workflows. Agent runtime is not yet connected.</span>
          </div>
          <div className="grid gap-2 pt-2 sm:grid-cols-2 xl:grid-cols-3">
            {AGENTS.map((agent, index) => (
              <Link key={agent.name} href={agent.href} className="group flex min-h-[112px] items-start gap-3 border border-line bg-surface p-3 transition-colors hover:bg-surface-2 focus-visible:outline-2 focus-visible:outline-accent">
                <span className="grid size-9 shrink-0 place-items-center bg-surface-2 text-accent"><Icon name={agent.icon} className="size-[18px]" /></span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center justify-between gap-2 text-body font-semibold text-ink"><span>{agent.name}</span><span className="text-micro font-medium text-muted">0{index + 1}</span></span>
                  <span className="mt-1 block text-caption leading-relaxed text-muted">{agent.purpose}</span>
                  <span className="mt-2 inline-flex border border-line px-1.5 py-0.5 text-micro text-muted">{agent.state}</span>
                </span>
              </Link>
            ))}
          </div>
        </div>

        <div id="infrastructure" className="min-w-0 scroll-mt-6 border border-line bg-surface p-4">
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-label font-semibold text-ink">Reasoning infrastructure</h3>
            <Link href="/system-health" className="text-caption font-medium text-accent hover:underline">System health</Link>
          </div>
          <p className="mt-1 text-caption text-muted">Read-only checks refresh every minute while this tab is visible. Unavailable checks retry automatically.</p>
          <dl className="mt-4 divide-y divide-line">
            <div className="flex items-center justify-between gap-3 py-2"><dt className="text-caption text-ink">FalkorDB reasoning graph</dt><dd><span className="text-caption text-muted">{falkorLabel}</span></dd></div>
            <div className="flex items-center justify-between gap-3 py-2"><dt className="text-caption text-ink">Kairos knowledge graph</dt><dd><ServiceMark service={graph} loading={loading} /></dd></div>
            <div className="flex items-center justify-between gap-3 py-2"><dt className="text-caption text-ink">Evidence retrieval</dt><dd><ServiceMark service={vector} loading={loading} /></dd></div>
            <div className="flex items-center justify-between gap-3 py-2"><dt className="text-caption text-ink">Model registry</dt><dd><span className="text-caption text-muted">{modelState.status === "loading" ? "Loading" : modelState.status === "error" ? "Unavailable" : `${catalog?.models.filter((model) => model.configured).length ?? 0} configured roles`}</span></dd></div>
          </dl>
          {falkorState.status === "live" && falkorState.data.reachable && !falkorState.data.site_graph_exists && <p className="mt-3 border-l-2 border-caution pl-3 text-caption leading-relaxed text-muted">FalkorDB is reachable. This site graph is created only when the first governed reasoning record is written.</p>}
          {falkorState.status === "error" && <p className="mt-3 border-l-2 border-caution pl-3 text-caption leading-relaxed text-muted">FalkorDB status could not be fetched. Retry the read-only check or open system health.</p>}
        </div>
      </div>

      <div className="mt-5 grid gap-5 border-t border-line pt-5 xl:grid-cols-[minmax(0,3fr)_minmax(260px,2fr)]">
        <div id="curation" className="scroll-mt-6">
          <div>
            <h3 className="text-label font-semibold text-ink">Data curation with the team</h3>
            <p className="mt-1 text-caption text-muted">Human-reviewed labels and held documents prepare safer evidence and evaluation sets.</p>
          </div>
          <dl className="mt-3 grid grid-cols-3 divide-x divide-line border-y border-line bg-surface">
            <div className="min-w-0 px-3 py-3"><dt className="text-micro text-muted">Validation labels</dt><dd className="mt-1 text-body font-semibold text-ink">{corpusState.status === "loading" ? "…" : corpus ? corpus.total_corpus_size.toLocaleString() : "Unavailable"}</dd></div>
            <div className="min-w-0 px-3 py-3"><dt className="text-micro text-muted">Team annotations</dt><dd className="mt-1 text-body font-semibold text-ink">{annotationState.status === "loading" ? "…" : annotations ? annotations.total.toLocaleString() : "Unavailable"}</dd></div>
            <div className="min-w-0 px-3 py-3"><dt className="text-micro text-muted">Corrections, 7 days</dt><dd className="mt-1 text-body font-semibold text-ink">{annotationState.status === "loading" ? "…" : annotations ? annotations.corrections_this_week.toLocaleString() : "Unavailable"}</dd></div>
          </dl>
          {(corpusState.status === "error" || annotationState.status === "error") && <p className="mt-2 text-caption text-muted">One or more curation summaries are unavailable. Open the source workflow to retry.</p>}
          <div className="mt-3 flex flex-wrap gap-2">
            <Link href="/governance/quarantine" className="inline-flex min-h-11 items-center gap-2 border border-line px-3 text-caption font-medium text-ink hover:bg-surface-2">Review held evidence <span aria-hidden="true" className="text-accent">&rarr;</span></Link>
            <Link href="/governance/model-gate" className="inline-flex min-h-11 items-center gap-2 border border-line px-3 text-caption font-medium text-ink hover:bg-surface-2">Validation corpus <span aria-hidden="true" className="text-accent">&rarr;</span></Link>
            <Link href="/documents/ingest" className="inline-flex min-h-11 items-center gap-2 border border-line px-3 text-caption font-medium text-ink hover:bg-surface-2">Curate source documents <span aria-hidden="true" className="text-accent">&rarr;</span></Link>
          </div>
        </div>
        <div id="models" className="scroll-mt-6 border-l-2 border-accent pl-4">
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-label font-semibold text-ink">Models and evaluation</h3>
            <span className="bg-surface-2 px-2 py-1 text-micro font-semibold text-muted">{catalog ? "Configuration" : modelState.status === "loading" ? "Loading" : "Unavailable"}</span>
          </div>
          <div className="mt-2 max-h-56 overflow-y-auto border-y border-line">
            {catalog?.models.length ? catalog.models.map((model) => (
              <div key={`${model.role}:${model.provider}:${model.model}`} className="flex items-start justify-between gap-3 border-b border-line py-2 last:border-b-0">
                <div className="min-w-0"><p className="text-caption font-medium capitalize text-ink">{model.role.replace(/_/g, " ")}</p><p className="truncate text-micro text-muted" title={`${model.provider}, ${model.model}`}>{model.provider}, {model.model}</p></div>
                <span className="shrink-0 text-micro text-muted">{model.configured ? "Configured" : "Not configured"}</span>
              </div>
            )) : <p className="py-3 text-caption text-muted">{modelState.status === "loading" ? "Loading model configuration…" : modelState.status === "error" ? "Model catalog is unavailable." : "No model roles are registered."}</p>}
          </div>
          <div className="flex items-center justify-between gap-3 border-b border-line py-2"><span className="text-caption text-ink">Fine-tuned model registry</span><span className="text-caption text-muted">{catalog ? catalog.fine_tuning.status === "not_connected" ? "Not connected" : "Connected" : modelState.status === "loading" ? "Checking" : "Unavailable"}</span></div>
          <p className="mt-2 text-caption leading-relaxed text-muted">Kairos supports human-curated evaluation through its validation corpus and model gate. Training jobs and checkpoints are not available in this deployment.</p>
          <Link href="/governance/model-gate" className="mt-2 inline-flex min-h-11 items-center gap-2 text-caption font-semibold text-accent hover:underline">Open model evaluation <span aria-hidden="true">&rarr;</span></Link>
        </div>
      </div>
    </section>
  );
}
