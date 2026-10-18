"use client";

// The compact, searchable Extensions drawer. It is closed by default, opens over the left edge of the centre panel, and lists extensions by category.
// Extensions the signed-in role cannot open are shown disabled with the reason, never hidden silently.
import { useEffect, useMemo, useRef, useState } from "react";
import { StatusBadge } from "@/components/ui";
import type { Role } from "@/lib/types";
import { EXTENSION_CATEGORIES, LAUNCHER_EXTENSIONS, isAvailable, searchExtensions, type AidtraceExtension } from "./registry";

interface Props { open: boolean; role: Role; onClose: () => void; onSelect: (id: string) => void; extensions?: AidtraceExtension[] }

export function ExtensionLauncher({ open, role, onClose, onSelect, extensions = LAUNCHER_EXTENSIONS }: Props) {
  const [query, setQuery] = useState("");
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (!open) return;
    const t = window.setTimeout(() => input.current?.focus(), 0);
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", key);
    return () => { window.clearTimeout(t); window.removeEventListener("keydown", key); };
  }, [open, onClose]);
  const results = useMemo(() => searchExtensions(extensions, query), [extensions, query]);
  if (!open) return null;
  return (
    <div className="absolute inset-0 z-40" data-testid="aidtrace-launcher">
      <button type="button" aria-label="Close extensions" className="absolute inset-0 bg-[var(--scrim)]" onClick={onClose} tabIndex={-1} />
      <aside role="dialog" aria-label="Extensions" aria-modal="true" className="absolute inset-y-0 left-0 flex w-[min(400px,92vw)] flex-col border-r border-line bg-surface shadow-lg">
        <div className="border-b border-line p-3">
          <label htmlFor="aidtrace-ext-search" className="sr-only">Search extensions</label>
          <input id="aidtrace-ext-search" ref={input} type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search extensions…" autoComplete="off"
            className="h-10 w-full border border-line bg-canvas px-3 text-caption text-ink placeholder:text-muted focus-visible:outline-2 focus-visible:outline-accent" />
          <p className="mt-1.5 text-micro text-muted" role="status">{results.length} of {extensions.length} extensions · Esc to close</p>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          {results.length === 0 && <p className="p-4 text-caption text-muted">No extension matches “{query}”.</p>}
          {EXTENSION_CATEGORIES.map((category) => {
            const items = results.filter((e) => e.category === category);
            if (!items.length) return null;
            return (
              <section key={category} aria-label={category} className="border-b border-line">
                <h3 className="px-3 pb-1 pt-3 text-micro font-medium uppercase tracking-wider text-muted">{category}</h3>
                <ul>
                  {items.map((e) => {
                    const ok = isAvailable(e, role);
                    return (
                      <li key={e.id}>
                        <button type="button" disabled={!ok} onClick={() => onSelect(e.id)} title={ok ? undefined : "Your role cannot open this extension."}
                          className="block w-full px-3 py-2 text-left hover:bg-surface-2 focus-visible:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-50">
                          <span className="flex flex-wrap items-center gap-2"><span className="text-caption font-medium text-ink">{e.title}</span>
                            {e.status === "partial" && <StatusBadge tone="caution">partial</StatusBadge>}
                            {e.contextual && <StatusBadge tone="info">context-aware</StatusBadge>}
                            {!ok && <StatusBadge tone="neutral">restricted</StatusBadge>}</span>
                          <span className="mt-0.5 block text-micro leading-snug text-muted">{e.description}</span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </section>
            );
          })}
        </div>
      </aside>
    </div>
  );
}
