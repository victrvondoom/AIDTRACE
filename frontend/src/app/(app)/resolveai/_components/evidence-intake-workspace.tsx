"use client";

import { useCallback, useState } from "react";
import { Button } from "@/components/ui";
import {
  importEvidence, memorySnapshot, previewEvidenceImport,
  type EvidenceImportPreview, type EvidenceIntakeRequest, type EvidenceImportResult,
} from "@/lib/lab-api";
import { useLiveQuery } from "@/lib/use-live-query";

type ClaimDraft = { key: string; value: string };
type Draft = { title: string; version: string; content: string; supersedes: string; verified: boolean; claims: ClaimDraft[] };
const EMPTY: Draft = { title: "", version: "v1", content: "", supersedes: "", verified: false, claims: [{ key: "", value: "" }] };

function parseFactValue(value: string): string | number | boolean {
  const clean = value.trim();
  if (clean.toLowerCase() === "true") return true;
  if (clean.toLowerCase() === "false") return false;
  if (clean !== "" && Number.isFinite(Number(clean))) return Number(clean);
  return value;
}

export function EvidenceIntakeWorkspace() {
  const query = useCallback(() => memorySnapshot(), []);
  const state = useLiveQuery(query);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [requestId, setRequestId] = useState("");
  const [preview, setPreview] = useState<EvidenceImportPreview | null>(null);
  const [result, setResult] = useState<EvidenceImportResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function edit(update: (current: Draft) => Draft) {
    setDraft(update);
    setRequestId(crypto.randomUUID());
    setPreview(null);
    setResult(null);
    setError("");
  }

  function bodyFor(id: string, reviewed?: EvidenceImportPreview): EvidenceIntakeRequest {
    const body: EvidenceIntakeRequest = {
      request_id: id, title: draft.title.trim(), version_label: draft.version.trim(), content: draft.content,
      claims: draft.claims.map((claim) => ({ fact_key: claim.key.trim(), fact_value: parseFactValue(claim.value) })),
      human_verified: draft.verified,
    };
    if (draft.supersedes) body.supersedes_source_id = draft.supersedes;
    if (reviewed?.expected_source_hash) body.expected_source_hash = reviewed.expected_source_hash;
    if (reviewed?.expected_source_revision) body.expected_source_revision = reviewed.expected_source_revision;
    return body;
  }

  async function runPreview() {
    const id = requestId || crypto.randomUUID();
    setRequestId(id); setBusy(true); setError(""); setResult(null); setPreview(null);
    try { setPreview(await previewEvidenceImport(bodyFor(id))); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "The source could not be previewed."); }
    finally { setBusy(false); }
  }

  async function commit() {
    if (!preview || preview.verdict === "REJECT") return;
    setBusy(true); setError("");
    try {
      const saved = await importEvidence(bodyFor(preview.request_id, preview));
      setResult(saved);
      await state.refresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The source could not be imported."); }
    finally { setBusy(false); }
  }

  async function loadFile(file?: File) {
    if (!file) return;
    if (file.size > 20_000) { setError("Text files must be 20 KB or smaller."); return; }
    try {
      const content = await file.text();
      edit((current) => ({ ...current, title: current.title || file.name.replace(/\.[^.]+$/, ""), content }));
    } catch { setError("The selected file could not be read."); }
  }

  const sources = state.data?.sources ?? [];
  const ready = draft.title.trim().length > 0 && draft.version.trim().length > 0 && draft.content.trim().length > 0 &&
    draft.claims.length > 0 && draft.claims.every((claim) => claim.key.trim() && claim.value.trim());

  return (
    <section aria-labelledby="evidence-intake-title" className="border border-line bg-surface p-5 sm:p-7">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-micro font-bold uppercase tracking-[0.14em] text-accent">Site graph · live evidence</p>
          <h2 id="evidence-intake-title" className="mt-2 text-title font-semibold">Add and review a source version</h2>
          <p className="mt-2 max-w-3xl text-caption leading-relaxed text-muted">Import text evidence into the signed-in site graph. Preview the dependency impact before replacing a source. New manual evidence gets the weakest authority level; confidence is set only to the intake gate and is not measured. Mark it verified only after a person has checked it.</p>
        </div>
        <div className="flex items-center gap-2 text-micro text-muted" role="status">
          <span className={`size-2 rounded-full ${state.error ? "bg-danger" : state.data ? "bg-positive" : "bg-caution"}`} />
          {state.error ? "Graph refresh failed" : state.refreshing ? "Refreshing site graph" : state.data ? `Updated ${state.updatedAt ? new Date(state.updatedAt).toLocaleTimeString() : "just now"}` : "Connecting to site graph"}
          <button type="button" onClick={() => void state.refresh()} disabled={state.refreshing} className="ml-1 underline underline-offset-2 disabled:opacity-50">Refresh</button>
        </div>
      </div>

      {state.error && <p role="alert" className="mt-4 border-l-2 border-danger pl-3 text-caption text-danger">Could not read the current source list: {state.error}. Preview or import will still be checked by the API.</p>}

      <form className="mt-6 grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(280px,.7fr)]" onSubmit={(event) => { event.preventDefault(); void runPreview(); }}>
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="text-caption font-medium">Source title<input required maxLength={200} value={draft.title} onChange={(event) => edit((current) => ({ ...current, title: event.target.value }))} className="mt-1 block h-10 w-full border border-line bg-canvas px-3 font-normal" placeholder="Supplier audit report" /></label>
            <label className="text-caption font-medium">Version label<input required maxLength={80} value={draft.version} onChange={(event) => edit((current) => ({ ...current, version: event.target.value }))} className="mt-1 block h-10 w-full border border-line bg-canvas px-3 font-normal" placeholder="v1" /></label>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <label className="text-caption font-medium">Evidence text<textarea required maxLength={20_000} rows={7} value={draft.content} onChange={(event) => edit((current) => ({ ...current, content: event.target.value }))} className="mt-1 block w-full resize-y border border-line bg-canvas px-3 py-2 font-normal" placeholder="Paste the relevant source text here. This text is saved with the source and its SHA-256 digest." /></label>
            <label className="inline-flex min-h-10 cursor-pointer items-center border border-line px-3 text-caption font-medium hover:border-accent">Load .txt or .md<input type="file" accept=".txt,.md,.csv,text/plain,text/markdown,text/csv" className="sr-only" onChange={(event) => void loadFile(event.target.files?.[0])} /></label>
            <span className="ml-auto text-micro text-muted">{draft.content.length.toLocaleString()} / 20,000 characters</span>
          </div>
          <fieldset className="space-y-2">
            <legend className="text-caption font-semibold">Claims linked to this source</legend>
            {draft.claims.map((claim, index) => <div key={index} className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
              <label className="sr-only" htmlFor={`claim-key-${index}`}>Claim key</label><input id={`claim-key-${index}`} required maxLength={200} value={claim.key} onChange={(event) => edit((current) => ({ ...current, claims: current.claims.map((item, i) => i === index ? { ...item, key: event.target.value } : item) }))} className="h-10 min-w-0 border border-line bg-canvas px-3 text-caption" placeholder="supplier.audit.valid_until" />
              <label className="sr-only" htmlFor={`claim-value-${index}`}>Claim value</label><input id={`claim-value-${index}`} required value={claim.value} onChange={(event) => edit((current) => ({ ...current, claims: current.claims.map((item, i) => i === index ? { ...item, value: event.target.value } : item) }))} className="h-10 min-w-0 border border-line bg-canvas px-3 text-caption" placeholder="2027-04-30, true, or 90" />
              <button type="button" disabled={draft.claims.length === 1} onClick={() => edit((current) => ({ ...current, claims: current.claims.filter((_, i) => i !== index) }))} className="min-h-10 border border-line px-3 text-caption text-muted disabled:opacity-40" aria-label={`Remove claim ${index + 1}`}>Remove</button>
            </div>)}
            <button type="button" onClick={() => edit((current) => ({ ...current, claims: [...current.claims, { key: "", value: "" }] }))} className="min-h-10 text-caption font-semibold text-accent underline underline-offset-4">Add another claim</button>
          </fieldset>
          <label className="flex items-start gap-3 border border-caution/30 bg-caution/5 p-3 text-caption leading-relaxed text-muted">
            <input type="checkbox" checked={draft.verified} onChange={(event) => edit((current) => ({ ...current, verified: event.target.checked }))} className="mt-1 size-4 accent-[var(--color-accent)]" />
            <span><strong className="font-semibold text-caution">A human has reviewed this evidence.</strong> This records a human verification assertion. It does not raise the source above authority level 5.</span>
          </label>
        </div>

        <aside className="space-y-4">
          <label className="block text-caption font-medium">Existing source to supersede (optional)
            <select value={draft.supersedes} onChange={(event) => edit((current) => ({ ...current, supersedes: event.target.value }))} className="mt-1 h-10 w-full border border-line bg-canvas px-3 font-normal">
              <option value="">Import as a new source</option>
              {sources.filter((source) => source.status === "ACTIVE").map((source) => <option key={source.id} value={source.id}>{source.title} · {source.version_label} · authority {source.authority_level}</option>)}
            </select>
          </label>
          {draft.supersedes && <p className="border-l-2 border-caution pl-3 text-micro leading-relaxed text-muted">Replacing a source requires a current impact preview. Unverified or lower authority evidence can be recorded as a contest, but will leave the existing source and dependent decisions intact.</p>}
          <div className="flex flex-wrap gap-2">
            <Button type="submit" variant="primary" disabled={!ready || busy}>{busy && !preview ? "Checking impact…" : "Preview source and impact"}</Button>
            <Button type="button" variant="ghost" disabled={!preview || preview.verdict === "REJECT" || busy} onClick={() => void commit()}>{busy && preview ? "Importing…" : "Import reviewed source"}</Button>
          </div>
          {preview && <section aria-live="polite" className="border border-line bg-canvas p-4">
            <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="text-sm font-semibold">Preview result</h3><span className={`border px-2 py-1 font-mono text-micro ${preview.verdict === "REPLACE" ? "border-positive/30 text-positive" : preview.verdict === "REJECT" ? "border-danger/30 text-danger" : "border-caution/30 text-caution"}`}>{preview.verdict}</span></div>
            <p className="mt-2 text-caption leading-relaxed text-muted">{preview.verdict === "REPLACE" ? `This verified source can replace the selected version. ${preview.impact?.would_mark_stale.length ?? 0} dependent record(s) may be invalidated.` : preview.verdict === "CONTEST" ? "This evidence has lower authority or verification than the selected source. It will be stored as a contest and will not invalidate the existing branch." : preview.verdict === "REJECT" ? "The selected source is no longer active or this evidence cannot be accepted." : "A new source and its claims will be added without changing existing decisions."}</p>
            <dl className="mt-3 space-y-1.5 break-all font-mono text-[10px] text-muted"><div>Source ID: {preview.source_id}</div><div>SHA-256: {preview.content_sha256}</div><div>Confidence {preview.confidence.toFixed(2)} · {preview.confidence_basis}</div>{preview.expected_source_revision && <div>Reviewed graph revision: {preview.expected_source_revision}</div>}</dl>
            {preview.impact?.would_mark_stale.length ? <ul className="mt-3 max-h-56 space-y-1 overflow-y-auto border-t border-line pt-3 text-caption">{preview.impact.would_mark_stale.map((item) => <li key={item.id} className="flex items-start justify-between gap-3"><span className="min-w-0 text-ink">{item.summary || item.id}<span className="block font-mono text-micro text-muted">{item.label} · {item.id}</span></span><span className="shrink-0 text-micro text-caution">{item.status}</span></li>)}</ul> : preview.impact && <p className="mt-3 border-t border-line pt-3 text-caption text-muted">No dependent records were found.</p>}
          </section>}
          {result && <section aria-live="polite" className="border border-positive/30 bg-positive/5 p-4">
            <h3 className="text-sm font-semibold text-positive">Source stored in this site graph</h3>
            <p className="mt-2 text-caption leading-relaxed text-muted">{result.note} {result.duplicate ? "This is the saved result of the same request." : ""} Verification: {result.verification_status}. The graph has been refreshed.</p>
            <dl className="mt-3 space-y-1.5 break-all font-mono text-[10px] text-muted"><div>Source: {result.source_id}</div><div>Memory: {result.memory_id}</div><div>Observed: {new Date(result.observed_at).toLocaleString()}</div></dl>
            {result.invalidated.length > 0 && <p className="mt-3 text-caption font-medium text-caution">{result.invalidated.length} dependent graph record(s) were invalidated and need a fresh review.</p>}
          </section>}
          {error && <p role="alert" className="border-l-2 border-danger pl-3 text-caption text-danger">{error} <button type="button" className="underline" onClick={() => void runPreview()}>Refresh preview and retry</button></p>}
          {state.data && sources.length === 0 && <p className="text-micro text-muted">No source versions are recorded in this site graph yet. You can still add the first source.</p>}
        </aside>
      </form>
    </section>
  );
}
