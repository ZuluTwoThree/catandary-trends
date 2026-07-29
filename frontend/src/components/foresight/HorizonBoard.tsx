"use client";

import { useMemo, useState } from "react";
import {
  ANY_REGION,
  DIMENSION_META,
  HORIZON_META,
  cellFor,
  type Horizon,
  type RadarCell,
  type RadarView,
} from "@/lib/radar-shared";

/**
 * Horizon board: one dataset, two readings.
 *
 *   matrix — the working view. Rows are technology fields, columns are
 *            dimensions, each cell an H-badge. Overlap is structurally
 *            impossible and a field's whole profile reads across one row, which
 *            is the actual strategic statement ("technologically H2, but
 *            regulatorily H3 in the EU").
 *   radar  — the presentation view. Rings are H1/H2/H3 (act in the centre),
 *            sectors are dimensions. Blips are numbered against a legend rather
 *            than labelled in place, so nothing collides and nothing has to be
 *            hovered to be identified.
 *
 * Every cell carries its rationale and its evidence, and a cell with too little
 * evidence stays empty instead of guessing.
 */

interface EvidenceItem {
  id: number;
  title: string;
  source_url: string | null;
  source_name: string | null;
}

const SIZE = 620;
const CX = SIZE / 2;
const CY = SIZE / 2;
// H1 innermost: the closer to the centre, the sooner you must act.
const RING_R: Record<Horizon, number> = { H1: 112, H2: 186, H3: 260 };
const DOT_R = 8;

type Mode = "matrix" | "radar";

export default function HorizonBoard({
  view,
  evidence,
}: {
  view: RadarView;
  evidence: Record<number, EvidenceItem>;
}) {
  const [mode, setMode] = useState<Mode>("matrix");
  const [region, setRegion] = useState<string>(
    view.regions.includes("GLOBAL") ? "GLOBAL" : view.regions[0] ?? "GLOBAL"
  );
  const [sel, setSel] = useState<{ scope: string; dimension: string } | null>(null);

  const selCell: RadarCell | null = sel
    ? cellFor(view, sel.scope, sel.dimension, region)
    : null;
  const selScope = sel ? view.scopes.find((s) => s.slug === sel.scope) : null;

  // Numbered legend — the polar view identifies blips by index, so a dot never
  // needs a label of its own and labels can never collide.
  const scopeIndex = useMemo(
    () => new Map(view.scopes.map((s, i) => [s.slug, i + 1])),
    [view.scopes]
  );

  const blips = useMemo(() => {
    const dims = view.dimensions;
    if (!dims.length) return [];
    const seg = (2 * Math.PI) / dims.length;
    const out: {
      key: string;
      scope: string;
      dimension: string;
      n: number;
      x: number;
      y: number;
      horizon: Horizon;
    }[] = [];
    dims.forEach((dim, di) => {
      // Group by ring first so placement can spread within (sector × ring).
      const byRing: Record<Horizon, string[]> = { H1: [], H2: [], H3: [] };
      view.scopes.forEach((s) => {
        const c = cellFor(view, s.slug, dim, region);
        if (c?.effective) byRing[c.effective].push(s.slug);
      });
      (Object.keys(byRing) as Horizon[]).forEach((h) => {
        const members = byRing[h];
        const base = -Math.PI / 2 + di * seg;
        const usable = seg * 0.82;
        const start = base + (seg - usable) / 2;
        members.forEach((slug, i) => {
          const t = members.length === 1 ? 0.5 : i / (members.length - 1);
          const a = start + usable * t;
          // Alternate radially when a cell is crowded: keeps circles apart even
          // if the arc gets tight.
          const r = RING_R[h] + (members.length > 5 ? (i % 2 ? 11 : -11) : 0);
          out.push({
            key: `${dim}-${slug}`,
            scope: slug,
            dimension: dim,
            n: scopeIndex.get(slug) ?? 0,
            x: CX + r * Math.cos(a),
            y: CY + r * Math.sin(a),
            horizon: h,
          });
        });
      });
    });
    return out;
  }, [view, region, scopeIndex]);

  const chip = (active: boolean) =>
    `font-mono text-[10px] uppercase tracking-[0.14em] px-3 py-1.5 border transition-colors ${
      active
        ? "text-accent border-accent bg-accent/10"
        : "text-muted border-border hover:text-paper"
    }`;

  const selEvidence = (selCell?.evidence ?? [])
    .map((id) => evidence[id])
    .filter(Boolean);

  return (
    <div className="hb">
      {/* Controls: view mode + jurisdiction. Two controls, no configuration duty. */}
      <div className="mb-5 flex flex-wrap items-center gap-4">
        <div className="flex flex-wrap gap-1">
          <button className={chip(mode === "matrix")} onClick={() => setMode("matrix")}>
            Matrix
          </button>
          <button className={chip(mode === "radar")} onClick={() => setMode("radar")}>
            Radar
          </button>
        </div>
        <div className="flex flex-wrap items-center gap-1">
          <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted mr-1">
            Jurisdiction
          </span>
          {view.regions.map((r) => (
            <button key={r} className={chip(region === r)} onClick={() => setRegion(r)}>
              {r}
            </button>
          ))}
        </div>
      </div>

      <div className="hb-grid">
        <div className="min-w-0">
          {mode === "matrix" ? (
            <div className="hb-scroll">
              <table className="hb-table">
                <caption className="sr-only">
                  Horizon per technology field and dimension for {region}
                </caption>
                <thead>
                  <tr>
                    <th scope="col" className="hb-th hb-th-field">
                      Technology field
                    </th>
                    {view.dimensions.map((d) => (
                      <th key={d} scope="col" className="hb-th" title={DIMENSION_META[d]?.blurb}>
                        {DIMENSION_META[d]?.label ?? d}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {view.scopes.map((s) => (
                    <tr key={s.slug}>
                      <th scope="row" className="hb-row-h">
                        <span className="hb-num">{scopeIndex.get(s.slug)}</span>
                        {s.label}
                      </th>
                      {view.dimensions.map((d) => {
                        const c = cellFor(view, s.slug, d, region);
                        const h = c?.effective ?? null;
                        const active =
                          sel?.scope === s.slug && sel?.dimension === d;
                        return (
                          <td key={d} className="hb-td">
                            <button
                              className={`hb-cell ${active ? "is-active" : ""}`}
                              onClick={() => setSel({ scope: s.slug, dimension: d })}
                              aria-label={`${s.label}, ${DIMENSION_META[d]?.label ?? d}: ${
                                h ? `${h} — ${HORIZON_META[h].action}` : "not enough evidence"
                              }`}
                            >
                              {h ? (
                                <span
                                  className="hb-badge"
                                  style={{
                                    color: HORIZON_META[h].color,
                                    borderColor: HORIZON_META[h].color,
                                  }}
                                >
                                  {h}
                                </span>
                              ) : (
                                <span className="hb-badge hb-badge-empty">–</span>
                              )}
                              {c?.override_horizon ? (
                                <span className="hb-ov" title="Analyst override">
                                  ✎
                                </span>
                              ) : null}
                              {c?.region === ANY_REGION ? (
                                <span
                                  className="hb-any"
                                  title="Not jurisdiction-specific — patent maturity is global"
                                >
                                  ·
                                </span>
                              ) : null}
                            </button>
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div>
              <svg
                viewBox={`0 0 ${SIZE} ${SIZE}`}
                className="hb-svg"
                role="group"
                aria-label={`Horizon radar for ${region}: rings are H1 to H3, sectors are dimensions`}
              >
                {(["H3", "H2", "H1"] as Horizon[]).map((h) => (
                  <g key={h}>
                    <circle cx={CX} cy={CY} r={RING_R[h]} className="hb-ring" fill="none" />
                    <text x={CX} y={CY - RING_R[h] + 14} className="hb-ring-label">
                      {h} · {HORIZON_META[h].action}
                    </text>
                  </g>
                ))}
                {view.dimensions.map((d, i) => {
                  const seg = 360 / view.dimensions.length;
                  const a = (-90 + i * seg) * (Math.PI / 180);
                  const la = (-90 + (i + 0.5) * seg) * (Math.PI / 180);
                  const lr = RING_R.H3 + 26;
                  return (
                    <g key={d}>
                      <line
                        x1={CX}
                        y1={CY}
                        x2={CX + RING_R.H3 * Math.cos(a)}
                        y2={CY + RING_R.H3 * Math.sin(a)}
                        className="hb-spoke"
                      />
                      <text
                        x={CX + lr * Math.cos(la)}
                        y={CY + lr * Math.sin(la)}
                        className="hb-seg-label"
                        textAnchor="middle"
                      >
                        {(DIMENSION_META[d]?.label ?? d).toUpperCase()}
                      </text>
                    </g>
                  );
                })}
                {blips.map((b) => {
                  const active =
                    sel?.scope === b.scope && sel?.dimension === b.dimension;
                  return (
                    <g
                      key={b.key}
                      className="hb-blip"
                      role="button"
                      tabIndex={0}
                      aria-label={`${b.n}: ${
                        view.scopes.find((s) => s.slug === b.scope)?.label
                      }, ${DIMENSION_META[b.dimension]?.label}, ${b.horizon}`}
                      onClick={() => setSel({ scope: b.scope, dimension: b.dimension })}
                      onFocus={() => setSel({ scope: b.scope, dimension: b.dimension })}
                    >
                      <circle cx={b.x} cy={b.y} r={14} fill="transparent" aria-hidden="true" />
                      <circle
                        cx={b.x}
                        cy={b.y}
                        r={DOT_R}
                        fill={HORIZON_META[b.horizon].color}
                        fillOpacity={active ? 1 : 0.72}
                        stroke={HORIZON_META[b.horizon].color}
                      />
                      <text x={b.x} y={b.y + 3.4} className="hb-blip-n" textAnchor="middle">
                        {b.n}
                      </text>
                    </g>
                  );
                })}
              </svg>
              <ol className="hb-legend">
                {view.scopes.map((s) => (
                  <li key={s.slug}>
                    <span className="hb-num">{scopeIndex.get(s.slug)}</span>
                    {s.label}
                  </li>
                ))}
              </ol>
            </div>
          )}
        </div>

        {/* Readout: why this cell says what it says, and what it is built on. */}
        <aside className="hb-readout" aria-live="polite">
          {selCell && selScope ? (
            <div>
              <div className="hb-readout-kicker">
                {DIMENSION_META[selCell.dimension]?.label ?? selCell.dimension}
                {selCell.region === ANY_REGION ? " · all jurisdictions" : ` · ${region}`}
              </div>
              <h3 className="hb-readout-title">{selScope.label}</h3>
              {selCell.effective ? (
                <p
                  className="hb-readout-h"
                  style={{ color: HORIZON_META[selCell.effective].color }}
                >
                  {selCell.effective} — {HORIZON_META[selCell.effective].action}
                </p>
              ) : (
                <p className="hb-readout-h hb-muted">Not enough evidence</p>
              )}
              <p className="hb-readout-line">{selCell.rationale}</p>
              {selCell.override_note ? (
                <p className="hb-readout-line hb-ovnote">
                  Analyst note: {selCell.override_note}
                </p>
              ) : null}
              <p className="hb-readout-meta">
                {selCell.n_signals.toLocaleString("en-US")} signals ·{" "}
                {selCell.method.replace(/_/g, " ")}
              </p>
              {selEvidence.length > 0 && (
                <ul className="hb-evidence">
                  {selEvidence.map((e) =>
                    e.source_url ? (
                      <li key={e.id}>
                        <a href={e.source_url} target="_blank" rel="noopener noreferrer">
                          {e.title}
                        </a>
                        {e.source_name ? <span className="hb-src"> — {e.source_name}</span> : null}
                      </li>
                    ) : (
                      <li key={e.id}>{e.title}</li>
                    )
                  )}
                </ul>
              )}
            </div>
          ) : (
            <div>
              <p className="hb-readout-title">How to read this</p>
              <p className="hb-readout-line">
                Each cell is a recommendation for one technology field on one
                dimension: <strong>H1 act now</strong>, <strong>H2 build</strong>,{" "}
                <strong>H3 watch</strong>. A field usually sits on different
                horizons per dimension — that difference is the point.
              </p>
              <p className="hb-readout-line hb-muted">
                Pick a cell for the reasoning and the sources behind it. A dash
                means the evidence was too thin to place it, so we don&apos;t.
              </p>
              <dl className="hb-key">
                {(["H1", "H2", "H3"] as Horizon[]).map((h) => (
                  <div key={h}>
                    <dt style={{ color: HORIZON_META[h].color }}>
                      {h} · {HORIZON_META[h].action}
                    </dt>
                    <dd>{HORIZON_META[h].blurb}</dd>
                  </div>
                ))}
              </dl>
            </div>
          )}
        </aside>
      </div>

      <style>{`
        .hb-grid { display: grid; grid-template-columns: minmax(0,1fr) 330px; gap: 1.5rem; align-items: start; }
        @media (max-width: 940px) { .hb-grid { grid-template-columns: 1fr; } }
        .hb-scroll { overflow-x: auto; }
        .hb-table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
        .hb-th { text-align: center; padding: 0.5rem 0.6rem; font-family: var(--font-mono); font-size: 9px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--color-muted); border-bottom: 1px solid var(--color-border); white-space: nowrap; }
        .hb-th-field { text-align: left; min-width: 14rem; }
        .hb-row-h { text-align: left; font-weight: 400; padding: 0.55rem 0.6rem; color: var(--color-paper); border-bottom: 1px solid color-mix(in srgb, var(--color-border) 55%, transparent); white-space: nowrap; }
        .hb-num { display: inline-flex; align-items: center; justify-content: center; width: 1.15rem; height: 1.15rem; margin-right: 0.5rem; border: 1px solid var(--color-border); font-family: var(--font-mono); font-size: 9px; color: var(--color-muted); }
        .hb-td { text-align: center; padding: 0.3rem 0.4rem; border-bottom: 1px solid color-mix(in srgb, var(--color-border) 55%, transparent); }
        .hb-cell { position: relative; display: inline-flex; align-items: center; gap: 2px; padding: 0.25rem 0.3rem; background: none; border: 1px solid transparent; cursor: pointer; }
        .hb-cell:hover, .hb-cell:focus-visible { border-color: var(--color-border); }
        .hb-cell.is-active { border-color: var(--color-accent); }
        .hb-badge { display: inline-block; min-width: 2.1rem; padding: 0.1rem 0.35rem; border: 1px solid; font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.08em; }
        .hb-badge-empty { color: var(--color-muted); border-color: var(--color-border); opacity: 0.7; }
        .hb-ov, .hb-any { font-size: 9px; color: var(--color-muted); }
        .hb-svg { width: 100%; height: auto; display: block; overflow: visible; }
        .hb-ring { stroke: currentColor; stroke-opacity: 0.16; }
        .hb-ring-label { fill: currentColor; fill-opacity: 0.5; font-size: 10px; text-anchor: middle; letter-spacing: 0.08em; font-family: var(--font-mono); text-transform: uppercase; }
        .hb-spoke { stroke: currentColor; stroke-opacity: 0.1; }
        .hb-seg-label { font-size: 10px; letter-spacing: 0.14em; font-family: var(--font-mono); fill: var(--color-muted); }
        .hb-blip { cursor: pointer; }
        .hb-blip-n { font-size: 9px; font-family: var(--font-mono); fill: #0a0c0a; font-weight: 700; pointer-events: none; }
        .hb-blip:focus-visible circle { stroke: var(--color-accent); stroke-width: 2px; }
        .hb-legend { list-style: none; padding: 0; margin: 1rem 0 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(13rem, 1fr)); gap: 0.35rem 1rem; font-size: 0.82rem; color: var(--color-text); }
        .hb-readout { border: 1px solid color-mix(in srgb, currentColor 14%, transparent); padding: 1.1rem 1.2rem; min-height: 300px; }
        .hb-readout-kicker { font-family: var(--font-mono); font-size: 9px; letter-spacing: 0.16em; text-transform: uppercase; color: var(--color-muted); }
        .hb-readout-title { font-size: 1.05rem; font-weight: 600; margin: 0.4rem 0 0.5rem; color: var(--color-paper); }
        .hb-readout-h { font-family: var(--font-mono); font-size: 0.85rem; letter-spacing: 0.1em; text-transform: uppercase; margin: 0 0 0.6rem; }
        .hb-readout-line { font-size: 0.88rem; line-height: 1.55; margin: 0 0 0.7rem; color: var(--color-text); }
        .hb-readout-meta { font-family: var(--font-mono); font-size: 9px; letter-spacing: 0.1em; text-transform: uppercase; color: var(--color-muted); margin: 0 0 0.7rem; }
        .hb-ovnote { border-left: 2px solid var(--color-accent); padding-left: 0.6rem; }
        .hb-muted { color: var(--color-muted); }
        .hb-evidence { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 0.45rem; }
        .hb-evidence a { font-size: 0.8rem; line-height: 1.35; text-decoration: underline; text-underline-offset: 2px; }
        .hb-src { opacity: 0.55; }
        .hb-key { margin: 1rem 0 0; }
        .hb-key dt { font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.1em; text-transform: uppercase; margin-top: 0.6rem; }
        .hb-key dd { margin: 0.15rem 0 0; font-size: 0.8rem; color: var(--color-muted); line-height: 1.45; }
      `}</style>
    </div>
  );
}
