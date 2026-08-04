"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { RadarView } from "@/lib/radar-shared";

/**
 * Die Portfoliodarstellung nach Blechschmidt (Quick Guide Trendmanagement,
 * Abb. 8.2, S. 98/99): Trendreife × Trendrelevanz, zwölf Felder, jedes mit
 * eigener Handlungsempfehlung.
 *
 * Die beiden Achsen haben grundverschiedene Erkenntnislage, und das Bild muss
 * das führen:
 *
 *   – **Trendreife** (y) leitet die Maschine aus Evidenz ab. Sechs
 *     Teilkriterien, je 0–4 Punkte, jedes an eine überprüfbare Schwelle
 *     gebunden und mit Begründung. Durchgezogen dargestellt.
 *   – **Trendrelevanz** (x) setzt der Nutzer. Sie hängt vom Unternehmen ab und
 *     steht prinzipiell nicht in unseren Daten. Solange sie fehlt, steht das
 *     Feld am linken Rand in einer eigenen Spalte „unbewertet" — nicht bei
 *     „gering", denn das wäre eine Aussage, die niemand getroffen hat.
 *
 * Ohne diese Führung verkauft das Bild eine Schätzung mit der Autorität einer
 * Messung.
 */

const MATURITY = [
  { key: "established", label: "Etabliert", band: "Implementieren" },
  { key: "maturing", label: "Reifend", band: "Berücksichtigen" },
  { key: "volatile", label: "Volatil", band: "Verstehen" },
  { key: "emerging", label: "Entstehend", band: "Beobachten" },
];

const RELEVANCE = [
  { key: "low", label: "Gering", band: "Opportunistisch" },
  { key: "medium", label: "Mittel", band: "Gleichwertig" },
  { key: "high", label: "Hoch", band: "Proaktiv" },
];

/** Blechschmidts zwölf Handlungsempfehlungen, aus den Achsenbändern gebildet. */
function advice(mat: string, rel: string): string {
  const m = MATURITY.find((x) => x.key === mat)?.band ?? "";
  const r = RELEVANCE.find((x) => x.key === rel)?.band ?? "";
  return `${m} · ${r}`;
}

interface Criterion {
  key: string;
  label: string;
  question: string | null;
  anchor_0: string | null;
  anchor_4: string | null;
  weight: number;
}
interface Score {
  scope_slug: string;
  criterion_key: string;
  points: number | null;
  note: string | null;
}
interface Maturity {
  scope_slug: string;
  score: number | null;
  stage: string | null;
  criteria: { key: string; label: string; points: number | null; weight: number;
              rationale: string; anchor: string | null; question: string }[];
  relevance_hint: Record<string, { points: number | null; why: string }>;
}

function relevanceStage(
  scores: Record<string, number | null>,
  criteria: Criterion[]
): { score: number | null; stage: string | null; complete: boolean } {
  let num = 0;
  let den = 0;
  let n = 0;
  for (const c of criteria) {
    const v = scores[c.key];
    if (v === null || v === undefined) continue;
    num += v * c.weight;
    den += c.weight;
    n++;
  }
  if (!den) return { score: null, stage: null, complete: false };
  const s = num / den;
  const stage = s >= 2.67 ? "high" : s >= 1.34 ? "medium" : "low";
  return { score: Math.round(s * 100) / 100, stage, complete: n === criteria.length };
}

export default function PortfolioBoard({ view }: { view: RadarView }) {
  const radar = view.config.slug;
  const [criteria, setCriteria] = useState<Criterion[]>([]);
  const [scores, setScores] = useState<Score[]>([]);
  const [maturity, setMaturity] = useState<Maturity[]>([]);
  const [open, setOpen] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    const r = await fetch(`/api/foresight/radar/relevance?radar=${radar}`);
    const d = await r.json();
    if (d?.error) return;
    setCriteria(d.criteria ?? []);
    setScores(d.scores ?? []);
    setMaturity(d.maturity ?? []);
  }, [radar]);

  useEffect(() => {
    void load();
  }, [load]);

  const byScope = useMemo(() => {
    const out: Record<string, Record<string, number | null>> = {};
    for (const s of scores) {
      (out[s.scope_slug] ??= {})[s.criterion_key] = s.points;
    }
    return out;
  }, [scores]);

  const matBy = useMemo(
    () => Object.fromEntries(maturity.map((m) => [m.scope_slug, m])),
    [maturity]
  );

  async function setPoints(scope: string, criterion: string, points: number | null) {
    setSaving(true);
    setScores((prev) => {
      const rest = prev.filter(
        (p) => !(p.scope_slug === scope && p.criterion_key === criterion)
      );
      return [...rest, { scope_slug: scope, criterion_key: criterion, points, note: null }];
    });
    await fetch("/api/foresight/radar/relevance", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ radar, scope, criterion, points }),
    });
    setSaving(false);
  }

  const placed = view.scopes.map((s) => {
    const m = matBy[s.slug];
    const rel = relevanceStage(byScope[s.slug] ?? {}, criteria);
    return { scope: s, mat: m ?? null, rel };
  });

  const unrated = placed.filter((p) => !p.rel.stage);

  return (
    <div className="pf">
      <div className="pf-legend">
        <span className="pf-k">Portfolio</span>
        <span className="pf-v">
          Trendreife — von uns aus Evidenz abgeleitet
        </span>
        <span className="pf-v pf-user">
          Trendrelevanz — von Ihnen bewertet
        </span>
        {saving ? <span className="pf-v">speichert…</span> : null}
      </div>

      <div className="pf-grid">
        <div className="pf-corner" />
        {["Unbewertet", ...RELEVANCE.map((r) => r.label)].map((l, i) => (
          <div key={l} className={`pf-colh ${i === 0 ? "is-empty" : ""}`}>
            {l}
            {i > 0 ? <span className="pf-band">{RELEVANCE[i - 1].band}</span> : null}
          </div>
        ))}

        {MATURITY.map((m) => (
          <div key={m.key} style={{ display: "contents" }}>
            <div className="pf-rowh">
              {m.label}
              <span className="pf-band">{m.band}</span>
            </div>
            {[null, ...RELEVANCE.map((r) => r.key)].map((rk, i) => {
              const cellItems = placed.filter(
                (p) => p.mat?.stage === m.key && (p.rel.stage ?? null) === rk
              );
              return (
                <div
                  key={`${m.key}-${rk ?? "none"}`}
                  className={`pf-cell ${i === 0 ? "is-empty" : ""}`}
                  title={rk ? advice(m.key, rk) : "Noch nicht bewertet"}
                >
                  {cellItems.map((it) => (
                    <button
                      key={it.scope.slug}
                      className={`pf-chip ${open === it.scope.slug ? "is-on" : ""}`}
                      onClick={() =>
                        setOpen(open === it.scope.slug ? null : it.scope.slug)
                      }
                    >
                      {it.scope.label}
                    </button>
                  ))}
                  {rk && cellItems.length ? (
                    <span className="pf-advice">{advice(m.key, rk)}</span>
                  ) : null}
                </div>
              );
            })}
          </div>
        ))}
      </div>

      {unrated.length ? (
        <p className="pf-hint">
          {unrated.length} von {placed.length} Feldern sind noch nicht bewertet
          und stehen deshalb links außerhalb des Rasters — nicht bei „gering“.
          Ihre Relevanz kann Ihnen niemand abnehmen: sie hängt von Ihrem
          Geschäft ab, nicht vom Signalraum.
        </p>
      ) : null}

      {open ? (
        <RelevancePanel
          scope={view.scopes.find((s) => s.slug === open)!}
          criteria={criteria}
          scores={byScope[open] ?? {}}
          maturity={matBy[open] ?? null}
          onSet={(k, v) => setPoints(open, k, v)}
          onClose={() => setOpen(null)}
        />
      ) : null}

      <style>{`
        .pf { margin-bottom: 1.6rem; }
        .pf-legend { display: flex; flex-wrap: wrap; gap: .9rem; align-items: baseline; margin-bottom: .7rem; }
        .pf-k { font-family: var(--font-mono); font-size: 9px; letter-spacing: .2em; text-transform: uppercase; color: var(--color-accent); }
        .pf-v { font-family: var(--font-mono); font-size: 9px; letter-spacing: .1em; text-transform: uppercase; color: var(--color-muted); }
        .pf-v.pf-user { color: var(--color-paper); border-bottom: 1px dashed var(--color-border); }
        .pf-grid { display: grid; grid-template-columns: 9rem repeat(4, 1fr); gap: 1px; background: var(--color-border); border: 1px solid var(--color-border); }
        .pf-corner, .pf-colh, .pf-rowh, .pf-cell { background: var(--color-ink); padding: .5rem .55rem; }
        .pf-colh, .pf-rowh { font-family: var(--font-mono); font-size: 9px; letter-spacing: .14em; text-transform: uppercase; color: var(--color-paper); display: grid; gap: .15rem; align-content: start; }
        .pf-colh.is-empty, .pf-cell.is-empty { background: color-mix(in srgb, var(--color-ink) 88%, var(--color-border)); }
        .pf-band { font-size: 8px; letter-spacing: .1em; color: var(--color-accent); }
        .pf-cell { min-height: 5.2rem; display: flex; flex-direction: column; gap: .25rem; }
        .pf-chip { text-align: left; font-size: .76rem; line-height: 1.25; padding: .25rem .4rem; border: 1px solid var(--color-border); background: transparent; color: var(--color-paper); cursor: pointer; }
        .pf-chip:hover { border-color: var(--color-paper); }
        .pf-chip.is-on { border-color: var(--color-accent); color: var(--color-accent); }
        .pf-advice { margin-top: auto; font-family: var(--font-mono); font-size: 8px; letter-spacing: .1em; text-transform: uppercase; color: var(--color-muted); }
        .pf-hint { font-size: .78rem; color: var(--color-muted); margin: .7rem 0 0; max-width: 60em; line-height: 1.55; }
      `}</style>
    </div>
  );
}

/** Bewertungsmaske eines Felds — links die Frage, rechts der Vorschlag. */
function RelevancePanel({
  scope,
  criteria,
  scores,
  maturity,
  onSet,
  onClose,
}: {
  scope: { slug: string; label: string };
  criteria: Criterion[];
  scores: Record<string, number | null>;
  maturity: Maturity | null;
  onSet: (criterion: string, points: number | null) => void;
  onClose: () => void;
}) {
  return (
    <section className="rp">
      <div className="rp-head">
        <h3 className="rp-t">{scope.label}</h3>
        <button className="rp-x" onClick={onClose} aria-label="Schließen">
          ✕
        </button>
      </div>

      {maturity ? (
        <div className="rp-mat">
          <p className="rp-h">
            Trendreife {maturity.score} von 4 — aus Evidenz abgeleitet
          </p>
          <dl className="rp-crit">
            {maturity.criteria.map((c) => (
              <div key={c.key}>
                <dt>
                  {c.points === null ? "—" : c.points}
                  <span className="rp-w">×{c.weight}</span>
                </dt>
                <dd>
                  <span className="rp-cl">{c.label}</span> {c.rationale}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      ) : null}

      <p className="rp-h">Trendrelevanz — Ihre Bewertung</p>
      <div className="rp-rel">
        {criteria.map((c) => {
          const hint = maturity?.relevance_hint?.[c.key];
          const val = scores[c.key];
          return (
            <div key={c.key} className="rp-row">
              <div className="rp-q">
                <span className="rp-cl">
                  {c.label} <span className="rp-w">×{c.weight}</span>
                </span>
                {c.question ? <span className="rp-sub">{c.question}</span> : null}
                <span className="rp-anch">
                  0 = {c.anchor_0} · 4 = {c.anchor_4}
                </span>
              </div>
              <div className="rp-scale" role="group" aria-label={c.label}>
                {[0, 1, 2, 3, 4].map((n) => (
                  <button
                    key={n}
                    className={`rp-b ${val === n ? "is-on" : ""}`}
                    onClick={() => onSet(c.key, val === n ? null : n)}
                    aria-pressed={val === n}
                  >
                    {n}
                  </button>
                ))}
              </div>
              <div className="rp-hint">
                {hint ? (
                  hint.points === null ? (
                    <span className="rp-nohint">{hint.why}</span>
                  ) : (
                    <>
                      <span className="rp-hp">Vorschlag {hint.points}</span>
                      <span className="rp-hw">{hint.why}</span>
                    </>
                  )
                ) : null}
              </div>
            </div>
          );
        })}
      </div>

      <style>{`
        .rp { border: 1px solid var(--color-accent); border-left-width: 2px; padding: 1rem 1.1rem; margin-top: 1rem; background: var(--color-card); }
        .rp-head { display: flex; align-items: baseline; gap: 1rem; margin-bottom: .8rem; }
        .rp-t { font-family: var(--font-serif, var(--font-sans)); font-size: 1.05rem; color: var(--color-paper); margin: 0; }
        .rp-x { margin-left: auto; background: transparent; border: 1px solid var(--color-border); color: var(--color-muted); cursor: pointer; padding: .1rem .4rem; }
        .rp-h { font-family: var(--font-mono); font-size: 9px; letter-spacing: .2em; text-transform: uppercase; color: var(--color-accent); margin: 1rem 0 .5rem; }
        .rp-mat { border-bottom: 1px solid var(--color-border); padding-bottom: .8rem; }
        .rp-mat .rp-h { margin-top: 0; }
        .rp-crit { display: grid; gap: .35rem; margin: 0; }
        .rp-crit > div { display: grid; grid-template-columns: 3.4rem 1fr; gap: .7rem; align-items: baseline; }
        .rp-crit dt { font-family: var(--font-mono); font-size: 11px; color: var(--color-paper); border: 1px solid var(--color-border); text-align: center; padding: .1rem 0; }
        .rp-crit dd { margin: 0; font-size: .78rem; line-height: 1.45; color: var(--color-muted); }
        .rp-cl { color: var(--color-paper); }
        .rp-w { font-family: var(--font-mono); font-size: 8px; color: var(--color-muted); }
        .rp-rel { display: grid; gap: .6rem; }
        .rp-row { display: grid; grid-template-columns: minmax(12rem, 1fr) auto minmax(10rem, 1.1fr); gap: .9rem; align-items: start; border-top: 1px solid color-mix(in srgb, var(--color-border) 60%, transparent); padding-top: .55rem; }
        .rp-q { display: grid; gap: .12rem; font-size: .8rem; }
        .rp-sub { color: var(--color-muted); font-size: .76rem; }
        .rp-anch { color: var(--color-muted); font-size: .7rem; font-style: italic; }
        .rp-scale { display: flex; gap: 2px; }
        .rp-b { width: 1.9rem; height: 1.9rem; font-family: var(--font-mono); font-size: 11px; border: 1px solid var(--color-border); background: transparent; color: var(--color-muted); cursor: pointer; }
        .rp-b:hover { color: var(--color-paper); border-color: var(--color-paper); }
        .rp-b.is-on { background: var(--color-accent); border-color: var(--color-accent); color: var(--color-ink); font-weight: 600; }
        .rp-hint { display: grid; gap: .15rem; font-size: .72rem; line-height: 1.4; color: var(--color-muted); }
        .rp-hp { font-family: var(--font-mono); font-size: 9px; letter-spacing: .12em; text-transform: uppercase; color: var(--color-accent); }
        .rp-nohint { font-style: italic; }
      `}</style>
    </section>
  );
}
