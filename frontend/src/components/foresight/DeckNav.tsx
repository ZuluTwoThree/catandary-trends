"use client";

import { useCallback, useEffect, useState } from "react";

/**
 * Keyboard + progress rail for the briefing deck (/trends/foresight/pitch).
 *
 * The slides are plain server-rendered <section data-slide> blocks; this
 * component only adds what a presenter needs: ← → / PageUp PageDown / Home /
 * End to move, a rail on the right that shows where you are, and a click on
 * a rail dot to jump. No slide state lives here — the URL hash is the truth
 * (#s3), so a reload or a shared link lands on the same slide.
 */
export default function DeckNav({ count, labels }: { count: number; labels: string[] }) {
  const [active, setActive] = useState(0);

  const slides = useCallback(
    () => Array.from(document.querySelectorAll<HTMLElement>("[data-slide]")),
    []
  );

  const go = useCallback(
    (i: number) => {
      const all = slides();
      const idx = Math.max(0, Math.min(all.length - 1, i));
      all[idx]?.scrollIntoView({ behavior: "smooth", block: "start" });
      history.replaceState(null, "", `#s${idx}`);
      setActive(idx);
    },
    [slides]
  );

  useEffect(() => {
    const m = /^#s(\d+)$/.exec(location.hash);
    if (m) go(Number(m[1]));
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA")) return;
      if (e.key === "ArrowRight" || e.key === "PageDown" || e.key === " ") {
        e.preventDefault();
        go(active + 1);
      } else if (e.key === "ArrowLeft" || e.key === "PageUp") {
        e.preventDefault();
        go(active - 1);
      } else if (e.key === "Home") {
        e.preventDefault();
        go(0);
      } else if (e.key === "End") {
        e.preventDefault();
        go(count - 1);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, count, go]);

  useEffect(() => {
    // Keep the rail honest when the presenter scrolls with the wheel.
    const all = slides();
    if (!all.length) return;
    const io = new IntersectionObserver(
      (entries) => {
        const hit = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (hit) setActive(all.indexOf(hit.target as HTMLElement));
      },
      { threshold: [0.5] }
    );
    all.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, [slides]);

  return (
    <>
      <nav
        aria-label="Slides"
        className="fixed right-4 top-1/2 z-30 hidden -translate-y-1/2 flex-col gap-3 md:flex"
      >
        {labels.map((label, i) => (
          <button
            key={label}
            type="button"
            onClick={() => go(i)}
            aria-current={i === active ? "true" : undefined}
            title={label}
            className={`group flex items-center justify-end gap-2 font-mono text-[9px] uppercase tracking-[0.16em] ${
              i === active ? "text-accent" : "text-muted hover:text-text"
            }`}
          >
            <span className="opacity-0 transition-opacity group-hover:opacity-100 group-aria-[current=true]:opacity-100">
              {label}
            </span>
            <span
              className={`block h-[2px] transition-all ${
                i === active ? "w-6 bg-accent" : "w-3 bg-border-strong group-hover:bg-text"
              }`}
            />
          </button>
        ))}
      </nav>
      <div className="fixed bottom-4 right-4 z-30 hidden font-mono text-[10px] uppercase tracking-[0.16em] text-muted md:block">
        {active + 1} / {count} · ← →
      </div>
    </>
  );
}
