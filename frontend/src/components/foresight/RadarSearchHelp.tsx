"use client";

import { HORIZON_META, type Horizon } from "@/lib/radar-shared";
import { RADAR_THRESHOLDS as T } from "@/lib/radar-params";

/**
 * The instrument's own manual, next to the query field.
 *
 * It answers the two questions a user actually has before typing: what decides
 * where a field lands, and why a term sometimes returns nothing. Both answers
 * are specific — the criteria per dimension and the real thresholds — because a
 * vague "results may vary" would leave the user guessing whether an empty cell
 * is a bug or a statement.
 *
 * The numbers come from RADAR_THRESHOLDS, which tests/test_radar_query.py holds
 * against the Python constants: help text that quotes stale thresholds teaches a
 * rule the engine no longer follows, which is worse than no help at all.
 *
 * A native <details> keeps it keyboard- and screen-reader-accessible with no JS.
 */

const CRITERIA: { key: string; label: string; body: string; note?: string }[] = [
  {
    key: "TEC",
    label: "Technology",
    body:
      "The field's own cumulative market history — how many years its market signals go back — plus the patent record where its lead-time is flagged reliable.",
    note:
      `A field with market signals across ${T.establishedActiveYears}+ years, starting ${T.establishedFirstAge}+ years back, counts as established (H1) even while research continues — news covers change, not state, so ongoing research says nothing against maturity. Without that history the signal mix decides, capped at H2: scale and cost maturity are not readable from signals.`,
  },
  {
    key: "REG",
    label: "Regulatory",
    body:
      "Approval milestones, attributed to the authority named in the text — FDA to the US, EFSA to the EU — not to where the company sits.",
    note:
      "Approval granted → H1. A live filing under review → H2. Consultations, strategies and calls for reform → H3: a route being built is not a route you can use. Without “approval required” switched on, absent approvals make no call at all — batteries need none, so their absence is not a barrier.",
  },
  {
    key: "MKT",
    label: "Market",
    body:
      `Product launches in that jurisdiction over the last ${T.windowMonths} months, weighted by retail and scale evidence.`,
    note:
      "With “approval required” switched on, the market can never be rated ahead of its approval — without a licence there is no lawful market.",
  },
  {
    key: "ADO",
    label: "Adoption",
    body:
      "Consumer- and demand-side signals, as opposed to company announcements.",
  },
];

export default function RadarSearchHelp() {
  return (
    <details className="rsh">
      <summary className="rsh-toggle">ⓘ What decides the placement</summary>
      <div className="rsh-panel">
        {/* 1 — what to type */}
        <section className="rsh-sec">
          <h3 className="rsh-h">A good search term</h3>
          <p className="rsh-p">
            Name a <strong>concrete technology, material or process</strong> in two to
            six words — “solid state battery”, “direct air capture”, “precision
            fermentation”.
          </p>
          <p className="rsh-p rsh-muted">
            Company and product names, and abstract themes like “future of work”,
            match the wording of articles rather than a field, and produce a radar
            about the phrase instead of the technology.
          </p>
        </section>

        {/* 2 — how a placement is made */}
        <section className="rsh-sec">
          <h3 className="rsh-h">How each dimension is decided</h3>
          <dl className="rsh-crit">
            {CRITERIA.map((c) => (
              <div key={c.key}>
                <dt>{c.key}</dt>
                <dd>
                  <span className="rsh-crit-label">{c.label}</span> {c.body}
                  {c.note ? <span className="rsh-note"> {c.note}</span> : null}
                </dd>
              </div>
            ))}
          </dl>
          <ul className="rsh-hor">
            {(["H1", "H2", "H3"] as Horizon[]).map((h) => (
              <li key={h}>
                <span style={{ color: HORIZON_META[h].color }}>
                  {h} {HORIZON_META[h].action}
                </span>{" "}
                — {HORIZON_META[h].blurb}
              </li>
            ))}
          </ul>
          <p className="rsh-p rsh-muted">
            A field normally sits on different horizons per dimension and per
            jurisdiction. That spread is the reading, not an inconsistency.
          </p>
        </section>

        {/* 3 — when nothing comes back */}
        <section className="rsh-sec">
          <h3 className="rsh-h">When a term returns nothing</h3>
          <ul className="rsh-why">
            <li>
              <span className="rsh-num">&lt; {T.minScopeRows}</span>
              <span>
                <strong>Too little evidence.</strong> Below {T.minScopeRows} signals no
                radar is built at all. Usually the term is too specific, too new, or
                spelled differently in the sources — try the broader field it belongs
                to.
              </span>
            </li>
            <li>
              <span className="rsh-num">&gt; {T.maxScopeRows.toLocaleString("en-US")}</span>
              <span>
                <strong>Too broad.</strong> Something like “artificial intelligence”
                spans thousands of unrelated things and cannot be read as one field.
                Add a word.
              </span>
            </li>
            <li>
              <span className="rsh-num">—</span>
              <span>
                <strong>Stop words only.</strong> A term the search cannot turn into a
                query at all returns nothing rather than everything.
              </span>
            </li>
          </ul>
          <p className="rsh-p">
            A radar can also appear with <strong>individual cells empty</strong>, shown
            as a dash. That is a separate statement: the field exists, but this one
            dimension has too few signals in that jurisdiction — fewer than{" "}
            {T.minRegulatory} regulatory, {T.minMarket} market or {T.minAdoption}{" "}
            demand signals, or under {T.minTechFallback} for a technology call without
            a patent anchor.
          </p>
          <p className="rsh-p rsh-muted">
            An empty cell is deliberate. The radar withholds a placement it cannot
            support rather than inferring one from thin evidence.
          </p>
        </section>
      </div>

      <style>{`
        .rsh { position: relative; display: inline-block; }
        .rsh-toggle { list-style: none; cursor: pointer; font-family: var(--font-mono); font-size: 9px; letter-spacing: .16em; text-transform: uppercase; color: var(--color-muted); border: 1px dashed var(--color-border); padding: .35rem .7rem; user-select: none; transition: color .18s, border-color .18s; }
        .rsh-toggle::-webkit-details-marker { display: none; }
        .rsh-toggle:hover { color: var(--color-accent); border-color: color-mix(in srgb, var(--color-accent) 50%, transparent); }
        .rsh[open] .rsh-toggle { color: var(--color-accent); border-color: var(--color-accent); border-style: solid; }
        .rsh-panel { position: absolute; left: 0; top: calc(100% + .4rem); z-index: 30; width: min(38rem, 92vw); max-height: min(70vh, 40rem); overflow-y: auto; border: 1px solid var(--color-border); background: var(--color-card); padding: 1.1rem 1.2rem; box-shadow: 0 24px 60px -24px rgba(0,0,0,.9); }
        @media (max-width: 640px) { .rsh-panel { position: fixed; left: 1rem; right: 1rem; width: auto; } }
        .rsh-sec + .rsh-sec { margin-top: 1.3rem; padding-top: 1.1rem; border-top: 1px solid color-mix(in srgb, var(--color-border) 60%, transparent); }
        .rsh-h { font-family: var(--font-mono); font-size: 9px; letter-spacing: .22em; text-transform: uppercase; color: var(--color-accent); margin: 0 0 .6rem; font-weight: 400; }
        .rsh-p { font-size: .84rem; line-height: 1.6; color: var(--color-text); margin: 0 0 .55rem; }
        .rsh-p strong { color: var(--color-paper); font-weight: 500; }
        .rsh-muted { color: var(--color-muted); }
        .rsh-crit { margin: 0 0 .9rem; display: grid; gap: .6rem; }
        .rsh-crit > div { display: grid; grid-template-columns: 2.6rem 1fr; gap: .7rem; align-items: start; }
        .rsh-crit dt { font-family: var(--font-mono); font-size: 9px; letter-spacing: .12em; color: var(--color-muted); border: 1px solid var(--color-border); text-align: center; padding: .15rem 0; }
        .rsh-crit dd { margin: 0; font-size: .82rem; line-height: 1.55; color: var(--color-text); }
        .rsh-crit-label { color: var(--color-paper); }
        .rsh-note { color: var(--color-muted); }
        .rsh-hor { list-style: none; padding: 0; margin: 0 0 .6rem; display: grid; gap: .3rem; }
        .rsh-hor li { font-size: .8rem; line-height: 1.5; color: var(--color-muted); }
        .rsh-hor span { font-family: var(--font-mono); font-size: 9.5px; letter-spacing: .12em; text-transform: uppercase; }
        .rsh-why { list-style: none; padding: 0; margin: 0 0 .8rem; display: grid; gap: .55rem; }
        .rsh-why li { display: grid; grid-template-columns: 4.6rem 1fr; gap: .7rem; align-items: start; font-size: .82rem; line-height: 1.55; color: var(--color-text); }
        .rsh-num { font-family: var(--font-mono); font-size: 9.5px; letter-spacing: .08em; color: var(--color-accent); border: 1px solid color-mix(in srgb, var(--color-accent) 35%, transparent); text-align: center; padding: .18rem .2rem; white-space: nowrap; }
        .rsh-why strong { color: var(--color-paper); font-weight: 500; }
      `}</style>
    </details>
  );
}
