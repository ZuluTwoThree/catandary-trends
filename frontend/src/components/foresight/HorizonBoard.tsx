"use client";

import { useMemo, useState } from "react";
import {
  ANY_REGION,
  HORIZON_META,
  cellFor,
  dimensionStyle,
  type Horizon,
  type RadarCell,
  type RadarView,
  regionLabel,
  BASIS_META,
} from "@/lib/radar-shared";
import HorizonArc from "./HorizonArc";
import FieldReadout, { ReadoutStrip } from "./FieldReadout";
import FieldIdentity from "./FieldIdentity";
import SignalCloud from "./SignalCloud";

/**
 * The instrument: one dataset, two readings, one readout.
 *
 *   arc    — a 180° horizon dial. Bands are H1/H2/H3 from the baseline outward,
 *            sectors are the dimensions (PESTEL or strategic). Blips are
 *            numbered against the legend, so nothing needs a label in place and
 *            nothing can collide.
 *   matrix — the same cells as a table. Rows are fields, columns dimensions.
 *            Overlap is impossible by construction and a field's whole profile
 *            reads across one row — which is the actual strategic statement.
 *
 * A cell with too little evidence stays empty rather than guessing, and every
 * placement carries its reasoning and its sources in the readout.
 */

interface EvidenceItem {
  id: number;
  title: string;
  source_url: string | null;
  source_name: string | null;
}

type Mode = "arc" | "matrix" | "cloud";

export default function HorizonBoard({
  view,
  evidence,
}: {
  view: RadarView;
  evidence: Record<number, EvidenceItem>;
}) {
  const [mode, setMode] = useState<Mode>("arc");
  // Eine Entscheidung gilt immer für EINEN Markt. Die Weltspalte ist die
  // Vereinigung aller Signale und damit die großzügigste Lesart — als
  // Startansicht wäre der erste Eindruck systematisch der rosigste. Sie bleibt
  // einen Klick entfernt, aber die Bühne gehört einer benannten Jurisdiktion.
  const [region, setRegion] = useState<string>(
    view.regions.find((r) => r !== "GLOBAL") ?? view.regions[0] ?? "GLOBAL"
  );
  const [sel, setSel] = useState<{ scope: string; dimension: string } | null>(null);

  const selCell: RadarCell | null = sel
    ? cellFor(view, sel.scope, sel.dimension, region)
    : null;
  const selScope = sel ? view.scopes.find((s) => s.slug === sel.scope) : null;
  const selStyle = sel ? dimensionStyle(sel.dimension) : null;

  const scopeIndex = useMemo(
    () => new Map(view.scopes.map((s, i) => [s.slug, i + 1])),
    [view.scopes]
  );

  // Coverage is a trust statement, not decoration: how much of the grid the
  // engine was willing to place at all.
  const coverage = useMemo(() => {
    const rel = view.cells.filter(
      (c) => c.region === region || c.region === ANY_REGION
    );
    const placed = rel.filter((c) => c.effective).length;
    return { placed, total: rel.length };
  }, [view.cells, region]);

  const selEvidence = (selCell?.evidence ?? [])
    .map((id) => evidence[id])
    .filter(Boolean);

  return (
    <div className="hb">
      {/* ---- Instrument switches -------------------------------------- */}
      <div className="hb-switches">
        <div className="hb-switch-group" role="group" aria-label="View">
          {(["arc", "matrix", "cloud"] as Mode[]).map((m) => (
            <button
              key={m}
              className={`hb-switch ${mode === m ? "is-on" : ""}`}
              onClick={() => setMode(m)}
              aria-pressed={mode === m}
            >
              {m === "arc" ? "Arc" : m === "matrix" ? "Matrix" : "Signals"}
            </button>
          ))}
        </div>
        <div className="hb-switch-group" role="group" aria-label="Jurisdiction">
          <span className="hb-switch-legend">Jurisdiction</span>
          {view.regions.map((r) => (
            <button
              key={r}
              className={`hb-switch ${region === r ? "is-on" : ""}`}
              onClick={() => setRegion(r)}
              aria-pressed={region === r}
            >
              {regionLabel(r)}
            </button>
          ))}
        </div>
        <span className="hb-coverage">
          {coverage.placed}/{coverage.total} placed
        </span>
      </div>

      {(() => {
        const rs = view.readouts ?? [];
        if (!rs.length) return null;
        const activeSlug = sel?.scope ?? view.scopes[0]?.slug ?? null;
        const pick = rs.find((r) => r.scope_slug === activeSlug) ?? rs[0];
        return (
          <>
            <ReadoutStrip
              readouts={rs}
              rows={Object.fromEntries(
                view.scopes.map((sc) => [
                  sc.slug,
                  {
                    momentum: sc.meta?.momentum,
                    delta: sc.meta?.sov_delta_pp,
                    // Das Horizont-Profil in der gewählten Jurisdiktion — vier
                    // Zeichenpaare, die Felder tatsächlich unterscheiden. Der
                    // Haltungssatz tat das nicht: vier Cluster desselben
                    // Mega-Trends bekamen denselben.
                    profile: view.dimensions
                      .map((d) => {
                        const c = cellFor(view, sc.slug, d, region);
                        return `${dimensionStyle(d).short} ${c?.effective ?? "–"}`;
                      })
                      .join("  ·  "),
                  },
                ])
              )}
              selected={pick.scope_slug}
              onSelect={(slug) =>
                setSel({ scope: slug, dimension: view.dimensions[0] })
              }
            />
            {(() => {
              const meta = view.scopes.find(
                (s) => s.slug === pick.scope_slug
              )?.meta;
              return meta ? <FieldIdentity meta={meta} /> : null;
            })()}
            <FieldReadout readout={pick} compact={rs.length > 1} />
          </>
        );
      })()}

      <div className="hb-grid">
        <div className="hb-stage">
          {mode === "cloud" ? (
            // Die Wolke braucht ein Feld, keine Jurisdiktion: sie zeigt JEDES
            // Signal des Felds mit der Stufe, die es selbst belegt.
            <SignalCloud
              radar={view.config.slug}
              scope={sel?.scope ?? view.scopes[0]?.slug ?? ""}
              label={
                view.scopes.find((s) => s.slug === (sel?.scope ?? view.scopes[0]?.slug))
                  ?.label ?? ""
              }
            />
          ) : mode === "arc" ? (
            <HorizonArc
              view={view}
              region={region}
              selected={sel}
              onSelect={setSel}
            />
          ) : (
            <div className="hb-scroll">
              <table className="hb-table">
                <caption className="sr-only">
                  Horizon per technology field and dimension for {regionLabel(region)}
                </caption>
                <thead>
                  <tr>
                    <th scope="col" className="hb-th hb-th-field">
                      Field
                    </th>
                    {view.dimensions.map((d) => {
                      const st = dimensionStyle(d);
                      return (
                        <th key={d} scope="col" className="hb-th" title={st.blurb}>
                          <span style={{ color: st.color }}>{st.short}</span>
                        </th>
                      );
                    })}
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
                        const active = sel?.scope === s.slug && sel?.dimension === d;
                        return (
                          <td key={d} className="hb-td">
                            <button
                              className={`hb-cell ${active ? "is-active" : ""}`}
                              onClick={() => setSel({ scope: s.slug, dimension: d })}
                              aria-label={`${s.label}, ${dimensionStyle(d).label}: ${
                                h ? `${h} ${HORIZON_META[h].action}` : "not enough evidence"
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
                                <span
                                  className="hb-badge hb-badge-empty"
                                  title={
                                    c?.basis && BASIS_META[c.basis]
                                      ? BASIS_META[c.basis].label
                                      : "Too little evidence to place"
                                  }
                                >
                                  {c?.basis && BASIS_META[c.basis]
                                    ? BASIS_META[c.basis].short
                                    : "–"}
                                </span>
                              )}
                              {c && c.previous !== undefined &&
                              c.previous !== c.effective ? (
                                <span
                                  className="hb-delta"
                                  title={`Previous run: ${c.previous ?? "no call"}`}
                                >
                                  {c.previous === null
                                    ? "new"
                                    : `was ${c.previous}`}
                                </span>
                              ) : null}
                              {c?.override_horizon ? (
                                <span className="hb-mark" title="Analyst override">✎</span>
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
          )}

          {/* Legend — editorial, doubles as the click target list */}
          <ol className="hb-legend">
            {view.scopes.map((s) => {
              const on = sel?.scope === s.slug;
              return (
                <li key={s.slug}>
                  <button
                    className={`hb-legend-btn ${on ? "is-on" : ""}`}
                    onClick={() =>
                      setSel({
                        scope: s.slug,
                        dimension: sel?.dimension ?? view.dimensions[0],
                      })
                    }
                  >
                    <span className="hb-num">{scopeIndex.get(s.slug)}</span>
                    <span className="hb-legend-label">{s.label}</span>
                  </button>
                </li>
              );
            })}
          </ol>
        </div>

        {/* ---- Readout ------------------------------------------------- */}
        <aside className="hb-readout" aria-live="polite">
          {selCell && selScope && selStyle ? (
            <div className="hb-read">
              <div className="hb-read-head" style={{ borderColor: selStyle.color }}>
                <span className="hb-read-dim" style={{ color: selStyle.color }}>
                  {selStyle.short} · {selStyle.label}
                </span>
                <span className="hb-read-region">
                  {selCell.region === ANY_REGION ? "all jurisdictions" : regionLabel(region)}
                </span>
              </div>
              <h3 className="hb-read-title">{selScope.label}</h3>
              {selCell.effective ? (
                <p className="hb-read-h">
                  <span
                    className="hb-read-hbadge"
                    style={{
                      color: HORIZON_META[selCell.effective].color,
                      borderColor: HORIZON_META[selCell.effective].color,
                    }}
                  >
                    {selCell.effective}
                  </span>
                  <span className="hb-read-action">
                    {HORIZON_META[selCell.effective].action}
                  </span>
                </p>
              ) : (
                <p className="hb-read-h">
                  <span className="hb-read-hbadge hb-badge-empty">–</span>
                  <span className="hb-read-action hb-muted">Not enough evidence</span>
                </p>
              )}
              <p className="hb-read-line">{selCell.rationale}</p>
              {selCell.override_note ? (
                <p className="hb-read-line hb-ovnote">
                  Analyst note: {selCell.override_note}
                </p>
              ) : null}
              <p className="hb-read-meta">
                {selCell.n_signals.toLocaleString("en-US")} signals ·{" "}
                {selCell.method.replace(/_/g, " ")}
              </p>
              {selEvidence.length > 0 && (
                <>
                  <p className="hb-read-evh">Evidence</p>
                  <ul className="hb-evidence">
                    {selEvidence.map((e) =>
                      e.source_url ? (
                        <li key={e.id}>
                          <a href={e.source_url} target="_blank" rel="noopener noreferrer">
                            {e.title}
                          </a>
                          {e.source_name ? (
                            <span className="hb-src"> — {e.source_name}</span>
                          ) : null}
                        </li>
                      ) : (
                        <li key={e.id}>{e.title}</li>
                      )
                    )}
                  </ul>
                </>
              )}
            </div>
          ) : (
            <div className="hb-read">
              <p className="hb-read-evh">Reading the instrument</p>
              <p className="hb-read-line">
                Distance from the baseline is <em>how soon you have to act</em>.
                Sectors are the dimensions. A field usually sits on different
                horizons per dimension — that difference is the whole point.
              </p>
              <dl className="hb-key">
                {(["H1", "H2", "H3"] as Horizon[]).map((h) => (
                  <div key={h}>
                    <dt style={{ color: HORIZON_META[h].color }}>
                      {h} — {HORIZON_META[h].action}
                    </dt>
                    <dd>{HORIZON_META[h].blurb}</dd>
                  </div>
                ))}
              </dl>
              <p className="hb-read-line hb-muted">
                Pick any blip or cell for the reasoning and the sources behind it.
                A dash means the evidence was too thin to place it — so we
                don&apos;t.
              </p>
            </div>
          )}
        </aside>
      </div>

      <style>{`
        .hb-switches { display: flex; flex-wrap: wrap; align-items: center; gap: .5rem 1.6rem; padding-bottom: .9rem; border-bottom: 1px solid var(--color-border); margin-bottom: 1.6rem; }
        .hb-switch-group { display: flex; align-items: center; gap: .35rem; }
        .hb-switch-legend { font-family: var(--font-mono); font-size: 9px; letter-spacing: .2em; text-transform: uppercase; color: var(--color-muted); margin-right: .3rem; }
        .hb-switch { font-family: var(--font-mono); font-size: 10px; letter-spacing: .16em; text-transform: uppercase; padding: .4rem .8rem; border: 1px solid var(--color-border); background: transparent; color: var(--color-muted); cursor: pointer; transition: color .18s, border-color .18s, background .18s; }
        .hb-switch:hover { color: var(--color-paper); border-color: var(--color-paper); }
        .hb-switch.is-on { color: var(--color-ink); background: var(--color-accent); border-color: var(--color-accent); font-weight: 600; }
        .hb-coverage { margin-left: auto; font-family: var(--font-mono); font-size: 9px; letter-spacing: .18em; text-transform: uppercase; color: var(--color-muted); }

        .hb-grid { display: grid; grid-template-columns: minmax(0,1fr) 340px; gap: 2rem; align-items: start; }
        @media (max-width: 1000px) { .hb-grid { grid-template-columns: 1fr; } }
        .hb-stage { min-width: 0; }

        .hb-legend { list-style: none; padding: 0; margin: 1.2rem 0 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(12rem, 1fr)); gap: .1rem .8rem; border-top: 1px solid var(--color-border); padding-top: .9rem; }
        .hb-legend-btn { display: flex; align-items: center; gap: .5rem; width: 100%; padding: .3rem .2rem; background: none; border: 0; cursor: pointer; text-align: left; color: var(--color-text); font-size: .82rem; transition: color .15s; }
        .hb-legend-btn:hover, .hb-legend-btn.is-on { color: var(--color-accent); }
        .hb-legend-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .hb-num { display: inline-flex; align-items: center; justify-content: center; width: 1.25rem; height: 1.25rem; flex: none; border: 1px solid var(--color-border); font-family: var(--font-mono); font-size: 9px; color: var(--color-muted); }

        .hb-scroll { overflow-x: auto; }
        .hb-table { width: 100%; border-collapse: collapse; font-size: .9rem; }
        .hb-th { text-align: center; padding: .55rem .6rem; font-family: var(--font-mono); font-size: 9px; letter-spacing: .18em; border-bottom: 1px solid var(--color-border); white-space: nowrap; }
        .hb-th-field { text-align: left; min-width: 13rem; color: var(--color-muted); }
        .hb-row-h { text-align: left; font-weight: 400; padding: .6rem; color: var(--color-paper); border-bottom: 1px solid color-mix(in srgb, var(--color-border) 55%, transparent); white-space: nowrap; display: flex; align-items: center; gap: .5rem; }
        .hb-td { text-align: center; padding: .3rem .4rem; border-bottom: 1px solid color-mix(in srgb, var(--color-border) 55%, transparent); }
        .hb-cell { display: inline-flex; align-items: center; gap: 2px; padding: .25rem .3rem; background: none; border: 1px solid transparent; cursor: pointer; }
        .hb-cell:hover, .hb-cell:focus-visible { border-color: var(--color-border); }
        .hb-cell.is-active { border-color: var(--color-accent); }
        .hb-badge { display: inline-block; min-width: 2.1rem; padding: .12rem .4rem; border: 1px solid; font-family: var(--font-mono); font-size: 10px; letter-spacing: .08em; }
        .hb-badge-empty { color: var(--color-muted); border-color: var(--color-border); opacity: .7; }
        .hb-mark { font-size: 9px; color: var(--color-muted); }

        .hb-readout { position: sticky; top: 1.5rem; border: 1px solid var(--color-border); background: var(--color-card); }
        .hb-read { padding: 1.25rem 1.35rem; }
        .hb-read-head { display: flex; justify-content: space-between; align-items: baseline; gap: .8rem; border-left: 2px solid; padding-left: .65rem; margin-bottom: .8rem; }
        .hb-read-dim { font-family: var(--font-mono); font-size: 9.5px; letter-spacing: .2em; text-transform: uppercase; }
        .hb-badge-empty { font-size: 8.5px !important; letter-spacing: .04em; padding: .2rem .3rem; opacity: .65; text-transform: uppercase; }
        .hb-delta { display: block; font-family: var(--font-mono); font-size: 8px; letter-spacing: .1em; text-transform: uppercase; color: var(--color-accent); margin-top: .2rem; }
        .hb-read-region { font-family: var(--font-mono); font-size: 9px; letter-spacing: .16em; text-transform: uppercase; color: var(--color-muted); }
        .hb-read-title { font-family: var(--font-display); font-size: 1.4rem; line-height: 1.15; color: var(--color-paper); margin: 0 0 .7rem; letter-spacing: -.01em; }
        .hb-read-h { display: flex; align-items: center; gap: .6rem; margin: 0 0 .9rem; }
        .hb-read-hbadge { display: inline-block; min-width: 2.3rem; text-align: center; padding: .18rem .45rem; border: 1px solid; font-family: var(--font-mono); font-size: 12px; letter-spacing: .1em; }
        .hb-read-action { font-family: var(--font-mono); font-size: 10px; letter-spacing: .2em; text-transform: uppercase; color: var(--color-paper); }
        .hb-read-line { font-size: .875rem; line-height: 1.6; margin: 0 0 .8rem; color: var(--color-text); }
        .hb-read-line em { color: var(--color-paper); font-style: italic; }
        .hb-read-meta { font-family: var(--font-mono); font-size: 9px; letter-spacing: .14em; text-transform: uppercase; color: var(--color-muted); margin: 0 0 1rem; padding-top: .7rem; border-top: 1px dashed var(--color-border); }
        .hb-read-evh { font-family: var(--font-mono); font-size: 9px; letter-spacing: .22em; text-transform: uppercase; color: var(--color-accent); margin: 0 0 .6rem; }
        .hb-ovnote { border-left: 2px solid var(--color-accent); padding-left: .6rem; }
        .hb-muted { color: var(--color-muted); }
        .hb-evidence { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: .55rem; }
        .hb-evidence a { font-size: .8rem; line-height: 1.4; text-decoration: none; border-bottom: 1px solid color-mix(in srgb, var(--color-accent) 40%, transparent); }
        .hb-evidence a:hover { color: var(--color-accent); }
        .hb-src { opacity: .5; font-size: .75rem; }
        .hb-key { margin: 1rem 0; }
        .hb-key dt { font-family: var(--font-mono); font-size: 9.5px; letter-spacing: .14em; text-transform: uppercase; margin-top: .7rem; }
        .hb-key dd { margin: .2rem 0 0; font-size: .8rem; color: var(--color-muted); line-height: 1.5; }
      `}</style>
    </div>
  );
}
