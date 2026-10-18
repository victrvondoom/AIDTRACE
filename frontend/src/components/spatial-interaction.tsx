"use client";

import { useEffect } from "react";

/** Pointer lighting changes decoration only; controls and text never move. */
export function SpatialInteraction() {
  useEffect(() => {
    const root = document.getElementById("main");
    if (!root) return;
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const fine = window.matchMedia("(pointer: fine)");
    let frame = 0;
    let active: HTMLElement | null = null;
    const clear = () => {
      cancelAnimationFrame(frame);
      active?.style.removeProperty("--pointer-x");
      active?.style.removeProperty("--pointer-y");
      active = null;
    };
    const move = (event: PointerEvent) => {
      if (motion.matches || !fine.matches) return;
      const target = event.target instanceof Element
        ? event.target.closest<HTMLElement>(".kairos-spatial-header, .kairos-depth-card")
        : null;
      if (target !== active) { clear(); active = target; }
      if (!target) return;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const bounds = target.getBoundingClientRect();
        target.style.setProperty("--pointer-x", `${event.clientX - bounds.left}px`);
        target.style.setProperty("--pointer-y", `${event.clientY - bounds.top}px`);
      });
    };
    root.addEventListener("pointermove", move, { passive: true });
    root.addEventListener("pointerleave", clear);
    motion.addEventListener("change", clear);
    return () => {
      clear();
      root.removeEventListener("pointermove", move);
      root.removeEventListener("pointerleave", clear);
      motion.removeEventListener("change", clear);
    };
  }, []);
  return null;
}
