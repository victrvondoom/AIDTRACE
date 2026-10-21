"use client";

import { useEffect, useState } from "react";
import { Button, StatusBadge } from "@/components/ui";
import {
  getCoordinationCapabilities,
  getCoordinationRuns,
  getCoordinationRunDetails,
  cancelCoordinationTask,
  startCoordinationRun,
  type CoordinationCapability,
  type CoordinationEvent,
  type CoordinationRun,
  type CoordinationTask,
} from "@/lib/lab-api";

const PRESET_GOALS = [
  { title: "Cybersecurity", domain: "cybersecurity", goal: "Check whether the supplied cybersecurity evidence IDs exist in the site graph." },
  { title: "Finance", domain: "finance", goal: "Check whether the supplied financial evidence IDs exist and report capability readiness." },
  { title: "Supply chain", domain: "supply_chain", goal: "Check whether the supplied supplier evidence IDs exist and report capability readiness." },
];

type Tab = "workflow" | "brain" | "registry" | "deletion";
type ConnectionStatus = "CHECKING" | "READY" | "UNAVAILABLE";

export function CoordinationWorkspace() {
  const [activeTab, setActiveTab] = useState<Tab>("workflow");
  const [goal, setGoal] = useState(PRESET_GOALS[0].goal);
  const [domain, setDomain] = useState(PRESET_GOALS[0].domain);
  const [evidenceInput, setEvidenceInput] = useState("");
  const [running, setRunning] = useState(false);
  const [activeRun, setActiveRun] = useState<CoordinationRun | null>(null);
  const [tasks, setTasks] = useState<CoordinationTask[]>([]);
  const [events, setEvents] = useState<CoordinationEvent[]>([]);
  const [pastRuns, setPastRuns] = useState<CoordinationRun[]>([]);
  const [capabilities, setCapabilities] = useState<CoordinationCapability[]>([]);
  const [connection, setConnection] = useState<ConnectionStatus>("CHECKING");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getCoordinationCapabilities(), getCoordinationRuns("all")])
      .then(([registry, runs]) => {
        if (cancelled) return;
        setCapabilities(registry.capabilities);
        setPastRuns(runs.runs);
        setConnection("READY");
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        setConnection("UNAVAILABLE");
        setError(reason instanceof Error ? reason.message : "The FalkorDB coordination graph is unavailable.");
      });
    return () => { cancelled = true; };
  }, []);

  const handleLaunch = async () => {
    setRunning(true);
    setError(null);
    try {
      const contextIds = [...new Set(evidenceInput.split(/[\n,]/).map((id) => id.trim()).filter(Boolean))].slice(0, 100);
      const result = await startCoordinationRun(goal, domain, contextIds);
      setActiveRun({ ...result.run, status: result.execution?.status ?? result.run.status });
      if (result.execution) {
        setTasks(result.execution.tasks);
        setEvents(result.execution.events);
      } else if (result.tasks) {
        setTasks(result.tasks);
      }
      const refreshed = await getCoordinationRuns("all");
      setPastRuns(refreshed.runs);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "The coordination run could not be persisted.");
    } finally {
      setRunning(false);
    }
  };

  const handleCancelTask = async (taskId: string) => {
    if (!activeRun) return;
    setError(null);
    try {
      await cancelCoordinationTask(activeRun.run_id, taskId);
      const updated = await getCoordinationRunDetails(activeRun.run_id);
      setActiveRun(updated.run);
      setTasks(updated.tasks);
      setEvents(updated.events);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "The task cancellation could not be persisted.");
    }
  };

  const toneForStatus = (status: string) => {
    switch (status) {
      case "SUCCEEDED":
      case "OPERATIONAL":
      case "READY":
        return "verified";
      case "RUNNING":
      case "CLAIMED":
      case "PARTIAL":
      case "CONFIGURATION_REQUIRED":
        return "caution";
      case "FAILED":
      case "BLOCKED":
      case "UNAVAILABLE":
        return "danger";
      default:
        return "neutral";
    }
  };

  const tabs: { id: Tab; label: string }[] = [
    { id: "workflow", label: "Investigation" },
    { id: "brain", label: `Prior Runs (${pastRuns.length})` },
    { id: "registry", label: `Capability Registry (${capabilities.length})` },
    { id: "deletion", label: "Deletion readiness" },
  ];

  return (
    <div className="flex h-full w-full flex-col bg-canvas text-ink">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-3">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-body font-bold text-ink">Graph-backed coordination</h1>
            <StatusBadge tone={toneForStatus(connection)}>{connection === "CHECKING" ? "Checking FalkorDB" : connection === "READY" ? "FalkorDB connected" : "FalkorDB unavailable"}</StatusBadge>
          </div>
          <p className="max-w-3xl text-caption text-muted">
            Worker A checks exact graph IDs. Worker B reports adapter readiness. The run stays blocked until a tested domain adapter can produce evidence-backed findings.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5 rounded-lg border border-line bg-surface p-1 text-caption">
          {tabs.map((tab) => (
            <button key={tab.id} type="button" onClick={() => setActiveTab(tab.id)} aria-current={activeTab === tab.id ? "page" : undefined}
              className={`rounded px-3 py-1 font-medium transition-colors ${activeTab === tab.id ? "bg-accent text-on-accent" : "text-muted hover:text-ink"}`}>
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {error && <div role="alert" className="mx-5 mt-3 rounded border border-danger/30 bg-danger/10 px-4 py-2 text-caption text-danger">{error}</div>}

      <div className="min-h-0 flex-1 overflow-y-auto p-5">
        {activeTab === "workflow" && (
          <div className="space-y-6">
            <div className="rounded-lg border border-line bg-surface p-4 shadow-xs">
              <span className="text-micro font-semibold uppercase tracking-wider text-muted">Investigation goal</span>
              <div className="mt-2 flex flex-wrap gap-2">
                {PRESET_GOALS.map((preset) => (
                  <button key={preset.title} type="button" onClick={() => { setGoal(preset.goal); setDomain(preset.domain); }}
                    className={`rounded border px-2.5 py-1 text-micro transition-colors ${goal === preset.goal ? "border-ink bg-surface-2 font-semibold text-ink" : "border-line text-muted hover:text-ink"}`}>
                    {preset.title}
                  </button>
                ))}
              </div>
              <label htmlFor="coordination-goal" className="sr-only">Investigation goal</label>
              <div className="mt-3 flex flex-wrap gap-2">
                <input id="coordination-goal" type="text" value={goal} onChange={(event) => setGoal(event.target.value)} maxLength={500}
                  placeholder="Describe the question to investigate" className="min-w-[16rem] flex-1 rounded border border-line bg-canvas px-3 py-1.5 text-caption text-ink placeholder:text-muted focus:border-ink focus:outline-hidden" />
                <Button onClick={handleLaunch} disabled={running || connection !== "READY" || goal.trim().length < 3} variant="primary">
                  {running ? "Coordinating…" : "Run graph check"}
                </Button>
              </div>
              <label htmlFor="coordination-evidence-ids" className="mt-3 block text-micro font-semibold uppercase tracking-wider text-muted">
                Exact evidence IDs in the site graph
              </label>
              <textarea id="coordination-evidence-ids" value={evidenceInput} onChange={(event) => setEvidenceInput(event.target.value)} rows={2} maxLength={13_000}
                placeholder="One graph ID per line or comma separated; up to 100 IDs"
                className="mt-1 w-full resize-y rounded border border-line bg-canvas px-3 py-2 text-caption text-ink placeholder:text-muted focus:border-ink focus:outline-hidden" />
              <p className="mt-1 text-micro text-muted">The check verifies node presence only. It does not verify domain facts or treat a missing ID as evidence.</p>
            </div>

            {activeRun && (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line bg-surface p-3 text-caption">
                  <div><span className="font-semibold">Run:</span> <span className="font-mono text-micro text-muted">{activeRun.run_id}</span>
                    <p className="text-micro text-muted">{activeRun.campaign_goal}</p></div>
                  <StatusBadge tone={toneForStatus(activeRun.status)}>{activeRun.status}</StatusBadge>
                </div>
                <div>
                  <h2 className="mb-2 text-micro font-semibold uppercase tracking-wider text-muted">Dependency-aware task trace</h2>
                  <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                    {tasks.map((task, index) => (
                      <article key={task.task_id} className="flex flex-col justify-between rounded-lg border border-line bg-surface p-3.5 shadow-xs">
                        <div>
                          <div className="flex items-center justify-between gap-2"><span className="rounded bg-canvas px-1.5 py-0.5 font-mono text-[10px] text-muted">Stage {index + 1}</span><StatusBadge tone={toneForStatus(task.status)}>{task.status}</StatusBadge></div>
                          <h3 className="mt-2 text-caption font-semibold">{task.goal}</h3>
                          <p className="mt-1 text-micro text-muted">Capability: <code className="text-ink">{task.capability_id}</code></p>
                          <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-micro text-muted"><span className="rounded border border-line px-1.5 py-0.5">Role: {task.assigned_role}</span>{task.depends_on.length > 0 && <span className="rounded bg-accent/10 px-1.5 py-0.5 font-medium text-accent">Waits on {task.depends_on.length}</span>}</div>
                        </div>
                        {task.result_data && <pre className="mt-3 overflow-x-auto whitespace-pre-wrap break-words rounded border border-line/60 bg-canvas p-2 text-[10px] text-muted">{JSON.stringify(task.result_data, null, 2)}</pre>}
                        {task.error && <p className="mt-2 text-micro text-danger">{task.error}</p>}
                        {["PENDING", "READY", "CLAIMED", "RUNNING", "WAITING_FOR_DEPENDENCY", "WAITING_FOR_REVIEW"].includes(task.status) && <button type="button" onClick={() => void handleCancelTask(task.task_id)} className="mt-3 min-h-9 self-start border border-danger/30 px-3 text-micro text-danger hover:bg-danger/5">Cancel task</button>}
                      </article>
                    ))}
                  </div>
                </div>
                {events.length > 0 && <div>
                  <h2 className="mb-2 text-micro font-semibold uppercase tracking-wider text-muted">Persisted event trace ({events.length})</h2>
                  <div className="max-h-60 divide-y divide-line overflow-y-auto rounded-lg border border-line bg-surface text-caption">
                    {events.map((event) => <div key={event.event_id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-1.5 text-micro">
                      <div className="flex flex-wrap items-center gap-2"><span className="font-mono text-muted">{event.timestamp.slice(11, 19)}</span><span className="rounded bg-canvas px-1.5 py-0.5 font-semibold">{event.event_type}</span><span className="text-muted">by <strong className="text-ink">{event.agent_id}</strong></span></div>
                      <span className="max-w-xs truncate text-muted">{JSON.stringify(event.payload)}</span>
                    </div>)}
                  </div>
                </div>}
              </div>
            )}
          </div>
        )}

        {activeTab === "brain" && <div className="space-y-4">
          <div className="rounded-lg border border-line bg-surface p-4"><h2 className="text-body font-semibold">Prior coordination runs</h2><p className="mt-1 text-caption text-muted">Run and task history is persisted in this site&apos;s graph. Prior runs can inform planning but do not prove that old evidence is current.</p></div>
          {pastRuns.length === 0 ? <p className="rounded-lg border border-dashed border-line p-4 text-caption text-muted">No coordination runs are recorded for this site.</p> : <div className="space-y-2.5">{pastRuns.map((run) => <article key={run.run_id} className="rounded-lg border border-line bg-surface p-3.5"><div className="flex items-center justify-between gap-2"><span className="font-mono text-micro font-semibold text-accent">{run.run_id}</span><StatusBadge tone={toneForStatus(run.status)}>{run.status}</StatusBadge></div><h3 className="mt-1 text-caption font-semibold">{run.campaign_goal}</h3><p className="mt-1 text-micro text-muted">Domain: {run.domain} · Tasks: {run.task_ids.length} · Created: {run.created_at.slice(0, 16)}</p></article>)}</div>}
        </div>}

        {activeTab === "registry" && <div className="space-y-4">
          <div className="rounded-lg border border-line bg-surface p-4"><h2 className="text-body font-semibold">Capability registry</h2><p className="mt-1 text-caption text-muted">Statuses reflect implementation and prerequisites. An OPERATIONAL status requires a tested backend operation; a route or specification is not enough.</p></div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">{capabilities.map((capability) => <article key={capability.capability_id} className="flex flex-col justify-between rounded-lg border border-line bg-surface p-3.5"><div><div className="flex items-center justify-between gap-2"><span className="font-mono text-micro text-muted">{capability.capability_id}</span><StatusBadge tone={toneForStatus(capability.availability)}>{capability.availability}</StatusBadge></div><h3 className="mt-1.5 text-caption font-semibold">{capability.display_name}</h3><p className="mt-1 text-micro leading-relaxed text-muted">{capability.description}</p><p className="mt-2 text-micro text-muted">Required services: {capability.required_services?.join(", ") || "None listed"}</p></div><div className="mt-3 flex items-center justify-between border-t border-line/60 pt-2 text-[11px] text-muted"><span>{capability.pack}</span><span>Risk: {capability.risk_level}</span></div></article>)}</div>
        </div>}

        {activeTab === "deletion" && <div className="max-w-2xl space-y-4">
          <div className="rounded-lg border border-caution/30 bg-caution/5 p-4"><h2 className="text-body font-semibold">Governed deletion is not available</h2><p className="mt-2 text-caption leading-relaxed text-muted">The compatibility endpoint fails closed and changes no data. A real deletion flow needs retention-policy review, authorization, removal from every applicable graph, vector, search, and relational store, index revocation, and re-query verification before it can issue a receipt.</p></div>
        </div>}
      </div>
    </div>
  );
}
