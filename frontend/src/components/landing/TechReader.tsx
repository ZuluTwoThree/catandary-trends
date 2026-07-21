"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Interactive "technology reader": pick a technology and see (a) an
 * improvement-rate trajectory K(t) with an uncertainty band and a greyed
 * "not yet reliable" recent-years zone, and (b) where it sits on the four
 * lead-time tiers. Curves are illustrative (shape/direction from our
 * validation set), clearly labelled — the live engine returns real figures.
 */
type Tech = {
  key: string;
  label: string;
  pts: number[];
  rate: string;
  verdict: string;
  color: string;
  lead: [number, number, number, number];
  note: string;
};

const TECHS: Tech[] = [
  { key: "battery", label: "Solid-state battery", pts: [0.28, 0.3, 0.34, 0.4, 0.5, 0.62, 0.72, 0.8, 0.85, 0.88], rate: "≈ 9%/yr", verdict: "Steady", color: "#34d399", lead: [0.3, 0.42, 0.58, 0.78], note: "Solid-state battery: research and patents run well ahead of a market that's only now scaling." },
  { key: "crispr", label: "CRISPR gene editing", pts: [0.2, 0.24, 0.32, 0.46, 0.62, 0.78, 0.88, 0.93, 0.96, 0.97], rate: "accelerating", verdict: "Accelerating", color: "#22c55e", lead: [0.22, 0.4, 0.6, 0.72], note: "CRISPR: a steep science-led take-off — the engine reads the acceleration in the citation graph." },
  { key: "solar", label: "Solar PV", pts: [0.35, 0.48, 0.6, 0.7, 0.78, 0.83, 0.86, 0.88, 0.89, 0.9], rate: "maturing", verdict: "Maturing", color: "#60a5fa", lead: [0.2, 0.34, 0.52, 0.62], note: "Solar PV: a maturing S-curve — fast improvement earlier, flattening as it industrialises." },
  { key: "ml", label: "Machine learning", pts: [0.22, 0.26, 0.3, 0.38, 0.5, 0.66, 0.82, 0.92, 0.97, 0.99], rate: "accelerating", verdict: "Accelerating", color: "#d4ff3a", lead: [0.3, 0.46, 0.66, 0.8], note: "Machine learning: a rising cluster and a steep recent trajectory — the engine flags the surge." },
];

const TIER_COLORS = ["#a78bfa", "#60a5fa", "#34d399", "#d4ff3a"];
const TIER_NAMES = ["Science", "Patents", "Funding", "Market"];

function hexA(hex: string, a: number) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${a})`;
}

export default function TechReader() {
  const ref = useRef<HTMLCanvasElement | null>(null);
  const [cur, setCur] = useState<Tech>(TECHS[0]);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;

    function draw() {
      const c = canvas as HTMLCanvasElement;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const r = c.getBoundingClientRect();
      c.width = Math.max(1, Math.round(r.width * dpr));
      c.height = Math.max(1, Math.round(r.height * dpr));
      const ctx = c.getContext("2d");
      if (!ctx) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const W = r.width;
      const H = r.height;
      const d = cur;
      ctx.clearRect(0, 0, W, H);
      const padL = 8;
      const padR = 8;
      const padT = 12;
      const padB = 16;
      const pw = W - padL - padR;
      const ph = H - padT - padB;

      ctx.strokeStyle = "rgba(58,61,53,0.4)";
      ctx.lineWidth = 1;
      for (let g = 0; g <= 3; g++) {
        const y = padT + (ph * g) / 3;
        ctx.beginPath();
        ctx.moveTo(padL, y);
        ctx.lineTo(padL + pw, y);
        ctx.stroke();
      }
      const cut = 0.8;
      ctx.fillStyle = "rgba(255,255,255,0.035)";
      ctx.fillRect(padL + pw * cut, padT, pw * (1 - cut), ph);
      ctx.strokeStyle = "rgba(138,141,130,0.35)";
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(padL + pw * cut, padT);
      ctx.lineTo(padL + pw * cut, padT + ph);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = "rgba(138,141,130,0.7)";
      ctx.font = "8px ui-monospace, monospace";
      ctx.textBaseline = "top";
      ctx.fillText("not yet reliable", padL + pw * cut + 4, padT + 2);

      const pts = d.pts;
      const n = pts.length;
      const X = (i: number) => padL + (pw * i) / (n - 1);
      const Y = (v: number) => padT + ph * (1 - v);

      ctx.beginPath();
      pts.forEach((v, i) => {
        const x = X(i);
        const y = Y(Math.min(1, v + 0.07));
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      for (let i = n - 1; i >= 0; i--) ctx.lineTo(X(i), Y(Math.max(0, pts[i] - 0.07)));
      ctx.closePath();
      ctx.fillStyle = hexA(d.color, 0.12);
      ctx.fill();

      ctx.beginPath();
      pts.forEach((v, i) => {
        const x = X(i);
        const y = Y(v);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.strokeStyle = d.color;
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.fillStyle = d.color;
      ctx.beginPath();
      ctx.arc(X(n - 1), Y(pts[n - 1]), 3, 0, 7);
      ctx.fill();
    }

    draw();
    let rt = 0;
    const onResize = () => {
      window.clearTimeout(rt);
      rt = window.setTimeout(draw, 150);
    };
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      window.clearTimeout(rt);
    };
  }, [cur]);

  return (
    <div className="lp-demo lp-reveal in">
      <div className="lp-demo-head" role="group" aria-label="Choose a technology">
        {TECHS.map((t) => (
          <button
            key={t.key}
            className="lp-chip"
            aria-pressed={cur.key === t.key}
            onClick={() => setCur(t)}
            type="button"
          >
            {t.label}
          </button>
        ))}
      </div>
      <div className="lp-demo-body">
        <div className="lp-demo-pane">
          <div className="lp-pane-label">Improvement-rate trajectory &middot; K(t)</div>
          <div className="lp-chartbox">
            <canvas ref={ref} aria-label="Line chart of a technology's improvement-rate trajectory over time, with an uncertainty band and a greyed recent-years zone the engine treats as not yet reliable." />
          </div>
          <div className="lp-verdict">
            <span className="lp-v-rate">{cur.rate}</span>
            <span className="lp-v-badge" style={{ color: cur.color }}>
              {cur.verdict}
            </span>
          </div>
          <p className="lp-note">
            Illustrative shape and direction from our validation set — the live engine returns the
            figures and greys out years too recent to trust.
          </p>
        </div>
        <div className="lp-demo-pane">
          <div className="lp-pane-label">Where it is on the chain &middot; lead-time tiers</div>
          <div className="lp-lanes">
            {TIER_NAMES.map((name, i) => (
              <div className="lp-lane" key={name}>
                <span className="lp-lname" style={{ color: TIER_COLORS[i] }}>
                  {name}
                </span>
                <div className="lp-track">
                  <span className="lp-fill" style={{ background: TIER_COLORS[i], width: `${cur.lead[i] * 100}%` }} />
                  <span className="lp-dot" style={{ color: TIER_COLORS[i], background: TIER_COLORS[i], left: `${cur.lead[i] * 100}%` }} />
                </div>
              </div>
            ))}
          </div>
          <div className="lp-axis">
            <span />
            <div className="lp-ticks">
              <span>1995</span>
              <span>2005</span>
              <span>2015</span>
              <span>2026</span>
            </div>
          </div>
          <p className="lp-note">{cur.note}</p>
        </div>
      </div>
    </div>
  );
}
