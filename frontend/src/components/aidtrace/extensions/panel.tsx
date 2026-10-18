"use client";

// The centre-panel shell every extension opens in: title, context line, scope note, optional summary header, tabs, and the body (a migrated legacy page or a
// native component). Closing it only hides this panel; the workspace keeps the selection, run results and view, so the investigation is exactly as it was.
import { useCallback, useState } from "react";
import { Boundary } from "@/features/feature-host";
import { Button, StatusBadge } from "@/components/ui";
import { ContextBar } from "./native";
import { resolveRoute } from "./legacy-routes";
import { LegacyRouteHost } from "./route-host";
import { tabForPath, type AidtraceExtension } from "./registry";

interface Props {
  ext: AidtraceExtension;
  /** A legacy path to open at, e.g. "/documents/ABC". Omit to open the first tab. */
  initialPath?: string | null;
  onClose: () => void;
  /** Switch to another extension (a link inside this one points at a page another extension owns). */
  onOpen: (id: string, path?: string) => void;
}

export function ExtensionPanel({ ext, initialPath, onClose, onOpen }: Props) {
  const initialTab = (initialPath && tabForPath(ext, initialPath)) || ext.tabs[0];
  const [tabId, setTabId] = useState(initialTab.id);
  const [path, setPath] = useState<string | null>(initialPath && tabForPath(ext, initialPath) ? initialPath : initialTab.path ?? null);
  const [history, setHistory] = useState<string[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const tab = ext.tabs.find((t) => t.id === tabId) ?? ext.tabs[0];

  const navigate = useCallback((href: string, replace?: boolean) => {
    setNotice(null);
    const clean = href.split("?")[0];
    if (clean === "/hub" || clean === "/") { onClose(); return; }
    const resolved = resolveRoute(href);
    if (!resolved) { setNotice(`“${clean}” is not available inside the workspace.`); return; }
    if (resolved.route.extension !== ext.id) { onOpen(resolved.route.extension, href); return; }
    const target = tabForPath(ext, href);
    if (!target) { setNotice(`“${clean}” has no tab in ${ext.title}.`); return; }
    setHistory((h) => (replace || !path ? h : [...h, path]));
    setTabId(target.id); setPath(href);
  }, [ext, onClose, onOpen, path]);
  const back = useCallback(() => {
    setHistory((h) => {
      const prev = h[h.length - 1];
      if (prev) { const t = tabForPath(ext, prev); if (t) setTabId(t.id); setPath(prev); }
      return h.slice(0, -1);
    });
  }, [ext]);
  const pickTab = (id: string) => { const t = ext.tabs.find((x) => x.id === id); if (!t) return; setNotice(null); setHistory([]); setTabId(id); setPath(t.path ?? null); };

  const Header = ext.header;
  const Body = tab.body;
  return (
    <section aria-label={ext.title} className="flex size-full min-h-0 flex-col" data-testid="aidtrace-extension" data-extension={ext.id}>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-2">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <h2 className="text-body font-semibold text-ink">{ext.title}</h2>
          <span className="text-micro text-muted">{ext.category}</span>
          {ext.status === "partial" && <StatusBadge tone="caution">partial</StatusBadge>}
          {ext.contextual && <StatusBadge tone="info">follows your selection</StatusBadge>}
        </div>
        <div className="flex items-center gap-1.5">
          {history.length > 0 && <Button variant="ghost" onClick={back}>← Back</Button>}
          <Button variant="ghost" onClick={onClose} aria-label="Back to workspace">← Back to workspace</Button>
        </div>
      </div>
      <ContextBar />
      {ext.scope && <p role="note" className="border-b border-line bg-surface-2 px-4 py-2 text-micro text-muted">{ext.scope}</p>}
      {notice && <p role="status" className="border-b border-line px-4 py-2 text-micro text-caution-ink">{notice}</p>}
      <div className="min-h-0 flex-1 overflow-y-auto">
        {Header && <Boundary label={`${ext.title} summary`}><Header /></Boundary>}
        {ext.tabs.length > 1 && (
          <div role="tablist" aria-label={`${ext.title} sections`} className="flex flex-wrap gap-1 border-b border-line px-4 pt-2">
            {ext.tabs.map((t) => (
              <button key={t.id} role="tab" type="button" aria-selected={t.id === tab.id} onClick={() => pickTab(t.id)}
                className={`border-b-2 px-3 py-1.5 text-caption ${t.id === tab.id ? "border-accent font-semibold text-ink" : "border-transparent text-muted hover:text-ink"}`}>{t.label}</button>
            ))}
          </div>
        )}
        <Boundary key={`${ext.id}:${tab.id}`} label={`${ext.title} · ${tab.label}`}>
          {Body ? <Body /> : <LegacyRouteHost path={path ?? tab.path ?? ""} onNavigate={navigate} onBack={back} />}
        </Boundary>
      </div>
    </section>
  );
}
