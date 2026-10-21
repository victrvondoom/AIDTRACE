"use client";

import { useMemo, useState } from "react";
import { VoiceRecorder } from "@/components/voice-recorder";
import { useLiveQuery } from "@/lib/use-live-query";
import { engineeringMemoryRules, engineeringMemorySnapshot, saveEngineeringMemory, transcribeEngineeringMemory } from "@/lib/lab-api";

function download(name: string, contents: string, type: string) {
  const url = URL.createObjectURL(new Blob([contents], { type }));
  const anchor = document.createElement("a");
  anchor.href = url; anchor.download = name; anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

const MEMORY_PAGE_SIZE = 50;

export function EngineeringMemoryPanel() {
  const vault = useLiveQuery(engineeringMemorySnapshot);
  const [text, setText] = useState("");
  const [title, setTitle] = useState("");
  const [tags, setTags] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [memorySearch, setMemorySearch] = useState("");
  const [memoryPage, setMemoryPage] = useState(0);
  const [exports, setExports] = useState<{ rules: string; mcp_config: Record<string, unknown>; active_memories: number } | null>(null);
  const filteredMemories = useMemo(() => {
    const query = memorySearch.trim().toLocaleLowerCase();
    return [...(vault.data?.memories ?? [])]
      .sort((a, b) => (b.recorded_at ?? "").localeCompare(a.recorded_at ?? ""))
      .filter((memory) => !query || [memory.summary, memory.text, ...(memory.tags ?? [])]
        .some((value) => String(value).toLocaleLowerCase().includes(query)));
  }, [vault.data?.memories, memorySearch]);
  const memoryPageCount = Math.max(1, Math.ceil(filteredMemories.length / MEMORY_PAGE_SIZE));
  const currentMemoryPage = Math.min(memoryPage, memoryPageCount - 1);
  const visibleMemories = filteredMemories.slice(
    currentMemoryPage * MEMORY_PAGE_SIZE,
    (currentMemoryPage + 1) * MEMORY_PAGE_SIZE,
  );

  async function transcribe(audio: Blob) {
    setBusy("transcribe"); setError(""); setNotice("");
    try {
      const result = await transcribeEngineeringMemory(audio);
      setText((current) => [current, result.text].filter(Boolean).join("\n"));
      setNotice(`Transcript ready in ${result.language}; review and edit it before saving.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Transcription failed. Your recording was not saved.");
    } finally { setBusy(""); }
  }

  async function save() {
    setBusy("save"); setError(""); setNotice("");
    try {
      await saveEngineeringMemory({ text: text.trim(), title: title.trim() || "Engineering judgment", tags: tags.split(",").map((tag) => tag.trim()).filter(Boolean).slice(0, 8) });
      setText(""); setTitle(""); setTags(""); setNotice("Saved to the separate site-shared engineering vault. Available to connected agents on their next recall.");
      await vault.refresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "The judgment could not be saved."); }
    finally { setBusy(""); }
  }

  async function exportRules() {
    setBusy("export"); setError("");
    try {
      const result = await engineeringMemoryRules();
      setExports(result);
      setNotice(`Exported fail-closed rules with ${result.active_memories} active judgment(s), plus the MCP client configuration.`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Rules export failed."); }
    finally { setBusy(""); }
  }

  return <section className="space-y-5 border border-accent/35 bg-surface p-5 sm:p-7" aria-labelledby="engineering-memory-heading">
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="max-w-3xl">
        <p className="text-micro font-bold uppercase tracking-[0.16em] text-accent">Persistent · site-shared · graph-isolated</p>
        <h2 id="engineering-memory-heading" className="mt-2 text-2xl font-semibold">Teach your AI once. It never forgets.</h2>
        <p className="mt-2 text-caption leading-relaxed text-muted">Dictate the engineering judgment your agent cannot infer from code. It lives in a dedicated persistent FalkorDB graph for this site, separate from operational evidence, and is recalled through a read-only MCP server. Human review keeps transcription and saved guidance under your control.</p>
      </div>
      <button type="button" disabled={busy !== ""} onClick={() => void exportRules()} className="min-h-11 border border-accent bg-accent px-4 py-2 text-caption font-semibold text-on-accent disabled:opacity-50">{busy === "export" ? "Preparing exports…" : "Export agent rules + MCP"}</button>
    </div>

    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(300px,0.8fr)]">
      <div className="space-y-3 border border-line bg-canvas p-4">
        <h3 className="text-sm font-semibold">Capture a judgment</h3>
        <p className="text-micro leading-relaxed text-muted">Examples: “Keep the Kairos product identity and update the native route”; “Never turn UNKNOWN evidence into a negative”; “Run the package’s own checks before reporting completion.”</p>
        <div className="flex justify-center border-y border-line py-4"><VoiceRecorder onBlob={(audio) => void transcribe(audio)} disabled={busy !== ""} /></div>
        <label className="block text-caption">Title<input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={120} className="mt-1 min-h-10 w-full border border-line bg-surface px-3" placeholder="e.g. Preserve Kairos product identity" /></label>
        <label className="block text-caption">Judgment<textarea value={text} onChange={(event) => setText(event.target.value.slice(0, 4000))} rows={5} maxLength={4000} className="mt-1 w-full border border-line bg-surface px-3 py-2" placeholder="Speak into the recorder or write the exact engineering judgment…" /></label>
        <label className="block text-caption">Tags<input value={tags} onChange={(event) => setTags(event.target.value)} className="mt-1 min-h-10 w-full border border-line bg-surface px-3" placeholder="voice, architecture, verification" /></label>
        <div className="flex flex-wrap items-center justify-between gap-3"><span className="text-micro text-muted">{text.length}/4000 · transcript is editable before saving</span><button type="button" disabled={busy !== "" || text.trim().length < 12} onClick={() => void save()} className="min-h-10 bg-ink px-4 text-caption font-semibold text-surface disabled:opacity-40">{busy === "save" ? "Saving…" : "Save to engineering memory"}</button></div>
        {notice && <p role="status" className="border-l-2 border-positive bg-positive/5 p-2 text-caption text-positive">{notice}</p>}
        {error && <p role="alert" className="border-l-2 border-danger bg-danger/5 p-2 text-caption text-danger">{error}</p>}
        {exports && <div className="flex flex-wrap gap-2 border-t border-line pt-3"><button type="button" onClick={() => download("AGENTS.md", exports.rules, "text/markdown;charset=utf-8")} className="min-h-10 border border-line bg-surface px-3 text-caption font-medium">Download AGENTS.md</button><button type="button" onClick={() => download("kairos-engineering-memory.mcp.json", JSON.stringify(exports.mcp_config, null, 2), "application/json")} className="min-h-10 border border-line bg-surface px-3 text-caption font-medium">Download MCP configuration</button></div>}
      </div>

      <div className="space-y-3">
        <div className="border border-line bg-canvas p-4">
          <div className="flex items-center justify-between gap-2"><h3 className="text-sm font-semibold">Memory in the sandbox</h3><button type="button" disabled={vault.refreshing} onClick={() => void vault.refresh()} className="text-micro text-muted underline">Refresh</button></div>
          <p className="mt-1 text-micro leading-relaxed text-muted">Dedicated graph for this authenticated site in the configured FalkorDB instance. All connected coding agents share these judgments; supplier and site evidence memory stays in its own graph.</p>
          {vault.data && <div role="status" className="mt-3 flex flex-wrap items-center gap-2 border-y border-line py-2 text-micro"><span className={`border px-2 py-1 font-semibold ${vault.data.complete ? "border-positive/30 text-positive" : "border-danger/30 text-danger"}`}>{vault.data.complete ? "Complete vault scan" : "Incomplete vault scan"}</span><span className="text-muted">{vault.data.total_memories_scanned} graph records scanned</span><span className="text-muted">{vault.data.memories.length} engineering judgments</span></div>}
          {vault.error ? <p role="alert" className="mt-3 text-caption text-danger">Vault unavailable: {vault.error}</p> : !vault.data ? <p role="status" className="mt-3 text-caption text-muted">Checking the persistent memory vault…</p> : vault.data.memories.length === 0 ? <p className="mt-3 border border-dashed border-line p-4 text-caption text-muted">No engineering judgments saved yet.</p> : <div className="mt-3 space-y-3">
            <label className="block text-caption">Search saved judgments<input value={memorySearch} onChange={(event) => { setMemorySearch(event.target.value.slice(0, 120)); setMemoryPage(0); }} maxLength={120} className="mt-1 min-h-10 w-full border border-line bg-surface px-3" placeholder="Search titles, text, and tags" /></label>
            {filteredMemories.length === 0 ? <p role="status" className="border border-dashed border-line p-4 text-caption text-muted">No judgments match this search.</p> : <>
              <p className="text-micro text-muted">Showing {currentMemoryPage * MEMORY_PAGE_SIZE + 1}–{Math.min((currentMemoryPage + 1) * MEMORY_PAGE_SIZE, filteredMemories.length)} of {filteredMemories.length} judgments.</p>
              <ul className="max-h-[460px] space-y-2 overflow-y-auto">{visibleMemories.map((memory) => <li key={memory.id} className="border border-line bg-surface p-3"><div className="flex items-start justify-between gap-2"><strong className="text-caption">{memory.summary}</strong><span className={`shrink-0 text-micro ${memory.status === "VALID" ? "text-positive" : "text-caution"}`}>{memory.status}</span></div><p className="mt-2 whitespace-pre-wrap text-caption leading-relaxed">{memory.text}</p><div className="mt-2 flex flex-wrap gap-1">{memory.tags?.map((tag) => <span key={tag} className="border border-line px-1.5 py-0.5 text-[10px] text-muted">{tag}</span>)}</div><p className="mt-2 font-mono text-[10px] text-muted">Human-authored · {new Date(memory.recorded_at).toLocaleString()}</p></li>)}</ul>
              {memoryPageCount > 1 && <nav aria-label="Engineering memory pages" className="flex items-center justify-between gap-3 border-t border-line pt-3"><button type="button" disabled={currentMemoryPage === 0} onClick={() => setMemoryPage(currentMemoryPage - 1)} className="min-h-10 border border-line px-3 text-caption disabled:opacity-40">Previous</button><span aria-live="polite" className="text-micro text-muted">Page {currentMemoryPage + 1} of {memoryPageCount}</span><button type="button" disabled={currentMemoryPage + 1 >= memoryPageCount} onClick={() => setMemoryPage(currentMemoryPage + 1)} className="min-h-10 border border-line px-3 text-caption disabled:opacity-40">Next</button></nav>}
            </>}
          </div>}
        </div>
        <div className="border border-caution/25 bg-caution/5 p-4 text-caption leading-relaxed text-muted"><strong className="text-caution">A memory can still be unavailable.</strong> The exported `AGENTS.md` tells connected agents to halt and report `ENGINEERING_MEMORY_UNAVAILABLE` if MCP recall fails. This makes the failure visible and reviewable; it cannot guarantee that an agent runtime follows its instructions.</div>
      </div>
    </div>
  </section>;
}
