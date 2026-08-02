"use client";

import type { RadarReadout } from "@/lib/radar-shared";

/**
 * Der Absatz, den ein Nutzer ins Memo kopiert.
 *
 * Die Nutzerprobe am 2026-08-02 endete bei einer Tabellenzeile — `TEC H2 · REG –
 * · MKT H2 · ADO –` — und der ehrlichen Feststellung, dass damit niemand
 * entscheidet. Vier Buchstabenpaare sind ein Messergebnis, keine Aussage.
 *
 * TRL ist hier die richtige Sprache, weil sie in Industrie, EU-Förderung und
 * Beschaffung etabliert ist: „TRL 6-7" ist in einem Lenkungskreis sofort
 * anschlussfähig, „H2 / MKT" nicht. Gezeigt wird ein BAND, kein Punktwert — ein
 * exaktes TRL setzt Einblick in ein konkretes Entwicklungsprogramm voraus, wir
 * sehen ein Signalfeld. Das Band steht deshalb neben seiner Ableitung, nicht
 * an ihrer Stelle.
 */

const SCALE = [1, 2, 3, 4, 5, 6, 7, 8, 9];

/**
 * Vergleichsleiste: alle Felder mit ihrem TRL-Band nebeneinander.
 *
 * Eine Entscheidung lautet nie „X ja/nein", sondern „X statt Y". Wer drei Felder
 * gegeneinanderstellt, will die Bänder nebeneinander sehen und nicht dreimal
 * klicken — der ausführliche Readout gehört dann zum ausgewählten Feld.
 */
export function ReadoutStrip({
  readouts,
  selected,
  onSelect,
}: {
  readouts: RadarReadout[];
  selected: string | null;
  onSelect: (slug: string) => void;
}) {
  if (readouts.length < 2) return null;
  return (
    <div className="rs" role="group" aria-label="Readiness comparison">
      {readouts.map((r) => {
        const lo = r.trl_low ?? 0;
        const hi = r.trl_high ?? 0;
        return (
          <button
            key={r.scope_slug}
            className={`rs-item ${selected === r.scope_slug ? "is-on" : ""}`}
            onClick={() => onSelect(r.scope_slug)}
            aria-pressed={selected === r.scope_slug}
          >
            <span className="rs-name">{r.scope}</span>
            <span className="rs-bar" aria-hidden="true">
              {SCALE.map((n) => (
                <span key={n} className={`rs-seg ${n >= lo && n <= hi ? "is-on" : ""}`} />
              ))}
            </span>
            <span className="rs-trl">
              {lo ? `TRL ${lo === hi ? lo : `${lo}–${hi}`}` : "not assessable"}
            </span>
          </button>
        );
      })}
      <style>{`
        .rs { display: grid; gap: .4rem; margin-bottom: 1rem; }
        .rs-item { display: grid; grid-template-columns: minmax(8rem, 14rem) 1fr auto; gap: .8rem; align-items: center; text-align: left; background: transparent; border: 1px solid var(--color-border); padding: .5rem .7rem; cursor: pointer; }
        .rs-item:hover { border-color: var(--color-paper); }
        .rs-item.is-on { border-color: var(--color-accent); }
        .rs-name { font-size: .85rem; color: var(--color-paper); }
        .rs-bar { display: flex; gap: 2px; }
        .rs-seg { flex: 1; height: 6px; border: 1px solid var(--color-border); }
        .rs-seg.is-on { background: var(--color-accent); border-color: var(--color-accent); }
        .rs-trl { font-family: var(--font-mono); font-size: 9px; letter-spacing: .14em; text-transform: uppercase; color: var(--color-accent); white-space: nowrap; }
      `}</style>
    </div>
  );
}

export default function FieldReadout({
  readout,
  compact = false,
}: {
  readout: RadarReadout;
  compact?: boolean;
}) {
  const { trl_low: lo, trl_high: hi } = readout;
  const has = lo != null && hi != null;

  return (
    <section className={`fr ${compact ? "is-compact" : ""}`} aria-label="Readout">
      <div className="fr-head">
        <span className="fr-scope">{readout.scope}</span>
        {has ? (
          <span className="fr-trl">
            TRL {lo === hi ? lo : `${lo}–${hi}`}
            <span className="fr-trl-label"> · {readout.trl_label}</span>
          </span>
        ) : (
          <span className="fr-trl fr-trl-none">TRL not assessable</span>
        )}
      </div>

      {has ? (
        <div className="fr-scale" role="img"
             aria-label={`Technology readiness level ${lo} to ${hi} of 9`}>
          {SCALE.map((n) => (
            <span
              key={n}
              className={`fr-step ${n >= (lo ?? 0) && n <= (hi ?? 0) ? "is-on" : ""}`}
            >
              {n}
            </span>
          ))}
        </div>
      ) : null}

      {readout.trl_blurb ? (
        <p className="fr-blurb">{readout.trl_blurb}</p>
      ) : null}

      <p className="fr-text">{readout.text}</p>
      <p className="fr-stance">{readout.stance}</p>
      <p className="fr-caveat">
        The band is derived from the cells below, not from a development
        programme — read it as the range the evidence supports, and open any cell
        for the reasoning.
      </p>

      <style>{`
        .fr { border: 1px solid var(--color-border); border-left: 2px solid var(--color-accent); padding: 1rem 1.1rem; margin-bottom: 1.4rem; background: var(--color-card); }
        .fr.is-compact { padding: .75rem .85rem; margin-bottom: .8rem; }
        .fr-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: .8rem; margin-bottom: .7rem; }
        .fr-scope { font-family: var(--font-serif, var(--font-sans)); font-size: 1.05rem; color: var(--color-paper); }
        .fr-trl { margin-left: auto; font-family: var(--font-mono); font-size: 10px; letter-spacing: .16em; text-transform: uppercase; color: var(--color-accent); }
        .fr-trl-label { color: var(--color-muted); }
        .fr-trl-none { color: var(--color-muted); }
        .fr-scale { display: flex; gap: 2px; margin-bottom: .7rem; }
        .fr-step { flex: 1; text-align: center; font-family: var(--font-mono); font-size: 9px; padding: .2rem 0; border: 1px solid var(--color-border); color: var(--color-muted); }
        .fr-step.is-on { border-color: var(--color-accent); color: var(--color-ink); background: var(--color-accent); font-weight: 600; }
        .fr-blurb { font-size: .8rem; color: var(--color-muted); margin: 0 0 .6rem; font-style: italic; }
        .fr-text { font-size: .89rem; line-height: 1.62; color: var(--color-text); margin: 0 0 .55rem; max-width: 62em; }
        .fr-stance { font-size: .89rem; line-height: 1.55; color: var(--color-paper); margin: 0 0 .5rem; max-width: 62em; }
        .fr-caveat { font-size: .76rem; line-height: 1.5; color: var(--color-muted); margin: 0; max-width: 62em; }
      `}</style>
    </section>
  );
}
