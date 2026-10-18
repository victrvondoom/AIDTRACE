"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

import { Icon } from "@/components/icon";
type Theme = "light" | "dark";

/** Flips the single AIDTRACE UI between its light and dark palettes. */
export function ThemeToggle({ className = "", labeled = false }: { className?: string; labeled?: boolean }) {
  const [theme, setTheme] = useState<Theme>("light");

  useEffect(() => {
    const sync = () => setTheme(document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light");
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    const onStorage = (event: StorageEvent) => {
      if (event.key === "kairos-theme" && (event.newValue === "light" || event.newValue === "dark")) {
        document.documentElement.setAttribute("data-theme", event.newValue);
      }
    };
    window.addEventListener("storage", onStorage);
    return () => { observer.disconnect(); window.removeEventListener("storage", onStorage); };
  }, []);

  function applyTheme(next: Theme) {
    setTheme(next);
    const apply = () => {
      document.documentElement.setAttribute("data-theme", next);
      try { localStorage.setItem("kairos-theme", next); } catch { /* no-op */ }
    };
    // Crossfade the palette flip where the browser supports it. A hard swap of
    // every surface at once reads as a glitch; the snapshot fade reads as a change
    // of light. Unsupported browsers and reduced-motion users get the instant swap.
    const startViewTransition = document.startViewTransition?.bind(document);
    if (!startViewTransition || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      apply();
      return;
    }
    startViewTransition(apply);
  }

  const isDark = theme === "dark";

  if (labeled) return (
    <div role="group" aria-label="Appearance" className={cn("grid grid-cols-2 gap-1 border border-line bg-surface-2 p-1", className)}>
      {(["light", "dark"] as const).map((option) => (
        <button key={option} type="button" aria-pressed={theme === option} onClick={() => applyTheme(option)}
          className={cn("flex min-h-11 items-center justify-center gap-2 px-2 text-caption font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent",
            theme === option ? "border border-line bg-surface text-ink shadow-sm" : "border border-transparent text-muted hover:text-ink")}>
          <Icon name={option === "light" ? "sun" : "moon"} size={16} />
          {option === "light" ? "Daylight" : "Nightlight"}
        </button>
      ))}
    </div>
  );

  return (
    <button
      type="button"
      onClick={() => applyTheme(isDark ? "light" : "dark")}
      role="switch"
      aria-checked={isDark}
      aria-label="Nightlight theme"
      title={`Switch to ${isDark ? "Daylight (white)" : "Nightlight (black)"}`}
      className={cn("grid size-11 shrink-0 place-items-center text-muted transition-colors hover:bg-surface-2 hover:text-ink focus-visible:outline-2 focus-visible:outline-accent", className)}
    >
      {isDark ? (
        <Icon name="sun" size={15} />
      ) : (
        <Icon name="moon" size={15} />
      )}
    </button>
  );
}

/** Sunlight / high-contrast toggle — third palette for outdoor legibility. */
export function ContrastToggle({ className = "" }: { className?: string }) {
  const [high, setHigh] = useState(false);

  useEffect(() => {
    // Mount-once sync of the pre-hydration <html data-contrast> into React state.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reading external DOM state on mount is what effects are for
    setHigh(document.documentElement.getAttribute("data-contrast") === "high");
  }, []);

  function toggle() {
    const next = !high;
    setHigh(next);
    if (next) {
      document.documentElement.setAttribute("data-contrast", "high");
    } else {
      document.documentElement.removeAttribute("data-contrast");
    }
    try { localStorage.setItem("kairos-contrast", next ? "high" : ""); } catch { /* no-op */ }
  }

  return (
    <button
      type="button"
      onClick={toggle}
      role="switch"
      aria-checked={high}
      aria-label={high ? "Disable sunlight mode" : "Enable sunlight mode"}
      title={high ? "Disable sunlight mode" : "Sunlight / high-contrast mode"}
      className={cn("grid size-8 place-items-center text-muted transition-colors hover:bg-surface-2", high ? "text-caution" : "hover:text-ink", className)}
    >
      <Icon name="sun" size={15} />
    </button>
  );
}
