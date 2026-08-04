"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

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
  field_key: string;
  label: string;
  stage: string;
  basis: string;
  note: string | null;
  relevance: number | null;
  rel_stage: string | null;
  spread: number;
  n_rated: number;
  n_raters: number;
  sample_size: number;
};

type Signal = {
  id: number;
  title: string;
  summary: string;
  source: string | null;
  url: string | null;
  type: string;
  date: string;
};

const BASIS_LABEL: Record<string, string> = {
  curve: "aus dem Verlaufsmuster",
  evidence: "aus Marktevidenz",
  "curve+evidence": "Verlauf und Evidenz stimmen überein",
  conflict: "Verlauf und Evidenz widersprechen sich",
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
  const [fields, setFields] = useState<Field[]>([]);
  const [open, setOpen] = useState<string | null>(null);
  const [queue, setQueue] = useState<Signal[]>([]);
  const [done, setDone] = useState(0);
  const [weight, setWeight] = useState<{ weight: number; n_rated: number } | null>(null);
  const [leaving, setLeaving] = useState<number | null>(null);
  const [stack, setStack] = useState<number[]>([]);
  const [busy, setBusy] = useState(true);

  const W = 760;
  const H = 132;
  const path = useMemo(() => curvePath(W, H), []);

  const loadBoard = useCallback(async () => {
    const r = await fetch("/api/foresight/instrument?what=board");
    const d = await r.json();
    if (!d?.error) setFields(d.fields ?? []);
    setBusy(false);
  }, []);

  const loadQueue = useCallback(async (field: string) => {
    const r = await fetch(
      `/api/foresight/instrument?what=queue&field=${encodeURIComponent(field)}`
    );
    const d = await r.json();
    if (d?.error) return;
    setQueue(d.signals ?? []);
    setDone(d.done ?? 0);
    setWeight(d.weight ?? null);
  }, []);

  useEffect(() => {
    void loadBoard();
  }, [loadBoard]);

  useEffect(() => {
    if (open) void loadQueue(open);
    else setQueue([]);
  }, [open, loadQueue]);

  const sig = queue[0] ?? null;
  const field = fields.find((f) => f.field_key === open) ?? null;

  const rate = useCallback(
    async (points: number | null) => {
      if (!sig || !open) return;
      setLeaving(sig.id);
      setStack((s) => [...s, points ?? -1].slice(-6));
      window.setTimeout(() => {
        setQueue((q) => q.slice(1));
        setLeaving(null);
        setDone((d) => d + (points === null ? 0 : 1));
      }, 300);
      const r = await fetch("/api/foresight/instrument", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          field: open, trend: sig.id,
          ...(points === null ? { skip: true } : { points }),
        }),
      });
      const d = await r.json();
      if (!d?.error) {
        setFields((prev) =>
          prev.map((f) =>
            f.field_key === open
              ? { ...f, stage: d.stage, basis: d.basis, note: d.note,
                  relevance: d.relevance, rel_stage: relStage(d.relevance),
                  spread: d.relevance_spread, n_rated: d.n_rated,
                  n_raters: d.n_raters }
              : f
          )
        );
      }
    },
    [sig, open]
  );

  // Tastatur zuerst: 0–4 bewerten, → überspringen. Wer sechzig Signale sichtet,
  // soll die Maus nicht anfassen müssen.
  useEffect(() => {
    if (!sig) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key >= "0" && e.key <= "4") {
        e.preventDefault();
        void rate(Number(e.key));
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        void rate(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [sig, rate]);

  const totalRated = fields.reduce((s, f) => s + f.n_rated, 0);

  return (
    <div className="ip">
      <header className="ip-head">
        <div>
          <span className="ip-eyebrow">Foresight · Instrument 02</span>
          <h1 className="ip-title">
            Der <em>Messtisch</em>
          </h1>
          <p className="ip-lede">
            Sie bewerten Signale. Das Portfolio ordnet sich daraufhin selbst:
            die <strong>Reife</strong> leiten wir aus Verlauf und Evidenz ab, die{" "}
            <strong>Relevanz</strong> entsteht aus Ihren Bewertungen. Zwei
            Achsen, zwei Besitzer.
          </p>
        </div>
        <dl className="ip-specs">
          <div><dt>Felder</dt><dd>{fields.length}</dd></div>
          <div><dt>Bewertet</dt><dd>{totalRated}</dd></div>
          <div>
            <dt>Ihr Gewicht</dt>
            <dd>{weight ? weight.weight.toFixed(2) : "—"}</dd>
          </div>
        </dl>
      </header>

      {/* Bewertungsstrecke */}
      <section className="ip-rate" aria-label="Signale bewerten">
        <div className="ip-stack" aria-hidden="true">
          {stack.map((v, i) => (
            <span key={i} className="ip-stack-card" style={{ ["--i" as string]: i }}>
              {v < 0 ? "–" : v}
            </span>
          ))}
        </div>

        {!open ? (
          <p className="ip-idle">
            Wählen Sie unten ein Feld, um seine Signale zu bewerten. Die Relevanz
            eines Felds entsteht ausschließlich aus diesen Bewertungen — sie kann
            Ihnen niemand abnehmen.
          </p>
        ) : !sig ? (
          <p className="ip-idle">
            {busy ? "Stichprobe wird gezogen…" : "Für dieses Feld liegt nichts mehr an. "}
            {!busy && (
              <button className="ip-linkbtn" onClick={() => void loadQueue(open)}>
                Neue Stichprobe ziehen
              </button>
            )}
          </p>
        ) : (
          <article className={`ip-card ${leaving === sig.id ? "is-gone" : ""}`}>
            <div className="ip-card-meta">
              <span>{sig.source ?? "ohne Quelle"}</span>
              <span>{sig.date}</span>
              <span className="ip-card-type">{sig.type.replace("_", " ")}</span>
            </div>
            <h2 className="ip-card-title">{sig.title}</h2>
            {sig.summary ? <p className="ip-card-sum">{sig.summary}</p> : null}
            <p className="ip-card-field">
              gehört zu <strong>{field?.label}</strong>
            </p>

            <div className="ip-scale" role="group" aria-label="Relevanz 0 bis 4">
              {[0, 1, 2, 3, 4].map((n) => (
                <button key={n} className="ip-key" onClick={() => void rate(n)}>
                  <span className="ip-key-n">{n}</span>
                  <span className="ip-key-l">
                    {["irrelevant", "am Rand", "beachten", "wichtig", "zentral"][n]}
                  </span>
                </button>
              ))}
            </div>
            <p className="ip-suggest">
              Tastatur: <b>0</b>–<b>4</b> bewerten, <b>→</b> überspringen.
            </p>
          </article>
        )}

        {open ? (
          <div className="ip-progress">
            <span className="ip-k">Stichprobe</span>
            <span className="ip-p-bar" aria-hidden="true">
              <span
                style={{
                  width: `${Math.min(100, (done / (field?.sample_size ?? 48)) * 100)}%`,
                }}
              />
            </span>
            <span className="ip-p-n">
              {done} / {field?.sample_size ?? 48} für dieses Feld
            </span>
            <span className="ip-p-note">
              Die Stichprobe ist über die ganze Zeitspanne und alle Signaltypen
              gezogen — sie ist repräsentativ, nicht vollständig. Eine Auswahl
              nur der jüngsten Signale ließe jedes Feld jung erscheinen.
            </span>
          </div>
        ) : null}
      </section>

      {/* Portfolio */}
      <section className="ip-pf" aria-label="Portfolio">
        <div className="ip-pf-head">
          <span className="ip-k">Portfolio</span>
          <span className="ip-legend"><i className="sw sw-set" /> von Ihnen gesetzt</span>
          <span className="ip-legend"><i className="sw sw-sug" /> Rückfall / geschätzt</span>
        </div>

        <div className="ip-pf-body">
          <div className="ip-axis" aria-hidden="true">
            <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
              <path d={path} className="ip-curve" />
              {STAGES.map((s) => (
                <line key={s.key} x1={s.at * W} x2={s.at * W} y1={0} y2={H}
                      className="ip-curve-tick" />
              ))}
            </svg>
            <div className="ip-axis-labels">
              {STAGES.map((s) => (
                <span key={s.key} style={{ left: `${s.at * 100}%` }}>{s.label}</span>
              ))}
            </div>
            <p className="ip-axis-note">
              Diffusionskurve mit Aufmerksamkeitsbuckel. Die Reifestufen sitzen
              dort, wo ein Feld auf ihr steht — das ist die Herleitung, nicht
              Zierde. Der Anteil am Signalaufkommen misst allerdings
              Aufmerksamkeit, nicht Marktreife; deshalb zählt die Marktevidenz
              gleichrangig mit.
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
                  const items = fields.filter(
                    (f) => f.stage === s.key && (f.rel_stage ?? null) === rk
                  );
                  return (
                    <div key={`${s.key}-${rk ?? "void"}`}
                         className={`ip-cell ${i === 0 ? "is-void" : ""}`}>
                      {items.map((f) => (
                        <button
                          key={f.field_key}
                          className={`ip-blip ${open === f.field_key ? "is-on" : ""} ${
                            f.basis === "default" ? "is-guess" : ""
                          }`}
                          onClick={() =>
                            setOpen(open === f.field_key ? null : f.field_key)
                          }
                          style={{
                            ["--w" as string]: `${Math.min(1, 0.3 + f.n_rated / 60)}`,
                          }}
                        >
                          <span className="ip-blip-l">{f.label}</span>
                          <span className="ip-blip-n">
                            {f.n_rated ? `${f.n_rated} bewertet` : "unbewertet"}
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

        {field ? <FieldDrawer field={field} onClose={() => setOpen(null)} /> : null}
      </section>

      <Styles />
    </div>
  );
}

function relStage(score: number | null): string | null {
  if (score === null || score === undefined) return null;
  return score >= 2.67 ? "high" : score >= 1.34 ? "medium" : "low";
}

function FieldDrawer({ field, onClose }: { field: Field; onClose: () => void }) {
  return (
    <aside className="ip-drawer">
      <div className="ip-drawer-head">
        <h3>{field.label}</h3>
        <button onClick={onClose} aria-label="Schließen">✕</button>
      </div>
      <div className="ip-drawer-grid">
        <div>
          <span className="ip-k">
            Reife — {STAGES.find((s) => s.key === field.stage)?.label}
          </span>
          {/* Die Begründung sagt die Herkunft selbst — ein vorangestelltes
              Etikett doppelte sie („aus dem Verlaufsmuster. Aus dem
              Verlaufsmuster. Seit 17 Jahren…"). Nur wo sie es NICHT tut, steht
              das Etikett davor. */}
          <p className="ip-drawer-t">
            {field.basis === "conflict" || field.basis === "default" ? null : (
              <em>{BASIS_LABEL[field.basis] ?? field.basis} · </em>
            )}
            {field.note}
          </p>
        </div>
        <div>
          <span className="ip-k">Relevanz — Ihre Bewertung</span>
          <p className="ip-drawer-t">
            {field.n_rated
              ? `${field.n_rated} Signale von ${field.n_raters} Bewerter${
                  field.n_raters > 1 ? "n" : ""
                }, gewichtet nach Fachnähe. Mittel ${field.relevance}.${
                  field.spread > 1
                    ? " Die Bewerter sind uneins — die Streuung steht am Punkt."
                    : ""
                }`
              : "Noch nicht bewertet. Die Relevanz hängt von Ihrem Geschäft ab, nicht vom Signalraum — sie kann Ihnen niemand abnehmen."}
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
      .ip-idle { font-size: .88rem; color: var(--color-muted); max-width: 46em; line-height: 1.6; margin: 0; }
      .ip-linkbtn { background: none; border: none; border-bottom: 1px solid var(--color-accent); color: var(--color-accent); cursor: pointer; padding: 0; font: inherit; }
      .ip-card-sum { font-size: .84rem; line-height: 1.5; color: #4a4940; margin: 0 0 .8rem; }
      .ip-drawer-t em { font-style: normal; color: var(--color-paper); }
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
