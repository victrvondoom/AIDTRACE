"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Icon } from "@/components/icon";
import { agentChat, agentChatReadiness, memoryHandoffs, memorySnapshot, type AgentChatResponse, type AgentChatTurn } from "@/lib/lab-api";

import { useLiveQuery } from "@/lib/use-live-query";
import { EngineeringMemoryPanel } from "./engineering-memory-panel";

type ChatMessage = { id: number; role: "user" | "assistant"; content: string; response?: AgentChatResponse };
const STARTERS = [
  "What decisions and actions are currently in my site's graph?",
  "Show me recent agent handoffs and whether they are still usable.",
  "What would be affected if I revise a source?",
];

function responseText(result: AgentChatResponse): string {
  if (result.answer) return [result.answer.finding, result.answer.why, result.answer.next_step].filter(Boolean).join("\n\n");
  return result.message || `The agent returned ${result.status} without an answer.`;
}

export default function AgentSandboxPage() {
  const status = useLiveQuery(agentChatReadiness);
  const getHandoffs = useCallback(async () => (await memoryHandoffs()).handoffs ?? [], []);
  const getMemory = useCallback(async () => memorySnapshot(), []);
  const handoffState = useLiveQuery(getHandoffs);
  const memoryState = useLiveQuery(getMemory);
  const readiness = status.data;
  const statusError = status.error;
  const canChat = !statusError && Boolean(readiness?.ready || readiness?.graph_chat_available);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const sequence = useRef(0);
  const endRef = useRef<HTMLDivElement>(null);

  const request = useRef<AbortController | null>(null);
  const [lastQuestion, setLastQuestion] = useState("");
  const [copiedCitation, setCopiedCitation] = useState("");
  useEffect(() => () => { request.current?.abort(); request.current = null; }, []);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block: "end" }); }, [messages, busy]);

  async function send(prompt = input) {
    const question = prompt.trim();
    if (!question || question.length < 3 || question.length > 500 || busy || request.current || !canChat) return;
    const controller = new AbortController();
    request.current = controller;
    setLastQuestion(question);
    const priorHistory: AgentChatTurn[] = messages.slice(-6).map((message) => ({ role: message.role, content: message.content.slice(0, 500) }));
    const userMessage: ChatMessage = { id: sequence.current++, role: "user", content: question };
    setMessages((current) => [...current, userMessage]);
    setInput(""); setError(""); setBusy(true);
    try {
      const result = await agentChat(question, priorHistory, controller.signal);
      if (request.current !== controller) return;
      const reply: ChatMessage = { id: sequence.current++, role: "assistant", content: responseText(result), response: result };
      setMessages((current) => [...current, reply]);
    } catch (reason) {
      if (request.current === controller) setError(controller.signal.aborted ? "Stopped waiting for the reply. You can edit and retry your question." : reason instanceof Error ? reason.message : "The agent could not answer. Try again.");
    } finally {
      if (request.current === controller) { request.current = null; setBusy(false); }
    }
  }

  function stop() {
    const current = request.current;
    if (!current) return;
    current.abort(); request.current = null; setBusy(false);
    setError("Stopped waiting for the reply. Edit and retry your question.");
  }

  async function copyCitation(citation: string) {
    try { await navigator.clipboard.writeText(citation); setCopiedCitation(citation); window.setTimeout(() => setCopiedCitation(""), 1800); }
    catch { setError("Clipboard access is unavailable. Select the citation text to copy it."); }
  }

  return (
    <main className="mx-auto flex min-h-[calc(100dvh-120px)] w-full max-w-[1280px] flex-col gap-5">
      <header className="grid gap-5 border border-line bg-surface p-6 sm:p-8 lg:grid-cols-[1fr_auto] lg:items-end">
        <div>
          <p className="flex items-center gap-2 text-micro font-bold uppercase tracking-[0.16em] text-accent"><Icon name="sparkle" size={15} /> AIDTRACE · Safe test space</p>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">Agent Sandbox</h1>
          <p className="mt-3 max-w-2xl text-body leading-relaxed text-muted">Talk through questions about your current site’s evidence graph. The agent can inspect sources and explain its reasoning, while every tool in this sandbox is read-only.</p>
        </div>
        <div className="flex items-center gap-2 border border-positive/25 bg-positive/5 px-3 py-2 text-caption text-positive"><span className="size-2 rounded-full bg-positive" /> Read-only tools · no approvals or writes</div>
      </header>

      <EngineeringMemoryPanel />

      <div className="grid flex-1 gap-5 lg:grid-cols-[minmax(0,1fr)_290px]">
        <section aria-label="Agent conversation" className="flex min-h-[560px] flex-col border border-line bg-surface">
          <div className="flex items-center justify-between border-b border-line px-4 py-3 sm:px-5">
            <div><h2 className="text-sm font-semibold">AIDTRACE site agent</h2><p className="mt-0.5 text-micro text-muted">Current site · evidence-backed answers</p></div>
            <button type="button" onClick={() => { setMessages([]); setError(""); }} disabled={busy || messages.length === 0} className="border border-line px-3 py-1.5 text-caption text-muted hover:text-ink disabled:opacity-40">New chat</button>
          </div>

          <div className="flex-1 space-y-4 overflow-y-auto bg-canvas p-4 sm:p-6" aria-live="polite">
            {messages.length === 0 && <div className="mx-auto mt-8 max-w-xl text-center">
              <span className="mx-auto grid size-12 place-items-center rounded-full bg-accent-soft text-accent"><Icon name="chat-centered-text" size={22} /></span>
              <h3 className="mt-4 text-lg font-semibold">Start a grounded conversation</h3>
              <p className="mt-2 text-caption leading-relaxed text-muted">Ask about graph evidence, decision history, agent handoffs, or a source revision. Each message triggers a fresh, site-scoped investigation.</p>
              <div className="mt-5 flex flex-col gap-2">{STARTERS.map((starter) => <button key={starter} type="button" disabled={!canChat || busy} onClick={() => void send(starter)} className="border border-line bg-surface px-3 py-2.5 text-left text-caption text-muted transition-colors hover:border-accent hover:text-ink disabled:cursor-not-allowed disabled:opacity-50">{starter}</button>)}</div>
            </div>}
            {messages.map((message) => <article key={message.id} className={`max-w-[92%] ${message.role === "user" ? "ml-auto" : "mr-auto"}`}>
              <p className="mb-1 text-micro font-semibold uppercase tracking-wider text-muted">{message.role === "user" ? "You" : `Agent · ${message.response?.answered_by ?? "reply"}`}</p>
              <div className={`whitespace-pre-wrap border px-4 py-3 text-sm leading-relaxed ${message.role === "user" ? "border-accent bg-accent text-on-accent" : "border-line bg-surface text-ink"}`}>{message.content}</div>
              {message.response && <div className="mt-2 space-y-2">
                <p className="text-micro text-muted">{message.response.status} ? {message.response.model}</p>
                {message.response.evidence.length > 0 && <details className="border border-line bg-surface px-3 py-2 text-caption"><summary className="cursor-pointer">View returned evidence</summary><pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap break-words text-micro">{JSON.stringify(message.response.evidence, null, 2)}</pre></details>}
                {message.response.answer?.citations?.length ? <div className="flex flex-wrap gap-1.5" aria-label="Cited record identifiers">{message.response.answer.citations.map((citation) => <button type="button" key={citation} title="Copy evidence record ID" onClick={() => void copyCitation(citation)} className="border border-line bg-surface px-2 py-1 font-mono text-micro text-muted hover:border-accent">{copiedCitation === citation ? "Copied" : citation}</button>)}</div> : null}
                {message.response.tool_calls.length > 0 && <details className="border border-line bg-surface px-3 py-2 text-caption"><summary className="cursor-pointer font-medium">Evidence lookups ({message.response.tool_calls.length})</summary><ul className="mt-2 space-y-1 text-micro text-muted">{message.response.tool_calls.map((call, index) => <li key={`${call.tool}-${index}`} className="flex items-center gap-2"><Icon name={call.ok ? "check" : "warning"} size={13} />{call.tool.replaceAll("_", " ")}{call.ok ? " · read" : ` · ${call.error ?? "unavailable"}`}</li>)}</ul></details>}
              </div>}
            </article>)}
            {busy && <p role="status" className="text-caption text-muted">The agent is checking the current site graph…</p>}
            {error && <p role="alert" className="border border-danger/25 bg-danger/5 p-3 text-caption text-danger">{error} <button type="button" onClick={() => setInput(lastQuestion)} className="underline">Edit and retry</button></p>}
            <div ref={endRef} />
          </div>

          <form onSubmit={(event) => { event.preventDefault(); void send(); }} className="border-t border-line p-3 sm:p-4">
            <div className="flex items-end gap-2"><label htmlFor="agent-sandbox-input" className="sr-only">Message the AIDTRACE agent</label><textarea id="agent-sandbox-input" value={input} onChange={(event) => setInput(event.target.value.slice(0, 500))} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void send(); } }} rows={2} maxLength={500} placeholder="Ask the agent about this site's evidence…" disabled={!canChat || busy} className="min-h-12 min-w-0 flex-1 resize-y border border-line bg-canvas px-3 py-2.5 text-sm outline-none focus:border-accent disabled:opacity-60"/><button type="submit" aria-label="Send message" disabled={!canChat || busy || input.trim().length < 3} className="grid size-11 shrink-0 place-items-center bg-accent text-on-accent disabled:cursor-not-allowed disabled:opacity-40"><Icon name="paper-plane-right" size={18} /></button>{busy && <button type="button" onClick={stop} className="min-h-11 border border-line px-3 text-caption font-medium">Stop</button>}</div>
            <p className="mt-1.5 text-right text-micro text-muted">{input.length}/500 · Enter to send · Shift+Enter for a new line</p>
          </form>
        </section>

        <aside className="space-y-4">
          <section className="border border-line bg-surface p-5">
            <p className="text-micro font-bold uppercase tracking-wider text-muted">Agent readiness</p>
            {statusError ? <p role="alert" className="mt-3 text-caption text-danger">{statusError}</p> : !readiness ? <p className="mt-3 text-caption text-muted">Checking provider…</p> : <>
              <p className={`mt-3 flex items-center gap-2 text-sm font-semibold ${readiness.ready ? "text-positive" : "text-caution"}`}><span className={`size-2 rounded-full ${readiness.ready ? "bg-positive" : "bg-caution"}`} />{readiness.ready ? "Model reasoning ready" : readiness.graph_chat_available ? "Graph answers available" : "Provider not ready"}</p>
              <p className="mt-2 text-caption leading-relaxed text-muted">{readiness.reason}</p>
              <dl className="mt-4 space-y-2 border-t border-line pt-3 text-caption"><div className="flex justify-between gap-3"><dt className="text-muted">Model</dt><dd className="text-right font-medium">{readiness.model}</dd></div><div className="flex justify-between gap-3"><dt className="text-muted">Fallback</dt><dd className="font-medium">{readiness.fallback}</dd></div></dl>
            </>}
            <button type="button" disabled={status.refreshing} onClick={() => void status.refresh()} className="mt-4 border border-line px-3 py-2 text-caption font-medium text-muted hover:text-ink">{status.refreshing ? "Refreshing?" : "Refresh readiness"}</button>
            {status.updatedAt && <p className="mt-2 text-micro text-muted">Checked {new Date(status.updatedAt).toLocaleTimeString()} ? refreshes automatically</p>}
          </section>
          <section className="border border-line bg-surface p-5">
            <div className="flex items-center justify-between gap-2"><h3 className="text-sm font-semibold">Recent agent handoffs</h3><button type="button" disabled={handoffState.refreshing || memoryState.refreshing} onClick={() => void Promise.all([handoffState.refresh(), memoryState.refresh()])} className="text-micro text-muted underline disabled:opacity-50">Refresh</button></div>
            {handoffState.error || memoryState.error ? <p role="alert" className="mt-3 text-caption text-danger">{handoffState.error ?? memoryState.error}</p> : !handoffState.data || !memoryState.data ? <p role="status" className="mt-3 text-caption text-muted">Reading current handoffs…</p> : handoffState.data.length === 0 ? <p className="mt-3 text-caption text-muted">No agent has recalled another agent&apos;s memory in this site yet.</p> : <ul className="mt-3 space-y-2">{handoffState.data.slice(0, 12).map((handoff) => {
              const memory = memoryState.data?.memories.find((item) => item.id === handoff.memory_id);
              return <li key={`${handoff.recall_session}-${handoff.memory_id}`} className="border-t border-line pt-2 text-caption first:border-t-0 first:pt-0">
                <p><strong>{handoff.produced_by}</strong> → <strong>{handoff.recalled_by}</strong></p>
                <p className="mt-0.5 text-micro text-muted">{memory?.summary ?? handoff.memory_id}</p>
                <div className="mt-1 flex flex-wrap items-center gap-2"><span className={`border px-2 py-0.5 text-micro ${handoff.usable ? "border-positive/30 text-positive" : "border-caution/30 text-caution"}`}>{handoff.usable ? "usable now" : `${handoff.memory_status.toLowerCase()} · review`}</span><span className="font-mono text-[10px] text-muted">{new Date(handoff.at).toLocaleString()}</span></div>
                {memory?.sources.length ? <p className="mt-1 break-all font-mono text-[10px] text-muted">Evidence: {memory.sources.map((source) => source.id).join(", ")}</p> : null}
                {memory?.blocked_reason && <p className="mt-1 text-micro text-danger">Blocked: {memory.blocked_reason}</p>}
              </li>;
            })}</ul>}
            {handoffState.updatedAt && <p className="mt-2 text-micro text-muted">Checked {new Date(handoffState.updatedAt).toLocaleTimeString()} · refreshes automatically</p>}
          </section>
          <section className="border border-line bg-surface p-5">
            <h3 className="text-sm font-semibold">Sandbox boundaries</h3>
            <ul className="mt-3 space-y-2 text-caption leading-relaxed text-muted"><li className="flex gap-2"><Icon name="check" size={14} className="mt-0.5 shrink-0 text-positive" />Reads evidence from your authenticated site only.</li><li className="flex gap-2"><Icon name="check" size={14} className="mt-0.5 shrink-0 text-positive" />Shows cited record IDs and the tools it used.</li><li className="flex gap-2"><Icon name="lock-simple" size={14} className="mt-0.5 shrink-0 text-accent" />Cannot write, approve, or execute operational actions.</li><li className="flex gap-2"><Icon name="info" size={14} className="mt-0.5 shrink-0 text-muted" />Conversation is temporary and sent as bounded context with each request.</li></ul>
          </section>
          <section className="border border-caution/25 bg-caution/5 p-4 text-caption leading-relaxed text-muted"><strong className="font-semibold text-caution">Check evidence before acting.</strong> Agent replies are interpretations; linked records and the current workspace remain authoritative.</section>
        </aside>
      </div>
    </main>
  );
}
