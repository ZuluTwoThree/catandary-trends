"use client";

import { useEffect, useRef } from "react";

/**
 * The hero "lead-time instrument": innovation signals flow across four tier
 * lanes (science → patents → funding → market), converge into a cluster node,
 * and resolve into a rising share-of-voice momentum line. This animates the
 * actual product mechanism — not decoration. Canvas 2D, DPR-aware, pauses
 * off-screen, and renders a static poster under prefers-reduced-motion.
 */
type Mark = { lane: number; x: number; speed: number; r: number; a: number };

const TIERS = [
  // Canonical tier palette — keep in sync with TierCurveChart / --t-* tokens.
  { name: "SCIENCE", color: "#22d3ee" },
  { name: "PATENTS", color: "#a78bfa" },
  { name: "FUNDING", color: "#fb923c" },
  { name: "MARKET", color: "#bde63a" },
];

export default function HeroInstrument() {
  const ref = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    let ctx: CanvasRenderingContext2D;
    let W = 0;
    let H = 0;
    let laneY: number[] = [];
    let marks: Mark[] = [];
    let momentum: number[] = [];
    let raf = 0;
    let visible = true;
    let last = 0;
    let mAcc = 0;

    function fit() {
      const c = canvas as HTMLCanvasElement;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const r = c.getBoundingClientRect();
      c.width = Math.max(1, Math.round(r.width * dpr));
      c.height = Math.max(1, Math.round(r.height * dpr));
      const context = c.getContext("2d");
      if (!context) return;
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx = context;
      W = r.width;
      H = r.height;
      const top = H * 0.16;
      const bottom = H * 0.62;
      const span = bottom - top;
      laneY = TIERS.map((_, i) => top + (span * i) / (TIERS.length - 1));
      momentum = [];
      for (let i = 0; i < 40; i++) momentum.push(0.5 + 0.28 * Math.sin(i / 6) * (i / 40));
    }

    function spawn() {
      let lane = Math.floor(Math.random() * TIERS.length);
      if (Math.random() < 0.35) lane = Math.floor(Math.random() * 2);
      marks.push({ lane, x: -0.03, speed: 0.04 + Math.random() * 0.05 + (3 - lane) * 0.006, r: 1.6 + Math.random() * 1.8, a: 0 });
    }

    function draw(ts: number) {
      const dt = Math.min((ts - (last || ts)) / 1000, 0.05);
      last = ts;
      ctx.clearRect(0, 0, W, H);
      const leftPad = W * 0.06;
      const rightPad = W * 0.1;
      const plotW = W - leftPad - rightPad;
      const convX = leftPad + plotW * 0.82;
      const nodeY = laneY[3] - (laneY[3] - laneY[0]) * 0.15;

      ctx.font = "9px ui-monospace, monospace";
      ctx.textBaseline = "middle";
      TIERS.forEach((tt, i) => {
        const y = laneY[i];
        ctx.strokeStyle = "rgba(255,255,255,0.05)";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(leftPad, y);
        ctx.lineTo(leftPad + plotW, y);
        ctx.stroke();
        ctx.fillStyle = "rgba(138,141,130,0.75)";
        ctx.fillText(tt.name, leftPad, y - 8);
        ctx.fillStyle = tt.color;
        ctx.globalAlpha = 0.55;
        ctx.beginPath();
        ctx.arc(leftPad, y, 2, 0, 7);
        ctx.fill();
        ctx.globalAlpha = 1;
      });

      ctx.strokeStyle = "rgba(58,61,53,0.6)";
      ctx.beginPath();
      ctx.moveTo(leftPad, H * 0.7);
      ctx.lineTo(leftPad + plotW, H * 0.7);
      ctx.stroke();

      if (!reduce) {
        marks.forEach((m) => {
          m.x += m.speed * dt * (visible ? 1 : 0);
          m.a = Math.min(m.a + dt * 3, 1);
          let y = laneY[m.lane];
          const px = leftPad + plotW * m.x;
          if (m.x > 0.6) {
            const k = (m.x - 0.6) / 0.4;
            y = y * (1 - k) + nodeY * k;
          }
          if (px > convX) m.a -= dt * 1.6;
          if (m.a <= 0) return;
          ctx.globalAlpha = m.a * 0.9;
          ctx.fillStyle = TIERS[m.lane].color;
          ctx.beginPath();
          ctx.arc(px, y, m.r, 0, 7);
          ctx.fill();
          ctx.globalAlpha = m.a * 0.18;
          ctx.beginPath();
          ctx.moveTo(px, y);
          ctx.lineTo(px - 14, y);
          ctx.strokeStyle = TIERS[m.lane].color;
          ctx.lineWidth = m.r * 0.9;
          ctx.stroke();
          ctx.globalAlpha = 1;
        });
        marks = marks.filter((m) => m.a > 0 && m.x < 1.05);
      } else {
        TIERS.forEach((tt, i) => {
          for (let k = 0; k < 4; k++) {
            ctx.fillStyle = tt.color;
            ctx.globalAlpha = 0.8;
            ctx.beginPath();
            ctx.arc(leftPad + plotW * (0.1 + k * 0.16), laneY[i], 2.4, 0, 7);
            ctx.fill();
          }
        });
        ctx.globalAlpha = 1;
      }

      const pulse = reduce ? 0.6 : 0.55 + 0.12 * Math.sin(ts / 500);
      ctx.globalAlpha = pulse;
      ctx.fillStyle = "#d4ff3a";
      ctx.beginPath();
      ctx.arc(convX, nodeY, 6.5, 0, 7);
      ctx.fill();
      ctx.globalAlpha = 0.25;
      ctx.beginPath();
      ctx.arc(convX, nodeY, 13, 0, 7);
      ctx.strokeStyle = "#d4ff3a";
      ctx.lineWidth = 1;
      ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.fillStyle = "rgba(244,241,232,0.85)";
      ctx.font = "9px ui-monospace, monospace";
      ctx.fillText("CLUSTER", convX + 16, nodeY - 1);

      if (!reduce) {
        mAcc += dt;
        if (mAcc > 0.12) {
          mAcc = 0;
          momentum.push(momentum[momentum.length - 1] + (Math.random() - 0.42) * 0.05);
          if (momentum.length > 44) momentum.shift();
          momentum = momentum.map((v) => Math.max(0.12, Math.min(0.92, v)));
        }
      }
      const my0 = H * 0.74;
      const myH = H * 0.2;
      ctx.beginPath();
      momentum.forEach((v, i) => {
        const x = leftPad + plotW * (i / (momentum.length - 1));
        const y = my0 + myH * (1 - v);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.strokeStyle = "#d4ff3a";
      ctx.lineWidth = 1.6;
      ctx.stroke();
      const lv = momentum[momentum.length - 1];
      const ex = leftPad + plotW;
      const ey = my0 + myH * (1 - lv);
      ctx.fillStyle = "#d4ff3a";
      ctx.beginPath();
      ctx.arc(ex - 1, ey, 2.6, 0, 7);
      ctx.fill();
      ctx.fillStyle = "rgba(34,197,94,0.95)";
      ctx.font = "8px ui-monospace, monospace";
      ctx.fillText("↗ RISING", ex - 56, my0 - 2);

      if (!reduce) {
        if (marks.length < 22 && Math.random() < 0.5) spawn();
        raf = requestAnimationFrame(draw);
      }
    }

    fit();
    if (reduce) {
      draw(0);
    } else {
      for (let i = 0; i < 12; i++) marks.push({ lane: i % 4, x: Math.random(), speed: 0.04 + Math.random() * 0.05, r: 1.6 + Math.random() * 1.8, a: 1 });
      raf = requestAnimationFrame(draw);
    }

    const vio = new IntersectionObserver((es) => es.forEach((e) => (visible = e.isIntersecting)), { threshold: 0.05 });
    vio.observe(canvas);
    let rt = 0;
    const onResize = () => {
      window.clearTimeout(rt);
      rt = window.setTimeout(() => {
        fit();
        if (reduce) draw(0);
      }, 150);
    };
    window.addEventListener("resize", onResize);

    return () => {
      cancelAnimationFrame(raf);
      vio.disconnect();
      window.removeEventListener("resize", onResize);
      window.clearTimeout(rt);
    };
  }, []);

  return (
    <div className="lp-instrument">
      <span className="lp-corner tl" aria-hidden="true" />
      <span className="lp-corner br" aria-hidden="true" />
      <div className="lp-cap">
        <span>Lead-time reader</span>
        <span>science &rarr; market</span>
      </div>
      <canvas
        ref={ref}
        aria-label="Animated diagram: innovation signals flow across four lead-time tiers — science, patents, funding, market — and converge into a rising trend cluster."
      />
    </div>
  );
}
