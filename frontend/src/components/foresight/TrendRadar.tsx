"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { RadarBlip, RadarTier } from "@/lib/foresight";
import { VERTICALS } from "@/lib/types";

/**
 * Trend radar (#3). SVG polar layout: rings = lead-time tier (science outer →
 * market inner, i.e. earliest signal on the outside), segments = vertical,
 * blip size = cluster size, colour = vertical, momentum shown as an arrow.
 * Hover/tap a blip for a plain-language readout; click drills into the
 * cluster explorer for that vertical. Deliberately theme-agnostic via
 * currentColor + explicit vertical colours.
 */

const TIER_LABEL: Record<RadarTier, string> = {
  science: "Research",
  patent: "Patents",
  funding: "Funding",
  market: "Market",
};
// Outer → inner. Earliest lead-time tier sits on the outside (furthest ahead).
const TIER_ORDER: RadarTier[] = ["science", "patent", "funding", "market"];

const MOMENTUM_GLYPH: Record<string, string> = {
  rising: "↗", // ↗
  declining: "↘", // ↘
  stable: "→", // →
  unknown: "·", // ·
};

const SIZE = 640;
const CX = SIZE / 2;
const CY = SIZE / 2;
const R_OUTER = 290;
const R_INNER = 70;

function vColor(v: string): string {
  return VERTICALS.find((x) => x.id === v)?.color ?? "#94a3b8";
}

function momentumPlain(m: string, pp: number): string {
  if (m === "rising") return `rising (+${pp.toFixed(1)} pts share)`;
  if (m === "declining") return `cooling (${pp.toFixed(1)} pts share)`;
  if (m === "stable") return "holding steady";
  return "not enough recent data";
}

interface Placed extends RadarBlip {
  x: number;
  y: number;
  r: number;
}

export default function TrendRadar({
  blips,
  vertical,
}: {
  blips: RadarBlip[];
  vertical: string | null;
}) {
  const [active, setActive] = useState<Placed | null>(null);

  const placed = useMemo<Placed[]>(() => {
    // Verticals present, in canonical order → each gets an angular segment.
    const present: string[] = VERTICALS.map((v) => v.id).filter((id) =>
      blips.some((b) => b.vertical === id)
    );
    const segAngle = present.length ? (2 * Math.PI) / present.length : 2 * Math.PI;
    const segIndex = new Map<string, number>(present.map((v, i) => [v, i]));
    const ringGap = (R_OUTER - R_INNER) / TIER_ORDER.length;
    const maxSize = Math.max(1, ...blips.map((b) => b.size));

    // Deterministic jitter so co-located blips (same tier+vertical) fan out.
    const bucket = new Map<string, number>();
    return blips.map((b) => {
      const si = segIndex.get(b.vertical) ?? 0;
      const ti = Math.max(0, TIER_ORDER.indexOf(b.tier));
      const key = `${b.vertical}:${b.tier}`;
      const n = bucket.get(key) ?? 0;
      bucket.set(key, n + 1);
      const spread = present.length ? segAngle * 0.7 : Math.PI * 1.6;
      const a =
        -Math.PI / 2 +
        si * segAngle +
        segAngle / 2 +
        ((n % 5) - 2) * (spread / 6);
      const radius = R_OUTER - ti * ringGap - ringGap / 2 - (Math.floor(n / 5) * 6);
      return {
        ...b,
        x: CX + radius * Math.cos(a),
        y: CY + radius * Math.sin(a),
        r: 5 + 13 * Math.sqrt(b.size / maxSize),
      };
    });
  }, [blips]);

  const present = VERTICALS.filter((v) => blips.some((b) => b.vertical === v.id));
  const segAngle = present.length ? 360 / present.length : 360;

  return (
    <div className="radar-wrap">
      <div className="radar-stage">
        <svg
          viewBox={`0 0 ${SIZE} ${SIZE}`}
          className="radar-svg"
          role="img"
          aria-label="Trend radar: clusters by lead-time tier and vertical"
        >
          {/* Tier rings */}
          {TIER_ORDER.map((t, i) => {
            const rr =
              R_OUTER - i * ((R_OUTER - R_INNER) / TIER_ORDER.length);
            return (
              <g key={t}>
                <circle
                  cx={CX}
                  cy={CY}
                  r={rr}
                  className="radar-ring"
                  fill="none"
                />
                <text x={CX} y={CY - rr + 15} className="radar-ring-label">
                  {TIER_LABEL[t]}
                </text>
              </g>
            );
          })}
          <circle cx={CX} cy={CY} r={R_INNER} className="radar-ring" fill="none" />

          {/* Vertical segment spokes */}
          {present.map((v, i) => {
            const a = (-90 + i * segAngle) * (Math.PI / 180);
            return (
              <line
                key={v.id}
                x1={CX}
                y1={CY}
                x2={CX + R_OUTER * Math.cos(a)}
                y2={CY + R_OUTER * Math.sin(a)}
                className="radar-spoke"
              />
            );
          })}

          {/* Segment labels */}
          {present.map((v, i) => {
            const a = (-90 + (i + 0.5) * segAngle) * (Math.PI / 180);
            const lr = R_OUTER + 18;
            return (
              <text
                key={v.id}
                x={CX + lr * Math.cos(a)}
                y={CY + lr * Math.sin(a)}
                className="radar-seg-label"
                fill={v.color}
                textAnchor="middle"
              >
                {v.code}
              </text>
            );
          })}

          {/* Blips */}
          {placed.map((b) => (
            <g
              key={`${b.tier}-${b.id}`}
              className="radar-blip"
              onMouseEnter={() => setActive(b)}
              onMouseLeave={() => setActive((cur) => (cur?.id === b.id ? null : cur))}
              onClick={() => setActive(b)}
              tabIndex={0}
              onFocus={() => setActive(b)}
            >
              <circle
                cx={b.x}
                cy={b.y}
                r={b.r}
                fill={vColor(b.vertical)}
                fillOpacity={active && active.id === b.id ? 0.95 : 0.6}
                stroke={vColor(b.vertical)}
                strokeOpacity={0.9}
              />
              <text
                x={b.x}
                y={b.y + 4}
                className="radar-blip-glyph"
                textAnchor="middle"
              >
                {MOMENTUM_GLYPH[b.momentum]}
              </text>
            </g>
          ))}
        </svg>
      </div>

      {/* Readout panel — plain language, evidence one click away */}
      <aside className="radar-readout">
        {active ? (
          <div>
            <div className="radar-readout-tier" style={{ color: vColor(active.vertical) }}>
              {TIER_LABEL[active.tier]} · {active.vertical}
            </div>
            <h3 className="radar-readout-title">{active.label}</h3>
            <p className="radar-readout-line">
              {MOMENTUM_GLYPH[active.momentum]} {momentumPlain(active.momentum, active.sov_delta_pp)}
              {" · "}
              {active.size.toLocaleString("en-US")} signals from {active.n_sources} sources
            </p>
            {active.top_tags.length > 0 && (
              <div className="radar-tags">
                {active.top_tags.slice(0, 5).map((t) => (
                  <span key={t} className="radar-tag">
                    {t}
                  </span>
                ))}
              </div>
            )}
            {active.reps.length > 0 && (
              <ul className="radar-evidence">
                {active.reps.slice(0, 3).map((r) =>
                  r.source_url ? (
                    <li key={r.id}>
                      <a href={r.source_url} target="_blank" rel="noopener noreferrer">
                        {r.title}
                      </a>
                      {r.source_name ? <span className="radar-src"> — {r.source_name}</span> : null}
                    </li>
                  ) : (
                    <li key={r.id}>{r.title}</li>
                  )
                )}
              </ul>
            )}
            <Link
              href={`/trends/foresight/clusters?vertical=${active.vertical}`}
              className="radar-drill"
            >
              Explore {active.vertical} clusters →
            </Link>
          </div>
        ) : (
          <div className="radar-hint">
            <p className="radar-readout-title">How to read this radar</p>
            <p className="radar-readout-line">
              Each dot is a trend cluster. <strong>Rings</strong> are the innovation
              stages — research sits on the outside (earliest), the market in the
              centre (latest). <strong>Segments</strong> are industries.
              <strong> Bigger dots</strong> carry more signals; the arrow shows whether
              a trend is rising (↗), steady (→) or cooling (↘).
            </p>
            <p className="radar-readout-line radar-muted">
              Hover or tap a dot for the plain-language readout and its sources.
            </p>
          </div>
        )}
      </aside>

      <style>{`
        .radar-wrap { display: grid; grid-template-columns: minmax(0, 1fr) 320px; gap: 1.5rem; align-items: start; }
        @media (max-width: 900px) { .radar-wrap { grid-template-columns: 1fr; } }
        .radar-stage { min-width: 0; }
        .radar-svg { width: 100%; height: auto; display: block; overflow: visible; }
        .radar-ring { stroke: currentColor; stroke-opacity: 0.14; }
        .radar-ring-label { fill: currentColor; fill-opacity: 0.45; font-size: 11px; text-anchor: middle; letter-spacing: 0.04em; }
        .radar-spoke { stroke: currentColor; stroke-opacity: 0.08; }
        .radar-seg-label { font-size: 12px; font-weight: 600; letter-spacing: 0.03em; }
        .radar-blip { cursor: pointer; outline: none; }
        .radar-blip circle { transition: fill-opacity 0.12s ease; }
        .radar-blip:focus circle, .radar-blip:hover circle { fill-opacity: 0.95; }
        .radar-blip-glyph { font-size: 11px; fill: #0b0f14; font-weight: 700; pointer-events: none; }
        .radar-readout { border: 1px solid currentColor; border-color: color-mix(in srgb, currentColor 14%, transparent); border-radius: 14px; padding: 1.1rem 1.2rem; min-height: 260px; }
        .radar-readout-tier { font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; }
        .radar-readout-title { font-size: 1.05rem; font-weight: 700; margin: 0.35rem 0 0.5rem; }
        .radar-readout-line { font-size: 0.9rem; line-height: 1.5; opacity: 0.9; margin: 0 0 0.6rem; }
        .radar-muted { opacity: 0.6; }
        .radar-tags { display: flex; flex-wrap: wrap; gap: 0.3rem; margin-bottom: 0.7rem; }
        .radar-tag { font-size: 0.72rem; padding: 0.1rem 0.5rem; border-radius: 999px; background: color-mix(in srgb, currentColor 10%, transparent); }
        .radar-evidence { list-style: none; padding: 0; margin: 0 0 0.8rem; display: flex; flex-direction: column; gap: 0.45rem; }
        .radar-evidence a { font-size: 0.82rem; line-height: 1.35; text-decoration: underline; text-underline-offset: 2px; }
        .radar-src { opacity: 0.55; }
        .radar-drill { font-size: 0.85rem; font-weight: 600; text-decoration: none; }
        .radar-drill:hover { text-decoration: underline; }
      `}</style>
    </div>
  );
}
