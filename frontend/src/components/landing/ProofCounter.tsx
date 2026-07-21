"use client";

import { useEffect, useRef, useState } from "react";

/** Animated count-up for the hero proof stats. Values are live DB numbers
 *  passed from the server page; the last item ("100% local") is static. */
type Item = { value: number | null; display: string; label: string };

function useCountUp(target: number | null, run: boolean) {
  // Initialise to the real value so SSR / no-JS / crawlers see the true number;
  // the animation (progressive enhancement) counts up once it scrolls into view.
  const [n, setN] = useState(target ?? 0);
  useEffect(() => {
    if (target == null || !run) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) return; // already showing the real number
    let raf = 0;
    let start = 0;
    const dur = 1600;
    const step = (ts: number) => {
      if (!start) start = ts;
      const p = Math.min((ts - start) / dur, 1);
      const eased = 1 - Math.pow(1 - p, 3);
      setN(Math.round(target * eased));
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target, run]);
  return n;
}

function Stat({ item, run }: { item: Item; run: boolean }) {
  const n = useCountUp(item.value, run);
  const text = item.value == null ? item.display : n.toLocaleString("en-US");
  return (
    <div>
      <div className="lp-num">{text}</div>
      <div className="lp-lbl">{item.label}</div>
    </div>
  );
}

export default function ProofCounter({ items }: { items: Item[] }) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [run, setRun] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (es) => es.forEach((e) => e.isIntersecting && setRun(true)),
      { threshold: 0.4 }
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return (
    <div className="lp-proof" ref={ref} aria-label="Corpus at a glance">
      {items.map((it) => (
        <Stat key={it.label} item={it} run={run} />
      ))}
    </div>
  );
}
