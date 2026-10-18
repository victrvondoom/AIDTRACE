"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { Button, ButtonLink, PageHeader, StatusBadge } from "@/components/ui";
import {
  getSourceLedger, getSourceReadme, getSourceRepos, getSourceSummary, getLabAlgorithms,
  type SourceReadme, type SourceRepo, type SourceStage,
} from "@/lib/lab-api";
import { useFetch } from "@/lib/use-fetch";

const STAGE_TONE: Record<SourceStage, "verified" | "info" | "neutral" | "caution"> = {
  README_READ: "neutral", FEATURE_DESIGNED: "info", SOURCE_AUDITED: "info", INTEGRATED: "verified", TESTED: "verified", BROWSER_VERIFIED: "verified", BLOCKED: "caution",
};
const stageLabel = (s: string) => s.replace(/_/g, " ").toLowerCase();

export function SourceLibrary() {
  return <Suspense fallback={null}><SourcesInner /></Suspense>;
}

function SourcesInner() {
  const search = useSearchParams();
  const [q, setQ] = useState(search.get("q") ?? "");
  const [dq, setDq] = useState(q.trim());
  const [family, setFamily] = useState("");
  const [stage, setStage] = useState("");
  const [engine, setEngine] = useState(search.get("engine") ?? "");
  const [open, setOpen] = useState<SourceRepo | null>(null);
  const [readme, setReadme] = useState<SourceReadme | null>(null);
  const readmeRequest = useRef(0);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [readmeError, setReadmeError] = useState<string | null>(null);
  const summary = useFetch(getSourceSummary);
  const engines = useFetch(getLabAlgorithms);
  const repos = useFetch(() => getSourceRepos({ family, stage, engine, q: dq }), [family, stage, engine, dq]);

  useEffect(() => { const t = setTimeout(() => setDq(q.trim()), 250); return () => clearTimeout(t); }, [q]);

  useEffect(() => () => { readmeRequest.current += 1; }, []);

  async function view(repo: SourceRepo) {
    const request = ++readmeRequest.current;
    setOpen(repo); setReadme(null); setReadmeError(null);
    if (!repo.readme.present) return;
    try { const { data } = await getSourceReadme(repo.slug); if (request === readmeRequest.current) setReadme(data); }
    catch (e) { if (request === readmeRequest.current) setReadmeError(e instanceof Error ? e.message : "The README could not be loaded."); }
  }
  async function downloadLedger() {
    setDownloading(true); setDownloadError(null);
    try {
    const { data } = await getSourceLedger();
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
    Object.assign(document.createElement("a"), { href: url, download: "graphhacks98-capability-ledger.json" }).click();
    URL.revokeObjectURL(url);
    } catch (e) { setDownloadError(e instanceof Error ? e.message : "The ledger could not be downloaded."); }
    finally { setDownloading(false); }
  }

  const s = summary.status === "live" ? summary.data : null;
  const items = repos.status === "live" ? repos.data.items : [];
  const maxFamily = Math.max(...Object.values(s?.by_family ?? { x: 1 }));

  return (
    <div className="mx-auto max-w-[1400px]">
      <PageHeader title="Source Library" lede="Every one of the 98 research repositories, its README exactly as collected, and an honest ledger of what AIDTRACE has actually built from it. README text is third-party and untrusted: it is shown as plain text and never executed."
        actions={<><Button variant="ghost" disabled={downloading} onClick={() => void downloadLedger()}>{downloading ? "Downloading?" : "Download ledger JSON"}</Button><ButtonLink href="/graph-lab">Open Graph Lab</ButtonLink></>} />

      {downloadError && <p role="alert">{downloadError}</p>}
      {[summary, engines].map((state, index) => state.status === "error" && <p key={index} role="alert">{state.error.message} <Button onClick={state.retry}>Retry</Button></p>)}
      {s && (
        <section aria-label="Library summary" className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {[["Repositories", s.repositories], ["READMEs collected", `${s.readme_present} of ${s.repositories}`], ["Engines built", s.engines], ["Repos mapped to an engine", s.integrated_repositories]].map(([k, v]) => (
            <div key={String(k)} className="border border-line bg-surface p-4"><p className="text-caption text-muted">{k}</p><p className="mt-1 text-title font-semibold">{v}</p></div>
          ))}
        </section>
      )}
      {s && (
        <section className="mt-4 grid gap-4 lg:grid-cols-2" aria-label="Breakdown">
          <div className="border border-line bg-surface p-4">
            <h2 className="text-body font-semibold">By capability family</h2>
            <ul className="mt-3 space-y-1.5">{Object.entries(s.by_family).map(([f, n]) => (
              <li key={f}><button type="button" onClick={() => setFamily(family === f ? "" : f)} aria-pressed={family === f} className={`grid w-full grid-cols-[minmax(0,14rem)_1fr_2rem] items-center gap-3 text-left text-caption ${family === f ? "font-semibold" : ""}`}>
                <span className="truncate">{f}</span><span className="h-2.5 bg-surface-2"><span className="block h-full" style={{ width: `${(n / maxFamily) * 100}%`, background: "var(--info)" }} /></span><span className="text-right text-muted">{n}</span></button></li>
            ))}</ul>
          </div>
          <div className="border border-line bg-surface p-4">
            <h2 className="text-body font-semibold">Highest evidenced stage</h2>
            <ul className="mt-3 flex flex-wrap gap-2">{[...s.stages, "BLOCKED" as SourceStage].filter((st) => s.by_stage[st]).map((st) => (
              <li key={st}><button type="button" onClick={() => setStage(stage === st ? "" : st)} aria-pressed={stage === st} className={`min-h-11 border px-3 text-caption ${stage === st ? "border-ink bg-surface-2" : "border-line"}`}>{stageLabel(st)} <strong>{s.by_stage[st]}</strong></button></li>
            ))}</ul>
            <p className="mt-3 text-micro leading-relaxed text-muted">A stage is claimed only with evidence: <em>integrated</em> means an engine implements the mechanism the README describes (clean-room; no third-party code copied), <em>tested</em> means that engine has automated tests, and <em>browser verified</em> appears only after a real browser check. {s.untrusted_notice}</p>
          </div>
        </section>
      )}

      <section className="mt-4 flex flex-wrap items-end gap-3" aria-label="Filters">
        <label className="min-w-[220px] flex-1 text-caption">Search<input type="search" className="mt-1 min-h-11 w-full border border-line bg-surface px-2" placeholder="repository, project or mechanism" value={q} onChange={(e) => setQ(e.target.value)} /></label>
        <label className="text-caption">Engine
          <select className="mt-1 min-h-11 border border-line bg-surface px-2" value={engine} onChange={(e) => setEngine(e.target.value)}>
            <option value="">Any</option>{(engines.status === "live" ? engines.data.algorithms : []).map((a) => <option key={a.id} value={a.id}>{a.title}</option>)}
          </select></label>
        {(family || stage || engine || q) && <Button variant="ghost" onClick={() => { setFamily(""); setStage(""); setEngine(""); setQ(""); }}>Clear filters</Button>}
        <p className="pb-3 text-caption text-muted" role="status">{repos.status === "live" ? `${repos.data.total} repositories` : repos.status === "loading" ? "Loading…" : "Could not load"}</p>
      </section>
      {repos.status === "error" && <p role="alert" className="mt-3 border-l-2 border-danger pl-3 text-caption text-danger">{repos.error.message} <Button variant="ghost" onClick={repos.retry}>Retry</Button></p>}

      <div className={`mt-3 grid gap-4 ${open ? "lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]" : ""}`}>
        <ul className="space-y-2" aria-label="Repositories">
          {items.map((r) => (
            <li key={r.slug} className={`border bg-surface p-4 ${open?.slug === r.slug ? "border-ink" : "border-line"}`}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <a href={r.url} target="_blank" rel="noopener noreferrer" className="break-all text-body font-semibold underline-offset-2 hover:underline">{r.repo}</a>
                  <p className="text-micro text-muted">{r.family} · license: {r.license_status.toLowerCase().replace(/_/g, " ")}</p>
                </div>
                <StatusBadge tone={STAGE_TONE[r.stage]}>{stageLabel(r.stage)}</StatusBadge>
              </div>
              <p className="mt-2 text-caption leading-relaxed">{r.summary}</p>
              <p className="mt-1 text-micro leading-relaxed text-muted">{r.note}</p>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Button variant="ghost" onClick={() => void view(r)} aria-pressed={open?.slug === r.slug}>{r.readme.present ? `README (${Math.max(1, Math.round(r.readme.bytes / 1024))} KB)` : "No README"}</Button>
                {r.engines.map((id) => <Link key={id} href="/hub" className="border border-line px-2 py-1 text-micro hover:bg-surface-2">{(engines.status === "live" && engines.data.algorithms.find((a) => a.id === id)?.title) || id}</Link>)}
              </div>
            </li>
          ))}
          {repos.status === "live" && items.length === 0 && <li className="border border-dashed border-line p-8 text-center text-caption text-muted">No repositories match these filters.</li>}
        </ul>

        {open && (
          <aside className="self-start border border-line bg-surface lg:sticky lg:top-4" aria-label={`README of ${open.repo}`}>
            <div className="flex items-start justify-between gap-3 border-b border-line p-3">
              <div className="min-w-0"><h2 className="break-all text-body font-semibold">{open.repo}</h2>
                {readme && <p className="font-mono text-micro text-muted">{readme.bytes.toLocaleString()} bytes · sha256 {readme.sha256.slice(0, 12)}…{readme.truncated ? " · truncated" : ""}</p>}</div>
              <Button variant="ghost" onClick={() => { readmeRequest.current += 1; setOpen(null); setReadme(null); }}>Close</Button>
            </div>
            <p className="border-b border-line bg-surface-2 p-3 text-micro text-muted">Third-party text, shown verbatim as plain text. Nothing in it is executed or followed.</p>
            {!open.readme.present && <p className="p-4 text-caption text-muted">{open.blocked_reason}</p>}
            {readmeError && <p role="alert" className="p-4 text-caption text-danger">{readmeError}</p>}
            {open.readme.present && !readme && !readmeError && <p role="status" className="p-4 text-caption text-muted">Loading README…</p>}
            {readme && <pre className="max-h-[70vh] overflow-auto whitespace-pre-wrap break-words p-4 font-mono text-micro leading-relaxed">{readme.text}</pre>}
          </aside>
        )}
      </div>
    </div>
  );
}
