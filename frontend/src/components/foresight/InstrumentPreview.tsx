"use client";

import { useMemo, useState } from "react";

/**
 * „Der Messtisch" — Gestaltungsvorlage des Radar-Neubaus.
 *
 * Leitbild: kein Dashboard, sondern eine Arbeitsfläche. Zeichentisch trifft
 * Oszilloskop. Zwei Gesten tragen das ganze Werkzeug:
 *
 *   1. **Papier auf dunklem Tisch.** Die Bewertungskarte ist hell und
 *      körperlich, alles andere tritt zurück. Sie liegt auf der Fläche, man
 *      sortiert sie weg. Das ist der stärkste visuelle Bruch und zugleich die
 *      Aussage: hier arbeitet ein Mensch, nicht ein Bericht.
 *
 *   2. **Die Reifeachse trägt die Diffusionskurve als Rückgrat.** Hinter den
 *      Stufen läuft die S-Kurve mit dem Hype-Cycle-Buckel, und die Felder
 *      sitzen sichtbar an ihrer Stelle darauf. Blechschmidts Raster bleibt
 *      exakt (4 × 3 mit Handlungsempfehlung), aber die Achse erklärt sich
 *      selbst — man sieht, warum „volatil" zwischen Anstieg und Tal liegt.
 *      Die Kurve ist Herleitung, nicht Dekoration.
 *
 * Farbgesetz, das den ganzen Umbau trägt: **Chartreuse = gesetzt, Zinnober =
 * vorgeschlagen.** Ein maschineller Vorschlag darf nie aussehen wie eine
 * Setzung des Nutzers (Owner-Vorgabe 2026-08-04).
 */

// ---------------------------------------------------------------------------
// Vorlagedaten. Die Strecke dahinter ist Schnitt 1–3 des Plans.
// ---------------------------------------------------------------------------
const STAGES = [
  { key: "emerging", label: "Entstehend", band: "Beobachten", at: 0.1 },
  { key: "volatile", label: "Volatil", band: "Verstehen", at: 0.36 },
  { key: "maturing", label: "Reifend", band: "Berücksichtigen", at: 0.63 },
  { key: "established", label: "Etabliert", band: "Implementieren", at: 0.9 },
];

const RELEVANCE = [
  { key: "low", label: "Gering", band: "Opportunistisch" },
  { key: "medium", label: "Mittel", band: "Gleichwertig" },
  { key: "high", label: "Hoch", band: "Proaktiv" },
];

type Field = {
  key: string;
  label: string;
  stage: string;
  rel: string | null;
  n: number;
  raters: number;
  spread: number;
  basis: "curve" | "evidence" | "research" | "default";
};

const FIELDS: Field[] = [
  { key: "ml", label: "Machine Learning", stage: "established", rel: "high", n: 58, raters: 3, spread: 0.4, basis: "evidence" },
  { key: "chip", label: "Chip Design", stage: "established", rel: "medium", n: 41, raters: 2, spread: 0.9, basis: "curve" },
  { key: "ev", label: "Electric Vehicles", stage: "maturing", rel: "medium", n: 36, raters: 2, spread: 0.5, basis: "evidence" },
  { key: "ux", label: "UX · AI Integration", stage: "maturing", rel: "high", n: 44, raters: 3, spread: 1.4, basis: "curve" },
  { key: "mat", label: "Sustainable Materials", stage: "volatile", rel: "low", n: 22, raters: 1, spread: 0, basis: "default" },
  { key: "neuro", label: "Neuromorphic", stage: "volatile", rel: null, n: 0, raters: 0, spread: 0, basis: "default" },
  { key: "gene", label: "Gene Expression", stage: "emerging", rel: null, n: 0, raters: 0, spread: 0, basis: "curve" },
  { key: "photon", label: "Silicon Photonics", stage: "volatile", rel: null, n: 0, raters: 0, spread: 0, basis: "research" },
];

const QUEUE = [
  {
    id: 1,
    title: "Broadcom ships Tomahawk 6 with co-packaged optics to hyperscalers",
    source: "Semiconductor Today",
    date: "12 Jul 2026",
    type: "product_launch",
    field: "Silicon Photonics",
    hint: 3,
    why: "Ähnelt 8 Signalen, die Sie mit 3 oder 4 bewertet haben.",
  },
];

const BASIS_LABEL: Record<Field["basis"], string> = {
  curve: "aus dem Verlaufsmuster",
  evidence: "aus Marktevidenz",
  research: "aus Recherche",
  default: "nicht bestimmbar — Rückfall auf volatil",
};

/** Rogers-S-Kurve mit Hype-Cycle-Buckel, als Pfad über die Breite 0..1. */
function curvePath(w: number, h: number): string {
  const pts: string[] = [];
  for (let i = 0; i <= 100; i++) {
    const x = i / 100;
    // Diffusion: logistische Basis. Darüber der Aufmerksamkeitsbuckel früh.
    const logistic = 1 / (1 + Math.exp(-12 * (x - 0.55)));
    const hype = 0.34 * Math.exp(-Math.pow((x - 0.22) / 0.1, 2));
    const trough = -0.13 * Math.exp(-Math.pow((x - 0.4) / 0.09, 2));
    const y = Math.min(1, Math.max(0, logistic * 0.82 + hype + trough));
    pts.push(`${(x * w).toFixed(1)},${((1 - y) * h).toFixed(1)}`);
  }
  return "M " + pts.join(" L ");
}

export default function InstrumentPreview() {
  const [rated, setRated] = useState<number[]>([]);
  const [pick, setPick] = useState<number | null>(null);
  const [open, setOpen] = useState<string | null>("ux");

  const W = 760;
  const H = 132;
  const path = useMemo(() => curvePath(W, H), []);
  const sig = QUEUE[0];

  return (
    <div className="ip">
      {/* ---------------- Kopf: Instrumentenschild ---------------- */}
      <header className="ip-head">
        <div>
          <span className="ip-eyebrow">Foresight · Instrument 02</span>
          <h1 className="ip-title">
            Der <em>Messtisch</em>
          </h1>
          <p className="ip-lede">
            Sie bewerten Signale. Das Portfolio ordnet sich daraufhin selbst:
            die <strong>Reife</strong> leiten wir aus Evidenz und Verlauf ab, die{" "}
            <strong>Relevanz</strong> entsteht aus Ihren Bewertungen. Zwei
            Achsen, zwei Besitzer.
          </p>
        </div>
        <dl className="ip-specs">
          <div>
            <dt>Felder</dt>
            <dd>8</dd>
          </div>
          <div>
            <dt>Bewertet</dt>
            <dd>201</dd>
          </div>
          <div>
            <dt>Bewerter</dt>
            <dd>3</dd>
          </div>
          <div>
            <dt>Stand</dt>
            <dd>5. Aug 2026</dd>
          </div>
        </dl>
      </header>

      {/* ---------------- Bewertungsstrecke ---------------- */}
      <section className="ip-rate" aria-label="Signale bewerten">
        <div className="ip-stack" aria-hidden="true">
          {rated.slice(-6).map((v, i) => (
            <span key={i} className="ip-stack-card" style={{ ["--i" as string]: i }}>
              {v}
            </span>
          ))}
        </div>

        <article className={`ip-card ${pick !== null ? "is-gone" : ""}`}>
          <div className="ip-card-meta">
            <span>{sig.source}</span>
            <span>{sig.date}</span>
            <span className="ip-card-type">{sig.type.replace("_", " ")}</span>
          </div>
          <h2 className="ip-card-title">{sig.title}</h2>
          <p className="ip-card-field">
            gehört zu <strong>{sig.field}</strong>
          </p>

          <div className="ip-scale" role="group" aria-label="Relevanz 0 bis 4">
            {[0, 1, 2, 3, 4].map((n) => (
              <button
                key={n}
                className={`ip-key ${n === sig.hint ? "is-hint" : ""}`}
                onClick={() => {
                  setRated((r) => [...r, n]);
                  setPick(n);
                  window.setTimeout(() => setPick(null), 420);
                }}
              >
                <span className="ip-key-n">{n}</span>
                <span className="ip-key-l">
                  {["irrelevant", "am Rand", "beachten", "wichtig", "zentral"][n]}
                </span>
              </button>
            ))}
          </div>

          <p className="ip-suggest">
            <span className="ip-sug-badge">Vorschlag {sig.hint}</span>
            {sig.why} Er zählt nicht mit, bis Sie ihn bestätigen.
          </p>
        </article>

        <div className="ip-progress">
          <span className="ip-k">Stichprobe</span>
          <span className="ip-p-bar" aria-hidden="true">
            <span style={{ width: `${Math.min(100, (rated.length / 48) * 100)}%` }} />
          </span>
          <span className="ip-p-n">{rated.length} / 48 für dieses Feld</span>
          <span className="ip-p-note">
            48 Signale, gezogen über die ganze Zeitspanne und alle Signaltypen —
            nicht die 12 400 des Felds. Die Stichprobe ist repräsentativ, nicht
            vollständig.
          </span>
        </div>
      </section>

      {/* ---------------- Portfolio mit Kurvenrückgrat ---------------- */}
      <section className="ip-pf" aria-label="Portfolio">
        <div className="ip-pf-head">
          <span className="ip-k">Portfolio</span>
          <span className="ip-legend">
            <i className="sw sw-set" /> von Ihnen gesetzt
          </span>
          <span className="ip-legend">
            <i className="sw sw-sug" /> maschineller Vorschlag
          </span>
        </div>

        <div className="ip-pf-body">
          {/* Die Achse erklärt sich: Kurve hinter den Stufen */}
          <div className="ip-axis" aria-hidden="true">
            <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
              <path d={path} className="ip-curve" />
              {STAGES.map((s) => (
                <line
                  key={s.key}
                  x1={s.at * W}
                  x2={s.at * W}
                  y1={0}
                  y2={H}
                  className="ip-curve-tick"
                />
              ))}
            </svg>
            <div className="ip-axis-labels">
              {STAGES.map((s) => (
                <span key={s.key} style={{ left: `${s.at * 100}%` }}>
                  {s.label}
                </span>
              ))}
            </div>
            <p className="ip-axis-note">
              Diffusionskurve mit Aufmerksamkeitsbuckel. Die Reifestufen sitzen
              dort, wo ein Feld auf ihr steht — das ist die Herleitung, nicht
              Zierde.
            </p>
          </div>

          <div className="ip-grid">
            <div className="ip-corner">
              <span>Reife ↓</span>
              <span>Relevanz →</span>
            </div>
            {["Unbewertet", ...RELEVANCE.map((r) => r.label)].map((l, i) => (
              <div key={l} className={`ip-colh ${i === 0 ? "is-void" : ""}`}>
                {l}
                {i > 0 && <em>{RELEVANCE[i - 1].band}</em>}
              </div>
            ))}

            {[...STAGES].reverse().map((s) => (
              <div key={s.key} style={{ display: "contents" }}>
                <div className="ip-rowh">
                  {s.label}
                  <em>{s.band}</em>
                </div>
                {[null, ...RELEVANCE.map((r) => r.key)].map((rk, i) => {
                  const items = FIELDS.filter(
                    (f) => f.stage === s.key && (f.rel ?? null) === rk
                  );
                  return (
                    <div
                      key={`${s.key}-${rk ?? "void"}`}
                      className={`ip-cell ${i === 0 ? "is-void" : ""}`}
                    >
                      {items.map((f) => (
                        <button
                          key={f.key}
                          className={`ip-blip ${open === f.key ? "is-on" : ""} ${
                            f.basis === "default" ? "is-guess" : ""
                          }`}
                          onClick={() => setOpen(open === f.key ? null : f.key)}
                          style={{ ["--w" as string]: `${Math.min(1, 0.35 + f.n / 70)}` }}
                        >
                          <span className="ip-blip-l">{f.label}</span>
                          <span className="ip-blip-n">
                            {f.n ? `${f.n} bewertet` : "unbewertet"}
                            {f.spread > 1 ? " · Bewerter uneins" : ""}
                          </span>
                        </button>
                      ))}
                      {rk && items.length ? (
                        <span className="ip-advice">
                          {s.band} · {RELEVANCE.find((r) => r.key === rk)!.band}
                        </span>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        </div>

        {open ? (
          <FieldDrawer
            field={FIELDS.find((f) => f.key === open)!}
            onClose={() => setOpen(null)}
          />
        ) : null}
      </section>

      <Styles />
    </div>
  );
}

function FieldDrawer({ field, onClose }: { field: Field; onClose: () => void }) {
  return (
    <aside className="ip-drawer">
      <div className="ip-drawer-head">
        <h3>{field.label}</h3>
        <button onClick={onClose} aria-label="Schließen">
          ✕
        </button>
      </div>
      <div className="ip-drawer-grid">
        <div>
          <span className="ip-k">Reife — {STAGES.find((s) => s.key === field.stage)!.label}</span>
          <p className="ip-drawer-t">
            {BASIS_LABEL[field.basis]}
            {field.basis === "default"
              ? ". Weder Verlauf noch Marktevidenz sind eindeutig — das Feld "
                + "steht deshalb auf volatil, dem einzigen Band, dessen "
                + "Empfehlung „genauer hinsehen“ lautet."
              : ". Verlauf und Evidenz stimmen überein."}
          </p>
        </div>
        <div>
          <span className="ip-k">Relevanz — Ihre Bewertung</span>
          <p className="ip-drawer-t">
            {field.n
              ? `${field.n} Signale von ${field.raters} Bewerter${
                  field.raters > 1 ? "n" : ""
                }, gewichtet nach Fachnähe.${
                  field.spread > 1
                    ? " Die Bewerter sind uneins — die Fachnahen liegen höher."
                    : ""
                }`
              : "Noch nicht bewertet. Ihre Relevanz kann Ihnen niemand abnehmen: sie hängt von Ihrem Geschäft ab, nicht vom Signalraum."}
          </p>
        </div>
      </div>
    </aside>
  );
}

function Styles() {
  return (
    <style>{`
      .ip { --paper: #f4f1e8; --sug: #e8503a; max-width: 78rem; margin: 0 auto; padding: 0 1.25rem 4rem; }

      /* Kopf */
      .ip-head { display: grid; grid-template-columns: 1fr auto; gap: 2rem; align-items: end; padding: 2.5rem 0 1.6rem; border-bottom: 1px solid var(--color-border); }
      .ip-eyebrow { font-family: var(--font-mono); font-size: 9px; letter-spacing: .28em; text-transform: uppercase; color: var(--color-accent); }
      .ip-title { font-size: clamp(2.4rem, 6vw, 4rem); line-height: .95; margin: .5rem 0 .7rem; color: var(--color-paper); font-weight: 400; letter-spacing: -.02em; }
      .ip-title em { font-style: italic; color: var(--color-accent); }
      .ip-lede { max-width: 44em; font-size: .95rem; line-height: 1.6; color: var(--color-text); margin: 0; }
      .ip-lede strong { color: var(--color-paper); font-weight: 500; }
      .ip-specs { display: flex; gap: 1.6rem; margin: 0; }
      .ip-specs dt { font-family: var(--font-mono); font-size: 8.5px; letter-spacing: .18em; text-transform: uppercase; color: var(--color-muted); }
      .ip-specs dd { font-family: var(--font-mono); font-size: 1.15rem; color: var(--color-paper); margin: .2rem 0 0; }

      .ip-k { font-family: var(--font-mono); font-size: 9px; letter-spacing: .22em; text-transform: uppercase; color: var(--color-accent); }

      /* Bewertungsstrecke — Papier auf dunklem Tisch */
      .ip-rate { position: relative; display: grid; grid-template-columns: 4.5rem 1fr; gap: 1.6rem; padding: 2.4rem 0 2rem; align-items: start; }
      .ip-stack { position: relative; height: 12rem; }
      .ip-stack-card { position: absolute; left: 0; top: calc(var(--i) * 9px); width: 3.6rem; height: 2.6rem; background: color-mix(in srgb, var(--paper) 22%, transparent); border: 1px solid color-mix(in srgb, var(--paper) 30%, transparent); display: grid; place-items: center; font-family: var(--font-mono); font-size: 11px; color: var(--paper); transform: rotate(calc(var(--i) * -1.1deg)); animation: drop .35s cubic-bezier(.2,.8,.3,1); }
      @keyframes drop { from { transform: translate(90px,-40px) rotate(8deg); opacity: 0 } }

      .ip-card { position: relative; background: var(--paper); color: #1a1c18; padding: 1.7rem 1.9rem 1.5rem; max-width: 46rem; box-shadow: 0 26px 60px -26px rgba(0,0,0,.9), 0 2px 0 0 rgba(0,0,0,.35); transition: transform .4s cubic-bezier(.4,0,.2,1), opacity .4s; }
      .ip-card.is-gone { transform: translateX(-120px) rotate(-6deg); opacity: 0; }
      .ip-card::after { content: ""; position: absolute; inset: 0; pointer-events: none; background-image: radial-gradient(rgba(0,0,0,.045) 1px, transparent 1px); background-size: 3px 3px; mix-blend-mode: multiply; }
      .ip-card-meta { display: flex; flex-wrap: wrap; gap: .9rem; font-family: var(--font-mono); font-size: 9px; letter-spacing: .14em; text-transform: uppercase; color: #6b6a60; margin-bottom: .8rem; }
      .ip-card-type { border: 1px solid #cfcbbd; padding: 0 .35rem; }
      .ip-card-title { font-size: 1.5rem; line-height: 1.24; margin: 0 0 .6rem; font-weight: 400; letter-spacing: -.01em; }
      .ip-card-field { font-size: .82rem; color: #6b6a60; margin: 0 0 1.3rem; }
      .ip-card-field strong { color: #1a1c18; font-weight: 500; }

      .ip-scale { display: grid; grid-template-columns: repeat(5, 1fr); gap: .35rem; }
      .ip-key { display: grid; gap: .15rem; padding: .6rem .3rem; background: transparent; border: 1px solid #cfcbbd; cursor: pointer; transition: background .14s, border-color .14s, transform .14s; }
      .ip-key:hover { background: #1a1c18; border-color: #1a1c18; transform: translateY(-2px); }
      .ip-key:hover .ip-key-n, .ip-key:hover .ip-key-l { color: var(--paper); }
      .ip-key-n { font-family: var(--font-mono); font-size: 1.1rem; color: #1a1c18; }
      .ip-key-l { font-family: var(--font-mono); font-size: 8px; letter-spacing: .1em; text-transform: uppercase; color: #6b6a60; }
      .ip-key.is-hint { border-color: var(--sug); box-shadow: inset 0 -3px 0 var(--sug); }

      .ip-suggest { margin: 1.1rem 0 0; font-size: .78rem; line-height: 1.5; color: #6b6a60; display: flex; flex-wrap: wrap; gap: .5rem; align-items: baseline; }
      .ip-sug-badge { font-family: var(--font-mono); font-size: 8.5px; letter-spacing: .16em; text-transform: uppercase; color: var(--paper); background: var(--sug); padding: .1rem .4rem; }

      .ip-progress { grid-column: 2; display: grid; grid-template-columns: auto 12rem auto; gap: .8rem; align-items: center; margin-top: 1.1rem; }
      .ip-p-bar { height: 3px; background: color-mix(in srgb, var(--color-paper) 14%, transparent); display: block; }
      .ip-p-bar span { display: block; height: 100%; background: var(--color-accent); transition: width .3s; }
      .ip-p-n { font-family: var(--font-mono); font-size: 9px; letter-spacing: .12em; text-transform: uppercase; color: var(--color-muted); }
      .ip-p-note { grid-column: 1 / -1; font-size: .74rem; line-height: 1.5; color: var(--color-muted); max-width: 46em; }

      /* Portfolio */
      .ip-pf { border-top: 1px solid var(--color-border); padding-top: 2rem; }
      .ip-pf-head { display: flex; gap: 1.4rem; align-items: center; margin-bottom: 1rem; }
      .ip-legend { display: flex; align-items: center; gap: .4rem; font-family: var(--font-mono); font-size: 8.5px; letter-spacing: .14em; text-transform: uppercase; color: var(--color-muted); }
      .sw { width: 10px; height: 10px; display: inline-block; }
      .sw-set { background: var(--color-accent); }
      .sw-sug { background: var(--sug); }

      .ip-axis { position: relative; margin-bottom: .5rem; padding-left: 9.5rem; }
      .ip-axis svg { width: 100%; height: 96px; display: block; }
      .ip-curve { fill: none; stroke: color-mix(in srgb, var(--color-accent) 45%, transparent); stroke-width: 1.5; }
      .ip-curve-tick { stroke: var(--color-border); stroke-dasharray: 2 4; }
      .ip-axis-labels { position: relative; height: 1rem; }
      .ip-axis-labels span { position: absolute; transform: translateX(-50%); font-family: var(--font-mono); font-size: 8.5px; letter-spacing: .16em; text-transform: uppercase; color: var(--color-muted); }
      .ip-axis-note { font-size: .72rem; color: var(--color-muted); margin: .7rem 0 1rem; max-width: 52em; line-height: 1.5; }

      .ip-grid { display: grid; grid-template-columns: 9.5rem repeat(4, 1fr); gap: 1px; background: var(--color-border); border: 1px solid var(--color-border); }
      .ip-corner, .ip-colh, .ip-rowh, .ip-cell { background: var(--color-ink); padding: .55rem .6rem; }
      .ip-corner { display: grid; gap: .2rem; font-family: var(--font-mono); font-size: 8px; letter-spacing: .14em; text-transform: uppercase; color: var(--color-muted); }
      .ip-colh, .ip-rowh { font-family: var(--font-mono); font-size: 9px; letter-spacing: .16em; text-transform: uppercase; color: var(--color-paper); display: grid; gap: .15rem; align-content: start; }
      .ip-colh em, .ip-rowh em { font-style: normal; font-size: 8px; color: var(--color-accent); letter-spacing: .1em; }
      .ip-colh.is-void, .ip-cell.is-void { background: #0d0f0c; }
      .ip-cell { min-height: 5.6rem; display: flex; flex-direction: column; gap: .3rem; }

      .ip-blip { text-align: left; display: grid; gap: .12rem; padding: .35rem .45rem; background: color-mix(in srgb, var(--color-accent) calc(var(--w) * 16%), transparent); border: 1px solid color-mix(in srgb, var(--color-accent) calc(var(--w) * 70%), var(--color-border)); cursor: pointer; transition: transform .18s, border-color .18s; }
      .ip-blip:hover { transform: translateX(2px); }
      .ip-blip.is-on { border-color: var(--color-accent); }
      .ip-blip.is-guess { border-style: dashed; }
      .ip-blip-l { font-size: .78rem; line-height: 1.2; color: var(--color-paper); }
      .ip-blip-n { font-family: var(--font-mono); font-size: 7.5px; letter-spacing: .1em; text-transform: uppercase; color: var(--color-muted); }
      .ip-advice { margin-top: auto; font-family: var(--font-mono); font-size: 7.5px; letter-spacing: .1em; text-transform: uppercase; color: var(--color-muted); }

      .ip-drawer { border: 1px solid var(--color-accent); border-left-width: 2px; margin-top: 1rem; padding: .9rem 1.1rem; background: var(--color-card); }
      .ip-drawer-head { display: flex; align-items: baseline; gap: 1rem; margin-bottom: .7rem; }
      .ip-drawer-head h3 { margin: 0; font-size: 1.05rem; font-weight: 400; color: var(--color-paper); }
      .ip-drawer-head button { margin-left: auto; background: transparent; border: 1px solid var(--color-border); color: var(--color-muted); cursor: pointer; padding: .05rem .4rem; }
      .ip-drawer-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.6rem; }
      .ip-drawer-t { font-size: .8rem; line-height: 1.55; color: var(--color-text); margin: .35rem 0 0; }

      @media (max-width: 900px) {
        .ip-head { grid-template-columns: 1fr; }
        .ip-rate { grid-template-columns: 1fr; }
        .ip-stack { display: none; }
        .ip-progress { grid-column: 1; }
        .ip-axis { padding-left: 0; }
        .ip-grid { grid-template-columns: 6.5rem repeat(4, 1fr); }
        .ip-drawer-grid { grid-template-columns: 1fr; }
      }
    `}</style>
  );
}
