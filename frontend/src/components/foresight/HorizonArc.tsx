"use client";

import { useMemo } from "react";
import {
  HORIZON_META,
  dimensionStyle,
  type Horizon,
  type RadarView,
  cellFor,
} from "@/lib/radar-shared";

/**
 * The horizon arc — a 180° instrument rather than a 360° dartboard.
 *
 * Why a half circle: the thing being drawn *is* a horizon. A baseline at the
 * bottom reads as "now", the bands above it as distance from now, and the whole
 * figure as a sextant arc or an engine gauge — a measuring instrument, which is
 * the claim the product makes. It also doubles the angular budget per sector
 * (30° per PESTEL wedge instead of 60° halved), which is what keeps blips apart
 * without jitter hacks.
 *
 * Encoding, deliberately single-purpose per channel:
 *   position (band)   → horizon: H1 nearest the baseline = act now
 *   sector            → dimension (PESTEL P/E/S/T/En/L, or the strategic four)
 *   colour            → the dimension's own identity colour, shared with
 *                       PestelBadge so a dimension looks the same everywhere
 *   number            → index into the legend, so no label can ever collide
 *
 * Blips are placed deterministically inside (sector × band) with a fixed angular
 * step, so two fields in the same cell cannot overlap — the failure mode of the
 * old radar, where 89 % of blips collided.
 */

const W = 1000;
const H = 560;
const CX = W / 2;
const CY = 500; // baseline sits low; the arc opens upward
const R_IN = 118;
const BAND = 104;
const R_H1 = R_IN;
const R_OUT = R_IN + 3 * BAND; // 430
/** Minimum arc distance between blip centres; dots are 22 px across. */
const MIN_ARC_GAP = 28;

const BANDS: { h: Horizon; r0: number; r1: number }[] = [
  { h: "H1", r0: R_H1, r1: R_H1 + BAND },
  { h: "H2", r0: R_H1 + BAND, r1: R_H1 + 2 * BAND },
  { h: "H3", r0: R_H1 + 2 * BAND, r1: R_OUT },
];

/** Upper semicircle: a runs from π (left) to 2π (right) with SVG's y-down. */
const pt = (r: number, a: number) => [CX + r * Math.cos(a), CY + r * Math.sin(a)];

function arcPath(r: number, a0: number, a1: number): string {
  const [x0, y0] = pt(r, a0);
  const [x1, y1] = pt(r, a1);
  return `M ${x0.toFixed(2)} ${y0.toFixed(2)} A ${r} ${r} 0 0 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`;
}

function wedgePath(r0: number, r1: number, a0: number, a1: number): string {
  const [x0, y0] = pt(r0, a0);
  const [x1, y1] = pt(r1, a0);
  const [x2, y2] = pt(r1, a1);
  const [x3, y3] = pt(r0, a1);
  return (
    `M ${x0.toFixed(2)} ${y0.toFixed(2)} L ${x1.toFixed(2)} ${y1.toFixed(2)} ` +
    `A ${r1} ${r1} 0 0 1 ${x2.toFixed(2)} ${y2.toFixed(2)} ` +
    `L ${x3.toFixed(2)} ${y3.toFixed(2)} ` +
    `A ${r0} ${r0} 0 0 0 ${x0.toFixed(2)} ${y0.toFixed(2)} Z`
  );
}

export interface ArcBlip {
  key: string;
  scope: string;
  dimension: string;
  n: number;
  x: number;
  y: number;
  r: number;
  a: number;
  horizon: Horizon;
  color: string;
}

export default function HorizonArc({
  view,
  region,
  selected,
  onSelect,
}: {
  view: RadarView;
  region: string;
  selected: { scope: string; dimension: string } | null;
  onSelect: (sel: { scope: string; dimension: string }) => void;
}) {
  const dims = view.dimensions;
  const seg = dims.length ? Math.PI / dims.length : Math.PI;

  const scopeIndex = useMemo(
    () => new Map(view.scopes.map((s, i) => [s.slug, i + 1])),
    [view.scopes]
  );

  const blips = useMemo<ArcBlip[]>(() => {
    const out: ArcBlip[] = [];
    dims.forEach((dim, di) => {
      const a0 = Math.PI + di * seg;
      const style = dimensionStyle(dim);
      BANDS.forEach((band) => {
        const members = view.scopes.filter((s) => {
          const c = cellFor(view, s.slug, dim, region);
          return c?.effective === band.h;
        });
        if (!members.length) return;
        // Row layout by available arc length. A fixed angular step breaks down
        // in the inner band of a six-sector radar: 8 fields in a 30° wedge at
        // r≈170 leaves ~10 px between centres for 22 px dots. So compute how
        // many fit per row at the *innermost* row radius (worst case) and add
        // rows until they do — up to three, which the 104 px band holds.
        const usable = seg * 0.8;
        const rowSets: number[][] = [
          [0.5],
          [0.32, 0.68],
          [0.2, 0.5, 0.8],
        ];
        const h = band.r1 - band.r0;
        let rows = rowSets[0];
        for (const cand of rowSets) {
          const rMin = band.r0 + h * Math.min(...cand);
          const capacity = Math.max(1, Math.floor((rMin * usable) / MIN_ARC_GAP));
          rows = cand;
          if (capacity * cand.length >= members.length) break;
        }
        const perRow = Math.ceil(members.length / rows.length);
        members.forEach((s, i) => {
          const rowIdx = Math.floor(i / perRow);
          const inRow = i % perRow;
          const rowLen = Math.min(perRow, members.length - rowIdx * perRow);
          const r = band.r0 + h * rows[Math.min(rowIdx, rows.length - 1)];
          const step = rowLen > 1 ? usable / (rowLen - 1) : 0;
          const a =
            rowLen === 1
              ? a0 + seg / 2
              : a0 + (seg - usable) / 2 + inRow * step;
          const [x, y] = pt(r, a);
          out.push({
            key: `${dim}:${s.slug}`,
            scope: s.slug,
            dimension: dim,
            n: scopeIndex.get(s.slug) ?? 0,
            x,
            y,
            r,
            a,
            horizon: band.h,
            color: style.color,
            _a0: a0,
            _r0: band.r0,
            _r1: band.r1,
          } as ArcBlip & { _a0: number; _r0: number; _r1: number });
        });
      });
    });

    // Relaxation pass. Row packing gets the layout close; this guarantees the
    // rest. Any pair closer than MIN_SEP is pushed apart — angularly inside its
    // own sector, radially inside its own band — so a blip can never leave the
    // cell that encodes its meaning while collisions still resolve. Converges in
    // a handful of passes at these densities; the loop is bounded regardless.
    const relax = out as (ArcBlip & { _a0: number; _r0: number; _r1: number })[];
    const MIN_SEP = 26;
    for (let iter = 0; iter < 60; iter++) {
      let moved = false;
      for (let i = 0; i < relax.length; i++) {
        for (let j = i + 1; j < relax.length; j++) {
          const A = relax[i];
          const B = relax[j];
          const dx = B.x - A.x;
          const dy = B.y - A.y;
          const d = Math.hypot(dx, dy) || 0.001;
          if (d >= MIN_SEP) continue;
          moved = true;
          const push = (MIN_SEP - d) / 2;
          // Separate along the arc first (cheap, keeps the band reading intact),
          // then radially if they are nearly on the same ray.
          const sign = A.a <= B.a ? 1 : -1;
          const dA = -sign * (push / Math.max(A.r, 1));
          const dB = sign * (push / Math.max(B.r, 1));
          const clampA = (b: typeof A, da: number) => {
            const lo = b._a0 + 0.06;
            const hi = b._a0 + seg - 0.06;
            b.a = Math.min(hi, Math.max(lo, b.a + da));
          };
          clampA(A, dA);
          clampA(B, dB);
          if (Math.abs(A.a - B.a) < 0.012) {
            A.r = Math.min(A._r1 - 14, Math.max(A._r0 + 14, A.r - push));
            B.r = Math.min(B._r1 - 14, Math.max(B._r0 + 14, B.r + push));
          }
          [A.x, A.y] = pt(A.r, A.a);
          [B.x, B.y] = pt(B.r, B.a);
        }
      }
      if (!moved) break;
    }
    return out;
  }, [view, region, dims, seg, scopeIndex]);

  const sel = selected
    ? blips.find(
        (b) => b.scope === selected.scope && b.dimension === selected.dimension
      )
    : null;

  return (
    <div className="arc-wrap">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="arc-svg"
        role="group"
        aria-label={`Horizon arc for ${region}: bands are H1 to H3 from the baseline outward, sectors are dimensions`}
      >
        <defs>
          <radialGradient id="arc-glow" cx="50%" cy="100%" r="75%">
            <stop offset="0%" stopColor="var(--color-accent)" stopOpacity="0.10" />
            <stop offset="55%" stopColor="var(--color-accent)" stopOpacity="0.02" />
            <stop offset="100%" stopColor="transparent" stopOpacity="0" />
          </radialGradient>
          <filter id="arc-grain">
            <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="3" />
            <feColorMatrix type="saturate" values="0" />
          </filter>
          <clipPath id="arc-clip">
            <path d={wedgePath(0, R_OUT + 60, Math.PI, 2 * Math.PI)} />
          </clipPath>
        </defs>

        {/* Atmosphere: a low glow at the baseline + a whisper of grain */}
        <path
          d={wedgePath(0, R_OUT + 40, Math.PI, 2 * Math.PI)}
          fill="url(#arc-glow)"
        />
        <g clipPath="url(#arc-clip)" opacity="0.05" style={{ mixBlendMode: "overlay" }}>
          <rect x="0" y="0" width={W} height={H} filter="url(#arc-grain)" />
        </g>

        {/* Sector wedges: faintest tint of the dimension's own colour */}
        {dims.map((dim, di) => {
          const a0 = Math.PI + di * seg;
          const style = dimensionStyle(dim);
          const isSel = sel?.dimension === dim;
          return (
            <path
              key={`wedge-${dim}`}
              d={wedgePath(R_IN, R_OUT, a0, a0 + seg)}
              fill={style.color}
              fillOpacity={isSel ? 0.075 : 0.028}
              className="arc-wedge"
            />
          );
        })}

        {/* Band arcs + graduation ticks along the outer rim */}
        {BANDS.map((band, bi) => (
          <g key={`band-${band.h}`} className="arc-band" style={{ animationDelay: `${bi * 90}ms` }}>
            <path d={arcPath(band.r1, Math.PI, 2 * Math.PI)} className="arc-ring" />
            <path
              d={arcPath(band.r0, Math.PI, 2 * Math.PI)}
              className="arc-ring arc-ring-inner"
            />
          </g>
        ))}
        {Array.from({ length: 37 }, (_, i) => {
          const a = Math.PI + (i / 36) * Math.PI;
          const major = i % 6 === 0;
          const [x0, y0] = pt(R_OUT, a);
          const [x1, y1] = pt(R_OUT + (major ? 15 : 7), a);
          return (
            <line
              key={`tick-${i}`}
              x1={x0}
              y1={y0}
              x2={x1}
              y2={y1}
              className={major ? "arc-tick arc-tick-major" : "arc-tick"}
            />
          );
        })}

        {/* Sector dividers */}
        {dims.map((dim, di) => {
          const a = Math.PI + di * seg;
          const [x0, y0] = pt(R_IN, a);
          const [x1, y1] = pt(R_OUT, a);
          return <line key={`div-${dim}`} x1={x0} y1={y0} x2={x1} y2={y1} className="arc-div" />;
        })}
        <line
          x1={CX - R_OUT}
          y1={CY}
          x2={CX + R_OUT}
          y2={CY}
          className="arc-div arc-baseline"
        />

        {/* Sector labels, set tangentially outside the rim like a dial face */}
        {dims.map((dim, di) => {
          const a = Math.PI + di * seg + seg / 2;
          const style = dimensionStyle(dim);
          const [x, y] = pt(R_OUT + 40, a);
          const deg = (a * 180) / Math.PI + 90;
          return (
            <text
              key={`lab-${dim}`}
              x={x}
              y={y}
              className="arc-sector-label"
              fill={style.color}
              textAnchor="middle"
              transform={`rotate(${deg} ${x} ${y})`}
            >
              {style.short}
            </text>
          );
        })}

        {/* Band labels, stacked on the vertical axis */}
        {BANDS.map((band) => {
          const [, y] = pt((band.r0 + band.r1) / 2, 1.5 * Math.PI);
          return (
            <g key={`bl-${band.h}`}>
              <text x={CX} y={y + 4} className="arc-band-label">
                {band.h}
              </text>
              <text x={CX} y={y + 20} className="arc-band-sub">
                {HORIZON_META[band.h].action.toUpperCase()}
              </text>
            </g>
          );
        })}

        {/* Crosshair on the selected blip — the instrument taking a reading */}
        {sel && (
          <g className="arc-cross">
            <line
              x1={CX + R_IN * Math.cos(sel.a)}
              y1={CY + R_IN * Math.sin(sel.a)}
              x2={CX + (R_OUT + 22) * Math.cos(sel.a)}
              y2={CY + (R_OUT + 22) * Math.sin(sel.a)}
            />
            <path d={arcPath(sel.r, Math.PI, 2 * Math.PI)} className="arc-cross-arc" />
          </g>
        )}

        {/* Blips */}
        {blips.map((b, i) => {
          const active =
            selected?.scope === b.scope && selected?.dimension === b.dimension;
          return (
            <g
              key={b.key}
              className={`arc-blip ${active ? "is-active" : ""}`}
              style={{ animationDelay: `${300 + i * 26}ms` }}
              role="button"
              tabIndex={0}
              aria-label={`${b.n}: ${
                view.scopes.find((s) => s.slug === b.scope)?.label
              }, ${dimensionStyle(b.dimension).label}, ${b.horizon} ${
                HORIZON_META[b.horizon].action
              }`}
              onClick={() => onSelect({ scope: b.scope, dimension: b.dimension })}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelect({ scope: b.scope, dimension: b.dimension });
                }
              }}
            >
              <circle cx={b.x} cy={b.y} r={20} fill="transparent" aria-hidden="true" />
              {active && <circle cx={b.x} cy={b.y} r={17} className="arc-halo" stroke={b.color} />}
              <circle
                cx={b.x}
                cy={b.y}
                r={11}
                fill={b.color}
                fillOpacity={active ? 1 : 0.82}
                stroke={b.color}
                strokeWidth={1.5}
                className="arc-dot"
              />
              <text x={b.x} y={b.y + 3.6} className="arc-dot-n" textAnchor="middle">
                {b.n}
              </text>
              {/* Bei wenigen Feldern steht der Name direkt am Punkt. Eine Zahl
                  zwingt sonst bei jedem Blick in die Legende — bei zwei oder
                  drei verglichenen Feldern ist das reine Reibung. Ab vier
                  Feldern kollidieren die Namen, dann bleibt es bei der Zahl. */}
              {view.scopes.length <= 3 && (
                <text
                  x={b.x}
                  y={b.y - 16}
                  className="arc-dot-label"
                  textAnchor="middle"
                >
                  {view.scopes.find((s) => s.slug === b.scope)?.label}
                </text>
              )}
            </g>
          );
        })}

        {/* Baseline caption */}
        <text x={CX} y={CY + 32} className="arc-now" textAnchor="middle">
          — TODAY · {region} —
        </text>
      </svg>

      <style>{`
        .arc-wrap { position: relative; }
        .arc-svg { width: 100%; height: auto; display: block; overflow: visible; }

        .arc-ring { fill: none; stroke: var(--color-paper); stroke-opacity: 0.17; stroke-width: 1; }
        .arc-ring-inner { stroke-opacity: 0.09; }
        .arc-band path { stroke-dasharray: 1600; animation: arc-draw 1.1s cubic-bezier(.2,.7,.2,1) backwards; }
        @keyframes arc-draw { from { stroke-dashoffset: 1600; } to { stroke-dashoffset: 0; } }

        .arc-tick { stroke: var(--color-paper); stroke-opacity: 0.16; stroke-width: 1; }
        .arc-tick-major { stroke-opacity: 0.42; stroke-width: 1.5; }
        .arc-div { stroke: var(--color-paper); stroke-opacity: 0.1; stroke-width: 1; }
        .arc-baseline { stroke-opacity: 0.3; }
        .arc-wedge { transition: fill-opacity .25s ease; }

        .arc-sector-label {
          font-family: var(--font-mono); font-size: 13px; letter-spacing: 0.26em;
          font-weight: 500;
        }
        .arc-dot-label {
          font-family: var(--font-mono); font-size: 8.5px; letter-spacing: .08em;
          text-transform: uppercase; fill: var(--color-paper); fill-opacity: .75;
          paint-order: stroke; stroke: var(--color-ink); stroke-width: 3px;
          stroke-linejoin: round; pointer-events: none;
        }
        .arc-band-label {
          font-family: var(--font-display); font-size: 20px; font-style: italic;
          fill: var(--color-paper); fill-opacity: 0.5; text-anchor: middle;
        }
        .arc-band-sub {
          font-family: var(--font-mono); font-size: 8.5px; letter-spacing: 0.2em;
          fill: var(--color-paper); fill-opacity: 0.3; text-anchor: middle;
        }
        .arc-now {
          font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.32em;
          fill: var(--color-accent); fill-opacity: 0.8;
        }

        .arc-cross line { stroke: var(--color-accent); stroke-opacity: 0.5; stroke-width: 1; stroke-dasharray: 3 5; }
        .arc-cross-arc { fill: none; stroke: var(--color-accent); stroke-opacity: 0.3; stroke-width: 1; stroke-dasharray: 3 5; }

        .arc-blip { cursor: pointer; animation: arc-pop .5s cubic-bezier(.2,1.3,.4,1) backwards; }
        @keyframes arc-pop { from { opacity: 0; transform: scale(.4); } to { opacity: 1; transform: none; } }
        .arc-blip .arc-dot { transition: transform .18s cubic-bezier(.2,.9,.3,1.3), fill-opacity .18s ease; transform-origin: center; transform-box: fill-box; }
        .arc-blip:hover .arc-dot { transform: scale(1.22); fill-opacity: 1; }
        .arc-blip:focus { outline: none; }
        .arc-blip:focus-visible .arc-dot { stroke: var(--color-accent); stroke-width: 3; }
        .arc-blip.is-active .arc-dot { transform: scale(1.15); }
        .arc-halo { fill: none; stroke-width: 1.5; stroke-opacity: 0.45; animation: arc-ping 2.4s ease-out infinite; transform-origin: center; transform-box: fill-box; }
        @keyframes arc-ping { 0% { transform: scale(.85); stroke-opacity: .55; } 70%,100% { transform: scale(1.5); stroke-opacity: 0; } }
        .arc-dot-n { font-family: var(--font-mono); font-size: 10px; font-weight: 700; fill: var(--color-ink); pointer-events: none; }

        @media (prefers-reduced-motion: reduce) {
          .arc-band path, .arc-blip { animation: none; }
          .arc-halo { animation: none; stroke-opacity: .5; }
          .arc-blip .arc-dot { transition: none; }
        }
      `}</style>
    </div>
  );
}
