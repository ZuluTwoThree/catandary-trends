"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import FieldPicker from "./FieldPicker";
import Discovery from "./Discovery";

/**
 * “The plotting table” — the rebuilt radar as a working surface.
 *
 * Guiding image: not a dashboard but a desk. Drafting table meets oscilloscope.
 * Two gestures carry the whole tool:
 *
 *   1. **Paper on a dark table.** The rating card is light and physical,
 *      everything else recedes. It lies on the surface and gets dealt away.
 *      That is the strongest visual break and simultaneously the statement:
 *      a person works here, this is not a report.
 *
 *   2. **The maturity axis carries the diffusion curve as its spine.** The
 *      S-curve with its hype bump runs behind the stages, and fields sit
 *      visibly at their place on it. Blechschmidt's grid stays exact (4 × 3
 *      with an action recommendation), but the axis explains itself — you can
 *      see why “volatile” sits between the climb and the trough. The curve is
 *      derivation, not decoration.
 *
 * Colour law that carries the entire rebuild: **chartreuse = set by you,
 * vermillion = proposed by the machine.** A machine proposal must never look
 * like a user's decision (owner requirement, 2026-08-04).
 *
 * English since 2026-08-07 (owner): the product language is English throughout,
 * and user tests should not read a second language into the instrument.
 */

const STAGES = [
  { key: "emerging", label: "Emerging", band: "Observe", at: 0.1 },
  { key: "volatile", label: "Volatile", band: "Understand", at: 0.36 },
  { key: "maturing", label: "Maturing", band: "Consider", at: 0.63 },
  { key: "established", label: "Established", band: "Implement", at: 0.9 },
];

const RELEVANCE = [
  { key: "low", label: "Low", band: "Opportunistic" },
  { key: "medium", label: "Medium", band: "On par" },
  { key: "high", label: "High", band: "Proactive" },
];

const SCALE = ["irrelevant", "peripheral", "worth noting", "important", "central"];

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
  automated: boolean;
  automated_accuracy: number | null;
};

type Signal = {
  id: number;
  title: string;
  summary: string;
  source: string | null;
  url: string | null;
  type: string;
  date: string;
  hint: number | null;
  hint_score: number | null;
};

type Blip = {
  kind: string;
  field_key: string;
  label: string;
  on_table: boolean;
  n: number;
  field_n: number;
  relevance: number;
  rel_stage: string;
  stage: string;
  basis: string;
  note: string | null;
  hits: { id: number; title: string; source: string | null; url: string | null }[];
};

/** Fortschritt zur Automatisierung. Gezählt werden POSITIVE Bewertungen, nicht
 *  Bewertungen — das ist der gemessene Engpass (docs/instrument_learning_curve.md).
 *  `accuracy` ist Präzision an der Spitze, um einen Eimer nach unten korrigiert. */
type Automation = {
  positives: number;
  rated: number;
  model_ready: boolean;
  unlocked: boolean;
  accuracy: number | null;
  min_positives: number;
  next_at: number | null;
  next_accuracy: number | null;
  needed: number;
  hit_rate: number | null;
};

type AutoResult = {
  ok: boolean;
  field_key?: string;
  scored?: number;
  flagged_relevant?: number;
  accuracy?: number;
  threshold?: { cut: number; f1: number; precision_in_sample: number;
                recall_in_sample: number } | null;
  top?: { id: number; points: number; title: string; source: string | null; url: string | null }[];
};

/** Was ein Neustart wirklich löscht — vom Server, nicht aus der Tafel
 *  geschätzt. Die Tafel zählt nur Felder, die noch auf dem Tisch liegen. */
type ResetPreview = {
  ratings: number;
  orphaned: number;
  skipped: number;
  fields: number;
  raters: number;
  field_labels: string[];
  model_was_ready: boolean;
};

type Projection = {
  ready: boolean;
  model: { n: number; positives: number; ready: boolean };
  n_hits?: number;
  n_placed?: number;
  blips: Blip[];
};

const BASIS_LABEL: Record<string, string> = {
  curve: "from the shape of its history",
  evidence: "from market evidence",
  "curve+evidence": "history and evidence agree",
  conflict: "history and evidence disagree",
  research: "from research",
  default: "not determinable — falls back to volatile",
};

/** Rogers S-curve with the hype bump, as a path across width 0..1. */
function curvePath(w: number, h: number): string {
  const pts: string[] = [];
  for (let i = 0; i <= 100; i++) {
    const x = i / 100;
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
  const [model, setModel] = useState<{ n: number; positives: number; ready: boolean } | null>(null);
  const [leaving, setLeaving] = useState<number | null>(null);
  const [stack, setStack] = useState<number[]>([]);
  const [busy, setBusy] = useState(true);
  const [proj, setProj] = useState<Projection | null>(null);
  const [projecting, setProjecting] = useState(false);
  const [confirmReset, setConfirmReset] = useState<ResetPreview | null>(null);
  const [askingReset, setAskingReset] = useState(false);
  const [auto, setAuto] = useState<Automation | null>(null);
  const [autoResult, setAutoResult] = useState<AutoResult | null>(null);
  const [automating, setAutomating] = useState(false);

  const W = 760;
  const H = 132;
  const path = useMemo(() => curvePath(W, H), []);

  const loadBoard = useCallback(async () => {
    const r = await fetch("/api/foresight/instrument?what=board");
    const d = await r.json();
    if (!d?.error) {
      setFields(d.fields ?? []);
      setAuto(d.automation ?? null);
    }
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
    setModel(d.model ?? null);
    if (d.automation) setAuto(d.automation);
  }, []);

  const runProjection = useCallback(async () => {
    setProjecting(true);
    const r = await fetch("/api/foresight/instrument?what=project");
    const d = await r.json();
    setProjecting(false);
    if (!d?.error) setProj(d);
  }, []);

  const askReset = useCallback(async () => {
    setAskingReset(true);
    const r = await fetch("/api/foresight/instrument?what=reset_preview");
    const d = await r.json();
    setAskingReset(false);
    if (!d?.error) setConfirmReset(d);
  }, []);

  const reset = useCallback(async () => {
    setConfirmReset(null);
    setBusy(true);
    await fetch("/api/foresight/instrument", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ reset: true }),
    });
    setOpen(null);
    setQueue([]);
    setStack([]);
    setDone(0);
    setProj(null);
    setModel(null);
    setAutoResult(null);
    await loadBoard();
  }, [loadBoard]);

  const automate = useCallback(async (key: string, on: boolean) => {
    setAutomating(true);
    const r = await fetch("/api/foresight/instrument", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(on ? { automate: key } : { unautomate: key }),
    });
    const d = await r.json();
    setAutomating(false);
    setAutoResult(on && d?.ok ? d : null);
    await loadBoard();
  }, [loadBoard]);

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
        if (d.automation) setAuto(d.automation);
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

  // Keyboard first: 0–4 to rate, → to skip. Anyone sifting sixty signals
  // should not have to touch the mouse.
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
  const own = new Set(fields.map((f) => f.field_key));
  const suggested = (proj?.blips ?? []).filter((b) => !own.has(b.field_key));

  return (
    <div className="ip">
      <header className="ip-head">
        <div>
          <span className="ip-eyebrow">Foresight · Instrument 02</span>
          <h1 className="ip-title">
            The <em>plotting table</em>
          </h1>
          <p className="ip-lede">
            You rate signals. The portfolio then arranges itself:{" "}
            <strong>maturity</strong> we derive from history and evidence,{" "}
            <strong>relevance</strong> comes out of your judgement. Two axes,
            two owners.
          </p>
        </div>
        <dl className="ip-specs">
          <div><dt>Topics</dt><dd>{fields.length}</dd></div>
          <div><dt>Rated</dt><dd>{totalRated}</dd></div>
          <div>
            <dt>Your weight</dt>
            <dd>{weight ? weight.weight.toFixed(2) : "—"}</dd>
          </div>
        </dl>
      </header>

      {/* Der Neustart gehört dorthin, wo ein Lauf BEGINNT — nicht in den
          Kennzahlenblock. Dort stand er zuerst, als kleiner Knopf unter
          „Session", und wurde prompt für den Sweep-Knopf im Portfolio
          gehalten. Ein Knopf, der 175 Bewertungen löscht, muss sich benennen. */}
      <section className="ip-run">
        <div className="ip-run-l">
          <span className="ip-k">Rating run</span>
          <p>
            {totalRated
              ? `${totalRated} ratings on record across ${fields.length} topic${
                  fields.length === 1 ? "" : "s"
                }. They are what the interest model is built from.`
              : "Nothing rated yet. Name a topic below and start."}
          </p>
        </div>
        {confirmReset ? (
          <div className="ip-run-confirm" role="alertdialog" aria-label="Confirm reset">
            <h3>Erase this rating run?</h3>
            <ul className="ip-run-list">
              <li>
                <b>{confirmReset.ratings}</b> ratings
                {confirmReset.orphaned > 0 ? (
                  <em>
                    {" "}
                    — {confirmReset.orphaned} of them on topics you already took
                    off the table. They are not on the board but still feed the
                    model, so they go too.
                  </em>
                ) : null}
              </li>
              {confirmReset.skipped > 0 ? (
                <li><b>{confirmReset.skipped}</b> skipped signals</li>
              ) : null}
              <li>
                <b>{confirmReset.fields}</b> topic
                {confirmReset.fields === 1 ? "" : "s"}
                {confirmReset.field_labels.length ? (
                  <em> — {confirmReset.field_labels.join(", ")}</em>
                ) : null}
              </li>
              <li>
                the learned interest model
                {confirmReset.model_was_ready ? (
                  <em> — currently active; proposals stop until you rate 25 again</em>
                ) : (
                  <em> — not active yet</em>
                )}
              </li>
            </ul>
            <p className="ip-run-safe">
              Untouched: the signal corpus, every published trend, and any other
              workspace. Only this rating run is erased — and it cannot be
              undone.
            </p>
            <div>
              <button className="ip-danger" onClick={() => void reset()}>
                yes, erase {confirmReset.ratings} ratings
              </button>
              <button className="ip-cancel" onClick={() => setConfirmReset(null)}>
                cancel
              </button>
            </div>
          </div>
        ) : (
          <button
            className="ip-resetbtn"
            onClick={() => void askReset()}
            disabled={askingReset || (!totalRated && !fields.length)}
          >
            {askingReset ? "checking…" : "↺ start a fresh run"}
          </button>
        )}
      </section>

      {/* Choosing what you follow — the first act of work */}
      <FieldPicker
        onChange={() => {
          void loadBoard();
          if (open) void loadQueue(open);
        }}
      />

      <Discovery onAdd={() => void loadBoard()} />

      {/* The rating run */}
      <section className="ip-rate" aria-label="Rate signals">
        <div className="ip-stack" aria-hidden="true">
          {stack.map((v, i) => (
            <span key={i} className="ip-stack-card" style={{ ["--i" as string]: i }}>
              {v < 0 ? "–" : v}
            </span>
          ))}
        </div>

        {!open ? (
          <p className="ip-idle">
            Pick a topic below to rate its signals. A topic&rsquo;s relevance comes
            solely out of those ratings — nobody can do that part for you.
          </p>
        ) : !sig ? (
          <p className="ip-idle">
            {busy ? "Drawing a sample…" : "Nothing left on this topic. "}
            {!busy && (
              <button className="ip-linkbtn" onClick={() => void loadQueue(open)}>
                Draw a fresh sample
              </button>
            )}
          </p>
        ) : (
          <article className={`ip-card ${leaving === sig.id ? "is-gone" : ""}`}>
            <div className="ip-card-meta">
              <span>{sig.source ?? "no source"}</span>
              <span>{sig.date}</span>
              <span className="ip-card-type">{sig.type.replace("_", " ")}</span>
            </div>
            <h2 className="ip-card-title">{sig.title}</h2>
            {sig.summary ? <p className="ip-card-sum">{sig.summary}</p> : null}
            <p className="ip-card-field">
              belongs to <strong>{field?.label}</strong>
            </p>

            <div className="ip-scale" role="group" aria-label="Relevance 0 to 4">
              {[0, 1, 2, 3, 4].map((n) => (
                <button
                  key={n}
                  className={`ip-key ${sig.hint === n ? "is-hint" : ""}`}
                  onClick={() => void rate(n)}
                >
                  <span className="ip-key-n">{n}</span>
                  <span className="ip-key-l">{SCALE[n]}</span>
                </button>
              ))}
            </div>
            {sig.hint !== null ? (
              <p className="ip-suggest">
                <span className="ip-sug-badge">proposal {sig.hint}</span>
                Learned from your {model?.n} ratings so far. It does not count
                until you confirm it.
              </p>
            ) : null}
            <p className="ip-suggest ip-keys">
              Keyboard: <b>0</b>–<b>4</b> to rate, <b>→</b> to skip.
            </p>
          </article>
        )}

        {open && auto ? (
          <AutomationBar
            auto={auto}
            field={field}
            done={done}
            busy={automating}
            onAutomate={() => void automate(open, true)}
          />
        ) : null}
      </section>

      {autoResult?.ok ? (
        <div className="ip-autoresult">
          <h3>
            Model rated {autoResult.scored?.toLocaleString("en-US")} signals —{" "}
            {autoResult.flagged_relevant?.toLocaleString("en-US")} came out relevant
          </h3>
          <p>
            That is{" "}
            {autoResult.scored
              ? Math.round(
                  ((autoResult.flagged_relevant ?? 0) / autoResult.scored) * 100
                )
              : 0}{" "}
            % of the topic, against a {Math.round((auto?.hit_rate ?? 0) * 100)} %
            hit rate in what you rated by hand. The cut-off is not a fixed
            number — it is the one that best separates your own relevant
            ratings from your irrelevant ones
            {autoResult.threshold ? (
              <>
                {" "}
                (precision {Math.round(autoResult.threshold.precision_in_sample * 100)} %,
                recall {Math.round(autoResult.threshold.recall_in_sample * 100)} % on
                your own ratings — optimistic, since it was chosen on them)
              </>
            ) : null}
            . On unseen signals expect around{" "}
            <b>{Math.round((autoResult.accuracy ?? 0) * 100)} %</b> at the top of
            the ranking. The tail stays uncertain, and even a well-trained model
            misses over half of everything relevant. Read the first twelve and
            see whether you agree — that is the only check that counts.
          </p>
          <ol>
            {autoResult.top?.map((h) => (
              <li key={h.id}>
                <b>{h.points.toFixed(1)}</b>{" "}
                {h.url ? (
                  <a href={h.url} target="_blank" rel="noreferrer">{h.title}</a>
                ) : (
                  h.title
                )}
              </li>
            ))}
          </ol>
          <button
            className="ip-undo"
            onClick={() => open && void automate(open, false)}
          >
            hand it back to me
          </button>
        </div>
      ) : null}

      {/* Portfolio */}
      <section className="ip-pf" aria-label="Portfolio">
        <div className="ip-pf-head">
          <span className="ip-k">Portfolio</span>
          <span className="ip-legend"><i className="sw sw-set" /> set by you</span>
          <span className="ip-legend"><i className="sw sw-sug" /> proposed / estimated</span>
          <button
            className="ip-project"
            onClick={() => void runProjection()}
            disabled={projecting}
          >
            {projecting ? "sweeping 1.13 M signals…" : "sweep for more like this"}
          </button>
          <span className="ip-legend ip-readonly">changes nothing · ~4 s</span>
        </div>

        {proj && !proj.ready ? (
          <p className="ip-projnote">
            The interest model is not ready yet — it needs at least 25 ratings
            with 5 of them positive (you have {proj.model.n} and{" "}
            {proj.model.positives}). Until then a sweep would only mirror the
            corpus back at you.
          </p>
        ) : null}
        {proj?.ready ? (
          <p className="ip-projnote">
            Swept every signal in the corpus against what you rated:{" "}
            <b>{proj.n_hits}</b> matched your interest, falling into{" "}
            <b>{proj.blips.length}</b> topics — <b>{suggested.length}</b> of them
            not on your table. Their position is a <em>proposal</em>: maturity
            from each topic&rsquo;s own history, relevance estimated by rating a
            random sample of it the way you would. Rate one and it turns from
            vermillion to chartreuse.
          </p>
        ) : null}

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
              Diffusion curve with the attention bump. The maturity stages sit
              where a topic stands on it — that is the derivation, not
              ornament. Share of signal volume measures attention, however, not
              market readiness; which is why market evidence counts equally.
            </p>
          </div>

          <div className="ip-grid">
            <div className="ip-corner">
              <span>Maturity ↓</span>
              <span>Relevance →</span>
            </div>
            {["Unrated", ...RELEVANCE.map((r) => r.label)].map((l, i) => (
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
                  const sugg = suggested.filter(
                    (b) => b.stage === s.key && b.rel_stage === rk
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
                            {f.n_rated ? `${f.n_rated} rated` : "unrated"}
                            {f.spread > 1 ? " · raters disagree" : ""}
                          </span>
                        </button>
                      ))}
                      {sugg.map((b) => (
                        <SuggestedBlip key={b.field_key} blip={b}
                                       onAdd={() => {
                                         void fetch("/api/foresight/instrument", {
                                           method: "POST",
                                           headers: { "content-type": "application/json" },
                                           body: JSON.stringify({ add: b.field_key, label: b.label }),
                                         }).then(() => {
                                           void loadBoard();
                                           setOpen(b.field_key);
                                         });
                                       }} />
                      ))}
                      {rk && (items.length || sugg.length) ? (
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

/**
 * Fortschritt zur Automatisierung.
 *
 * Bis 2026-08-07 stand hier „12 / 48 for this topic" — eine Zahl, die zwar
 * stimmte, aber das Falsche zählte. Gemessen (docs/instrument_learning_curve.md)
 * hängt die Güte des Modells nicht an der Zahl der Bewertungen, sondern an der
 * Zahl der POSITIVEN darunter: bei 5–7 Positiven liegt die Präzision an der
 * Spitze bei 52 %, bei 18–27 bei 72 %. Wer 48 Signale sichtet und dabei zwei
 * relevante findet, ist trotz voller Leiste kaum weiter.
 *
 * Die Leiste zeigt deshalb die Positiven — und, weil das ohne Bezug eine nackte
 * Zahl wäre, was sie freischalten und mit welcher Genauigkeit.
 */
function AutomationBar({
  auto, field, done, busy, onAutomate,
}: {
  auto: Automation;
  field: Field | null;
  done: number;
  busy: boolean;
  onAutomate: () => void;
}) {
  const pct = Math.min(100, (auto.positives / auto.min_positives) * 100);
  // Erwartete Restarbeit bei der bisher beobachteten Trefferquote. Ohne
  // belastbare Quote wird nicht geschätzt, sondern geschwiegen.
  const toSift =
    auto.hit_rate && auto.hit_rate > 0.01
      ? Math.ceil(auto.needed / auto.hit_rate)
      : null;

  return (
    <div className="ip-progress">
      <span className="ip-k">{field?.automated ? "Automated" : "Automation"}</span>
      <span className={`ip-p-bar ${auto.unlocked ? "is-full" : ""}`} aria-hidden="true">
        <span style={{ width: `${pct}%` }} />
      </span>

      {field?.automated ? (
        <span className="ip-p-n is-on">
          this topic is rated by the model
          {field.automated_accuracy
            ? ` · ~${Math.round(field.automated_accuracy * 100)}% precision`
            : ""}
        </span>
      ) : auto.unlocked ? (
        <span className="ip-p-n is-on">
          {auto.positives} relevant found — automation unlocked at ~
          {Math.round((auto.accuracy ?? 0) * 100)}% precision
        </span>
      ) : auto.positives < 5 ? (
        <span className="ip-p-n">
          {auto.positives} of {auto.min_positives} relevant signals — the model
          needs 5 before it can suggest anything
        </span>
      ) : (
        <span className="ip-p-n">
          {auto.needed} more relevant {auto.needed === 1 ? "signal" : "signals"}{" "}
          until automation unlocks at ~
          {Math.round((auto.accuracy ?? 0.5) * 100)}→
          {Math.round((auto.next_accuracy ?? 0.71) * 100)}% precision
        </span>
      )}

      {auto.unlocked && !field?.automated ? (
        <button className="ip-automate" onClick={onAutomate} disabled={busy}>
          {busy ? "rating the field…" : "⚡ Automate relevance rating"}
        </button>
      ) : null}

      <span className="ip-p-note">
        {field?.automated ? (
          <>
            Every signal in this topic now carries a model score instead of your
            judgement. Nothing was written into your ratings — the model does not
            train on its own output. Rate more by hand any time; the estimate
            follows.
          </>
        ) : (
          <>
            {done} rated on this topic, {auto.positives} of {auto.rated} rated
            relevant overall ({auto.hit_rate
              ? `${Math.round(auto.hit_rate * 100)}%`
              : "—"} hit rate)
            {toSift && !auto.unlocked ? `, so roughly ${toSift} more to sift` : ""}.
            What the model learns from is the <b>relevant</b> ones — 48 signals
            with two hits move it barely at all. Measured: at 5–7 relevant the
            top of the ranking is 52 % right, at 18–27 it is 72 %.
          </>
        )}
      </span>
    </div>
  );
}

function SuggestedBlip({ blip, onAdd }: { blip: Blip; onAdd: () => void }) {
  const [show, setShow] = useState(false);
  return (
    <div className="ip-sblip-wrap">
      <button className="ip-blip is-sug" onClick={() => setShow(!show)}>
        <span className="ip-blip-l">{blip.label}</span>
        <span className="ip-blip-n">
          {blip.n} of {blip.field_n.toLocaleString("en-US")} match · est. {blip.relevance}
        </span>
      </button>
      {show ? (
        <div className="ip-sblip-pop">
          <p>
            {blip.n} signals here match what you rated highly. Estimated
            relevance <b>{blip.relevance}</b> from a random sample of the topic —
            the same measure your own ratings produce, calibrated to how you
            rate. Maturity: {blip.note ?? "no clear pattern"}
          </p>
          <ul>
            {blip.hits.map((h) => (
              <li key={h.id}>
                {h.url ? <a href={h.url} target="_blank" rel="noreferrer">{h.title}</a> : h.title}
              </li>
            ))}
          </ul>
          <button className="ip-sblip-add" onClick={onAdd}>
            put on the table and rate →
          </button>
        </div>
      ) : null}
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
        <button onClick={onClose} aria-label="Close">✕</button>
      </div>
      <div className="ip-drawer-grid">
        <div>
          <span className="ip-k">
            Maturity — {STAGES.find((s) => s.key === field.stage)?.label}
          </span>
          {/* The note states its own origin — a prefixed label would double it
              (“from the shape of its history. From the shape of its history.
              Stable for 17 years…”). The label only appears where it does not. */}
          <p className="ip-drawer-t">
            {field.basis === "conflict" || field.basis === "default" ? null : (
              <em>{BASIS_LABEL[field.basis] ?? field.basis} · </em>
            )}
            {field.note}
          </p>
        </div>
        <div>
          <span className="ip-k">Relevance — your judgement</span>
          <p className="ip-drawer-t">
            {field.n_rated
              ? `${field.n_rated} signals from ${field.n_raters} rater${
                  field.n_raters > 1 ? "s" : ""
                }, weighted by expertise. Mean ${field.relevance}.${
                  field.spread > 1
                    ? " The raters disagree — the spread is marked on the point."
                    : ""
                }`
              : "Not yet rated. Relevance depends on your business, not on the signal space — nobody can do that part for you."}
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

      .ip-head { display: grid; grid-template-columns: 1fr auto; gap: 2rem; align-items: end; padding: 2.5rem 0 1.6rem; border-bottom: 1px solid var(--color-border); }
      .ip-eyebrow { font-family: var(--font-mono); font-size: 9px; letter-spacing: .28em; text-transform: uppercase; color: var(--color-accent); }
      .ip-title { font-size: clamp(2.4rem, 6vw, 4rem); line-height: .95; margin: .5rem 0 .7rem; color: var(--color-paper); font-weight: 400; letter-spacing: -.02em; }
      .ip-title em { font-style: italic; color: var(--color-accent); }
      .ip-lede { max-width: 44em; font-size: .95rem; line-height: 1.6; color: var(--color-text); margin: 0; }
      .ip-lede strong { color: var(--color-paper); font-weight: 500; }
      .ip-specs { display: flex; gap: 1.6rem; margin: 0; }
      .ip-specs dt { font-family: var(--font-mono); font-size: 8.5px; letter-spacing: .18em; text-transform: uppercase; color: var(--color-muted); }
      .ip-specs dd { font-family: var(--font-mono); font-size: 1.15rem; color: var(--color-paper); margin: .2rem 0 0; }
      .ip-run { display: flex; align-items: center; gap: 1.5rem; flex-wrap: wrap; padding: 1rem 0 .2rem; }
      .ip-run-l p { font-size: .82rem; line-height: 1.5; color: var(--color-muted); margin: .25rem 0 0; max-width: 44em; }
      .ip-resetbtn { margin-left: auto; font-family: var(--font-mono); font-size: 10px; letter-spacing: .18em; text-transform: uppercase; padding: .6rem 1.1rem; border: 1px solid var(--color-border); background: transparent; color: var(--color-muted); cursor: pointer; transition: border-color .16s, color .16s; }
      .ip-resetbtn:hover:not(:disabled) { border-color: var(--sug); color: var(--sug); }
      .ip-resetbtn:disabled { opacity: .3; cursor: not-allowed; }
      .ip-run-confirm { margin-left: auto; border: 1px solid var(--sug); border-left-width: 2px; padding: .7rem .9rem; background: color-mix(in srgb, var(--sug) 8%, transparent); max-width: 34rem; }
      .ip-run-confirm h3 { margin: 0 0 .5rem; font-size: .95rem; font-weight: 500; color: var(--color-paper); }
      .ip-run-list { list-style: none; margin: 0 0 .6rem; padding: 0; display: grid; gap: .3rem; }
      .ip-run-list li { font-size: .8rem; line-height: 1.45; color: var(--color-text); padding-left: .9rem; position: relative; }
      .ip-run-list li::before { content: "✕"; position: absolute; left: 0; color: var(--sug); font-size: .7rem; top: .15rem; }
      .ip-run-list b { color: var(--color-paper); font-weight: 600; }
      .ip-run-list em { font-style: normal; color: var(--color-muted); }
      .ip-run-safe { font-size: .76rem !important; color: var(--color-muted) !important; border-top: 1px solid var(--color-border); padding-top: .5rem; }
      .ip-run-confirm p { font-size: .8rem; line-height: 1.5; color: var(--color-text); margin: 0 0 .6rem; }
      .ip-run-confirm div { display: flex; gap: .4rem; }
      .ip-danger, .ip-cancel { font-family: var(--font-mono); font-size: 9.5px; letter-spacing: .16em; text-transform: uppercase; padding: .45rem .9rem; border: 1px solid var(--color-border); background: transparent; color: var(--color-muted); cursor: pointer; }
      .ip-danger { border-color: var(--sug); background: var(--sug); color: var(--paper); font-weight: 600; }
      .ip-cancel:hover { color: var(--color-paper); border-color: var(--color-paper); }
      .ip-readonly { margin-left: 0 !important; }

      .ip-k { font-family: var(--font-mono); font-size: 9px; letter-spacing: .22em; text-transform: uppercase; color: var(--color-accent); }

      /* Rating run — paper on a dark table */
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

      .ip-keys { color: #8a897e !important; }
      .ip-suggest { margin: 1.1rem 0 0; font-size: .78rem; line-height: 1.5; color: #6b6a60; display: flex; flex-wrap: wrap; gap: .5rem; align-items: baseline; }
      .ip-sug-badge { font-family: var(--font-mono); font-size: 8.5px; letter-spacing: .16em; text-transform: uppercase; color: var(--paper); background: var(--sug); padding: .1rem .4rem; }

      .ip-progress { grid-column: 2; display: grid; grid-template-columns: auto 12rem auto; gap: .8rem; align-items: center; margin-top: 1.1rem; }
      .ip-p-bar { height: 3px; background: color-mix(in srgb, var(--color-paper) 14%, transparent); display: block; }
      .ip-p-bar span { display: block; height: 100%; background: var(--color-accent); transition: width .3s; }
      .ip-p-n { font-family: var(--font-mono); font-size: 9px; letter-spacing: .12em; text-transform: uppercase; color: var(--color-muted); }
      .ip-p-note { grid-column: 1 / -1; font-size: .74rem; line-height: 1.5; color: var(--color-muted); max-width: 52em; }
      .ip-p-note b { color: var(--color-text); font-weight: 500; }
      .ip-p-bar.is-full span { background: var(--sug); }
      .ip-p-n.is-on { color: var(--sug); }
      .ip-automate { font-family: var(--font-mono); font-size: 9.5px; letter-spacing: .16em; text-transform: uppercase; padding: .45rem 1rem; border: 1px solid var(--sug); background: var(--sug); color: var(--paper); font-weight: 600; cursor: pointer; justify-self: start; }
      .ip-automate:hover:not(:disabled) { background: transparent; color: var(--sug); }
      .ip-automate:disabled { opacity: .55; cursor: wait; }
      .ip-autoresult { border: 1px solid var(--sug); border-left-width: 2px; background: color-mix(in srgb, var(--sug) 7%, transparent); padding: .8rem 1rem; margin: 1rem 0 0; }
      .ip-autoresult h3 { margin: 0 0 .4rem; font-size: .95rem; font-weight: 500; color: var(--color-paper); }
      .ip-autoresult p { font-size: .8rem; line-height: 1.55; color: var(--color-text); margin: 0 0 .6rem; max-width: 56em; }
      .ip-autoresult ol { margin: 0; padding-left: 1.2rem; display: grid; gap: .2rem; }
      .ip-autoresult li { font-size: .78rem; line-height: 1.35; color: var(--color-muted); }
      .ip-autoresult li b { font-family: var(--font-mono); font-size: 9px; color: var(--sug); }
      .ip-autoresult a { color: var(--color-text); text-decoration: none; border-bottom: 1px solid var(--color-border); }
      .ip-autoresult a:hover { color: var(--color-accent); border-color: var(--color-accent); }
      .ip-undo { font-family: var(--font-mono); font-size: 8.5px; letter-spacing: .14em; text-transform: uppercase; padding: .3rem .7rem; border: 1px solid var(--color-border); background: transparent; color: var(--color-muted); cursor: pointer; margin-top: .6rem; }
      .ip-undo:hover { border-color: var(--color-paper); color: var(--color-paper); }

      /* Portfolio */
      .ip-pf { border-top: 1px solid var(--color-border); padding-top: 2rem; }
      .ip-pf-head { display: flex; gap: 1.4rem; align-items: center; margin-bottom: 1rem; flex-wrap: wrap; }
      .ip-legend { display: flex; align-items: center; gap: .4rem; font-family: var(--font-mono); font-size: 8.5px; letter-spacing: .14em; text-transform: uppercase; color: var(--color-muted); }
      .sw { width: 10px; height: 10px; display: inline-block; }
      .sw-set { background: var(--color-accent); }
      .sw-sug { background: var(--sug); }
      .ip-project { margin-left: auto; font-family: var(--font-mono); font-size: 9px; letter-spacing: .16em; text-transform: uppercase; padding: .4rem .9rem; border: 1px solid var(--sug); background: transparent; color: var(--sug); cursor: pointer; }
      .ip-project:hover:not(:disabled) { background: var(--sug); color: var(--paper); }
      .ip-project:disabled { opacity: .5; cursor: wait; }
      .ip-projnote { font-size: .8rem; line-height: 1.6; color: var(--color-text); margin: 0 0 1rem; max-width: 60em; border-left: 2px solid var(--sug); padding-left: .8rem; }
      .ip-projnote b { color: var(--color-paper); font-weight: 500; }
      .ip-projnote em { color: var(--sug); font-style: normal; }

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

      .ip-blip { text-align: left; display: grid; gap: .12rem; padding: .35rem .45rem; background: color-mix(in srgb, var(--color-accent) calc(var(--w, .5) * 16%), transparent); border: 1px solid color-mix(in srgb, var(--color-accent) calc(var(--w, .5) * 70%), var(--color-border)); cursor: pointer; transition: transform .18s, border-color .18s; width: 100%; }
      .ip-blip:hover { transform: translateX(2px); }
      .ip-blip.is-on { border-color: var(--color-accent); }
      .ip-blip.is-guess { border-style: dashed; }
      .ip-blip.is-sug { background: color-mix(in srgb, var(--sug) 10%, transparent); border-color: color-mix(in srgb, var(--sug) 55%, transparent); border-style: dashed; }
      .ip-blip.is-sug:hover { border-color: var(--sug); }
      .ip-blip-l { font-size: .78rem; line-height: 1.2; color: var(--color-paper); }
      .ip-blip-n { font-family: var(--font-mono); font-size: 7.5px; letter-spacing: .1em; text-transform: uppercase; color: var(--color-muted); }
      .ip-advice { margin-top: auto; font-family: var(--font-mono); font-size: 7.5px; letter-spacing: .1em; text-transform: uppercase; color: var(--color-muted); }

      .ip-sblip-wrap { position: relative; }
      .ip-sblip-pop { position: absolute; z-index: 20; top: calc(100% + 3px); left: 0; width: 22rem; max-width: 60vw; background: var(--color-card); border: 1px solid var(--sug); padding: .7rem .8rem; box-shadow: 0 18px 40px -18px rgba(0,0,0,.9); }
      .ip-sblip-pop p { font-size: .76rem; line-height: 1.5; color: var(--color-text); margin: 0 0 .5rem; }
      .ip-sblip-pop b { color: var(--color-paper); }
      .ip-sblip-pop ul { list-style: none; margin: 0 0 .6rem; padding: 0; display: grid; gap: .2rem; }
      .ip-sblip-pop li { font-size: .74rem; line-height: 1.3; color: var(--color-muted); }
      .ip-sblip-pop a { color: var(--color-text); text-decoration: none; border-bottom: 1px solid var(--color-border); }
      .ip-sblip-pop a:hover { color: var(--color-accent); border-color: var(--color-accent); }
      .ip-sblip-add { font-family: var(--font-mono); font-size: 8.5px; letter-spacing: .16em; text-transform: uppercase; padding: .35rem .7rem; border: 1px solid var(--sug); background: var(--sug); color: var(--paper); cursor: pointer; width: 100%; }

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
