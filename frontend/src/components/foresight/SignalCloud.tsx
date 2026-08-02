"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { dimensionStyle } from "@/lib/radar-shared";

/**
 * Die Signalwolke: jedes Signal eines Felds als eigener Punkt.
 *
 * Warum überhaupt — die aggregierte Ansicht zeigt 32 Zellen, also 32 Mittelwerte.
 * Ein Mittelwert verschweigt genau das, was eine Einschätzung tragfähig macht:
 * wie viel Masse dahintersteht, wie breit sie streut, ob ein H1 auf tausend
 * Signalen oder auf dreien beruht, und ob ein Feld sich gerade nach innen
 * bewegt. Die Wolke zeigt die Verteilung statt ihres Mittels.
 *
 * Die Platzierung kommt aus DEMSELBEN Klassifikator wie die Zellen
 * (`place_signal` in radar_horizons.py). Eine Zelle ist damit sichtbar das
 * Mittel ihrer Punkte, und die beiden Ansichten können nicht auseinanderlaufen.
 *
 * Canvas statt SVG: bei 4.000 Punkten kostet ein DOM-Knoten je Punkt spürbar
 * Zeit, und gebraucht wird von jedem Punkt nur ein Kreis. Die Beschriftung
 * liegt als SVG darüber, damit sie scharf bleibt und vorlesbar ist.
 */

export interface CloudPoint {
  id: number;
  d: number;      // Dimensionsindex
  s: 1 | 2 | 3;   // Stufe: 1 = H1 innen, 3 = H3 außen
  k: string;      // Art des Belegs
  y: number;      // Jahr
  t: string;      // Titel
  r: string[];    // Jurisdiktionen
}

export interface Cloud {
  label: string;
  points: CloudPoint[];
  dimensions: string[];
  n_total: number;
  n_placed: number;
  n_shown: number;
  n_unplaceable: number;
  sample_step: number;
  capped: boolean;
  per_dimension: Record<string, number>;
}

const W = 940;
const H = 520;
const CX = W / 2;
const CY = H - 34;
const R_MIN = 62;
const R_MAX = 452;

/** Deterministischer Streuwert aus der Signal-ID — stabil über alle Neuzeichnungen. */
function jitter(id: number, salt: number): number {
  const x = Math.sin(id * 12.9898 + salt * 78.233) * 43758.5453;
  return x - Math.floor(x);
}

function position(p: CloudPoint, nDims: number) {
  const span = Math.PI / nDims;
  const a0 = Math.PI + p.d * span;
  // 6 % Rand je Sektor, damit die Trennlinien sichtbar bleiben
  const ang = a0 + span * (0.06 + 0.88 * jitter(p.id, 1));
  const band = (R_MAX - R_MIN) / 3;
  const r = R_MIN + (p.s - 1) * band + band * (0.12 + 0.76 * jitter(p.id, 2));
  return { x: CX + Math.cos(ang) * r, y: CY + Math.sin(ang) * r };
}

export default function SignalCloud({
  radar,
  scope,
  label,
}: {
  radar: string;
  scope: string;
  label: string;
}) {
  const [cloud, setCloud] = useState<Cloud | null>(null);
  const [err, setErr] = useState(false);
  const [hover, setHover] = useState<CloudPoint | null>(null);
  const [since, setSince] = useState(0);
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    let live = true;
    setCloud(null);
    setErr(false);
    fetch(`/api/foresight/radar/cloud?radar=${radar}&scope=${scope}`)
      .then((r) => r.json())
      .then((d) => {
        if (!live) return;
        d?.error ? setErr(true) : setCloud(d);
      })
      .catch(() => live && setErr(true));
    return () => {
      live = false;
    };
  }, [radar, scope]);

  const shown = useMemo(
    () => (cloud ? cloud.points.filter((p) => p.y >= since) : []),
    [cloud, since]
  );

  const years = useMemo(() => {
    if (!cloud?.points.length) return [0, 0] as const;
    const ys = cloud.points.map((p) => p.y);
    return [Math.min(...ys), Math.max(...ys)] as const;
  }, [cloud]);

  useEffect(() => {
    const c = canvas.current;
    if (!c || !cloud) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    c.width = W * dpr;
    c.height = H * dpr;
    const g = c.getContext("2d");
    if (!g) return;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, W, H);
    const nD = cloud.dimensions.length;
    const newest = years[1] || new Date().getFullYear();

    for (const p of shown) {
      const { x, y } = position(p, nD);
      const age = Math.max(0, newest - p.y);
      // Jüngere Signale kräftiger: die Wolke bekommt Tiefe statt Gleichförmigkeit.
      const alpha = Math.max(0.14, 0.9 - age * 0.11);
      g.fillStyle = dimensionStyle(cloud.dimensions[p.d]).color;
      g.globalAlpha = hover && hover.id === p.id ? 1 : alpha;
      g.beginPath();
      g.arc(x, y, hover && hover.id === p.id ? 5.5 : 2.4, 0, Math.PI * 2);
      g.fill();
    }
    g.globalAlpha = 1;
  }, [cloud, shown, hover, years]);

  function pick(e: React.MouseEvent<HTMLCanvasElement>) {
    if (!cloud) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const mx = ((e.clientX - rect.left) / rect.width) * W;
    const my = ((e.clientY - rect.top) / rect.height) * H;
    let best: CloudPoint | null = null;
    let bestD = 12;
    for (const p of shown) {
      const { x, y } = position(p, cloud.dimensions.length);
      const d = Math.hypot(x - mx, y - my);
      if (d < bestD) {
        bestD = d;
        best = p;
      }
    }
    setHover(best);
  }

  if (err) {
    return <p className="sc-msg">The signal cloud could not be computed.</p>;
  }
  if (!cloud) {
    return <p className="sc-msg">Reading every signal in this field…</p>;
  }

  const nD = cloud.dimensions.length;

  return (
    <div className="sc">
      <div className="sc-bar">
        <span className="sc-k">Signal cloud</span>
        <span className="sc-v">{label}</span>
        <span className="sc-v">
          {shown.length.toLocaleString("en-US")} dots ·{" "}
          {cloud.n_placed.toLocaleString("en-US")} placeable signals
        </span>
        <label className="sc-since">
          from {since || years[0]}
          <input
            type="range"
            min={years[0]}
            max={Math.max(years[0], years[1] - 1)}
            value={since || years[0]}
            onChange={(e) => setSince(Number(e.target.value))}
            aria-label="Earliest year shown"
          />
        </label>
      </div>

      <div className="sc-stage">
        <canvas
          ref={canvas}
          className="sc-canvas"
          style={{ width: "100%", aspectRatio: `${W} / ${H}` }}
          onMouseMove={pick}
          onMouseLeave={() => setHover(null)}
          role="img"
          aria-label={`${cloud.n_placed} signals of ${label}, placed by dimension and stage`}
        />
        <svg className="sc-overlay" viewBox={`0 0 ${W} ${H}`} aria-hidden="true">
          {[1, 2, 3].map((s) => {
            const band = (R_MAX - R_MIN) / 3;
            const r = R_MIN + s * band;
            return (
              <path
                key={s}
                d={`M ${CX - r} ${CY} A ${r} ${r} 0 0 1 ${CX + r} ${CY}`}
                className="sc-ring"
              />
            );
          })}
          {[0, 1, 2].map((s) => {
            const band = (R_MAX - R_MIN) / 3;
            const r = R_MIN + s * band + band / 2;
            return (
              <text key={s} x={CX} y={CY - r + 4} className="sc-band">
                {`H${s + 1}`}
              </text>
            );
          })}
          {cloud.dimensions.map((d, i) => {
            const span = Math.PI / nD;
            const a = Math.PI + (i + 0.5) * span;
            const st = dimensionStyle(d);
            return (
              <g key={d}>
                <path
                  d={`M ${CX} ${CY} L ${CX + Math.cos(Math.PI + i * span) * R_MAX} ${
                    CY + Math.sin(Math.PI + i * span) * R_MAX
                  }`}
                  className="sc-spoke"
                />
                <text
                  x={CX + Math.cos(a) * (R_MAX + 20)}
                  y={CY + Math.sin(a) * (R_MAX + 20)}
                  className="sc-dim"
                  fill={st.color}
                  textAnchor="middle"
                >
                  {st.short} {cloud.per_dimension[d]?.toLocaleString("en-US")}
                </text>
              </g>
            );
          })}
        </svg>

        {hover ? (
          <div className="sc-tip" role="status">
            <span className="sc-tip-k">
              {dimensionStyle(cloud.dimensions[hover.d]).short} · H{hover.s} ·{" "}
              {hover.k} · {hover.y}
              {hover.r.length ? ` · ${hover.r.join(", ")}` : ""}
            </span>
            <span className="sc-tip-t">{hover.t}</span>
          </div>
        ) : (
          <p className="sc-hint">
            Every dot is one signal. Ring = what that signal itself evidences,
            sector = which dimension it speaks to, brightness = how recent.
            Point at one to read it.
          </p>
        )}
      </div>

      <p className="sc-foot">
        {cloud.n_unplaceable.toLocaleString("en-US")} of{" "}
        {cloud.n_total.toLocaleString("en-US")} signals in this field carry no
        placement — commentary, roundups and undated items — and are left out
        rather than parked somewhere.
        {cloud.capped
          ? ` Beyond that, every ${cloud.sample_step}${
              cloud.sample_step === 2 ? "nd" : cloud.sample_step === 3 ? "rd" : "th"
            } signal is drawn, evenly across the whole period — so the shape you
            see is the distribution, not the most recent slice.`
          : ""}
      </p>

      <style>{`
        .sc { margin-bottom: 1.4rem; }
        .sc-msg { font-family: var(--font-mono); font-size: 10px; letter-spacing: .18em; text-transform: uppercase; color: var(--color-muted); padding: 2rem 0; }
        .sc-bar { display: flex; flex-wrap: wrap; align-items: baseline; gap: .8rem; margin-bottom: .5rem; }
        .sc-k { font-family: var(--font-mono); font-size: 9px; letter-spacing: .2em; text-transform: uppercase; color: var(--color-accent); }
        .sc-v { font-family: var(--font-mono); font-size: 9px; letter-spacing: .12em; text-transform: uppercase; color: var(--color-muted); }
        .sc-since { margin-left: auto; display: flex; align-items: center; gap: .5rem; font-family: var(--font-mono); font-size: 9px; letter-spacing: .12em; text-transform: uppercase; color: var(--color-muted); }
        .sc-since input { width: 9rem; accent-color: var(--color-accent); }
        .sc-stage { position: relative; }
        .sc-canvas { display: block; cursor: crosshair; }
        .sc-overlay { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
        .sc-ring { fill: none; stroke: var(--color-border); stroke-width: 1; opacity: .55; }
        .sc-spoke { stroke: var(--color-border); stroke-width: 1; opacity: .35; }
        .sc-band { font-family: var(--font-mono); font-size: 10px; letter-spacing: .2em; fill: var(--color-paper); fill-opacity: .35; text-anchor: middle; }
        .sc-dim { font-family: var(--font-mono); font-size: 10px; letter-spacing: .16em; }
        .sc-tip { position: absolute; left: 0; right: 0; bottom: 0; display: grid; gap: .2rem; border: 1px solid var(--color-border); background: var(--color-card); padding: .5rem .7rem; }
        .sc-tip-k { font-family: var(--font-mono); font-size: 9px; letter-spacing: .14em; text-transform: uppercase; color: var(--color-accent); }
        .sc-tip-t { font-size: .85rem; line-height: 1.4; color: var(--color-paper); }
        .sc-hint { position: absolute; left: 0; right: 0; bottom: 0; font-size: .76rem; color: var(--color-muted); margin: 0; padding: .5rem .7rem; }
        .sc-foot { font-size: .75rem; color: var(--color-muted); margin: .6rem 0 0; max-width: 62em; line-height: 1.5; }
      `}</style>
    </div>
  );
}
