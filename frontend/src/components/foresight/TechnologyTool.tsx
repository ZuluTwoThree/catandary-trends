"use client";

import { useState } from "react";
import {
  clusterChoices, clusterHeadline, clusterHint, gateVerdict, offTopicHeadline,
  suggestionQueries, type Gate,
} from "@/lib/techGate";

/**
 * Merged Technology tool (#28/#36/#42/#43). ONE input → ONE resolved domain (the
 * user picks the CPC classes) → ONE canonical TIR. Two complementary views over the
 * same selection: the K(t) improvement-rate trajectory, and the cross-tier lead
 * time (research→patent→funding→market). Replaces the two divergent tools.
 *
 * Query-quality gate (#67, pipeline/query_gate.py): the API's `gate.verdict` decides
 * what is shown BEFORE any number — off_topic → honest question with 2–3 nearest
 * real fields (clickable → new query); ambiguous → the field choice (clickable →
 * analysis on exactly that field); ok → the unchanged fast path.
 */

interface Point { year: number; K: number; K_lo?: number; K_hi?: number; n: number; complete: boolean; early_sparse?: boolean }
// NB: the API additionally returns direction/direction_de/reason — deliberately
// NOT typed here: direction labels are withdrawn from all frontend views (#68;
// preregistered holdout 4/10 — TIR is a relative development measure, not an
// early-warning signal). Do not reintroduce without a validated momentum signal.
interface Traj {
  points?: Point[];
  K_latest?: number | null; K_median?: number | null; K_recent?: number | null;
  calibrated?: boolean | null; n_total?: number;
  earliest_year?: number | null; earliest_dense_year?: number | null;
}
interface Candidate { symbol: string; title: string; dist: number | null; n: number; default: boolean }
interface Tier { n: number; first: number | null; takeoff: number | null; median: number | null; series: Record<string, number>; is_share: boolean }
interface Lead {
  tiers: Record<string, Tier>;
  lead_science_market: number | null;
  lead_patent_market: number | null;
  concurrent: boolean;
  established?: boolean;
}
interface HubPatent { pub: string; cites: number; title: string; year: string | null; url: string }
interface Analysis {
  query?: string; off_topic?: boolean; nearest_dist?: number;
  gate?: Gate | null;
  candidates?: Candidate[]; selection?: string[];
  trajectory?: Traj | null; leadtime?: Lead | null; verdict?: string | null;
  top_patents?: HubPatent[]; error?: string;
}

const TIER_LABEL: Record<string, string> = {
  science: "Research", patent: "Patents", funding: "Funding", market: "Market",
};
const EXAMPLES = ["processed cheese", "solid-state battery electrolyte", "mRNA vaccine manufacturing", "perovskite tandem solar cells"];

// CPC subgroup titles are frequently lowercase fragments that only make sense as a
// continuation of the parent group ("by addition of preservatives", "characterised
// by …"). Shown alone they read as gibberish; prefix an ellipsis so it's obviously a
// sub-facet, and tidy whitespace/trailing separators.
function cpcLabel(raw: string | undefined): string {
  const t = (raw || "").replace(/\s+/g, " ").replace(/[;,\s]+$/, "").trim();
  if (!t) return "—";
  return /^[a-z]/.test(t) ? `… ${t}` : t;
}

/* ---- trajectory chart: rate (%/yr, linear + CI band) or cumulative (index, log) ---- */
function Chart({ points, mode, earliestYear }: { points: Point[]; mode: "rate" | "cumulative"; earliestYear?: number | null }) {
  const W = 720, H = 240, PAD = { t: 22, r: 16, b: 26, l: 44 };
  if (points.length < 2) return null;
  const firstYr = points[0].year;
  // x-axis ALWAYS anchored at the earliest citation year; the span before the first
  // measurable point (few citations / central patents) is greyed.
  const x0 = Math.min(earliestYear ?? firstYr, firstYr);
  const x1 = Math.max(...points.map((p) => p.year));
  const plotW = W - PAD.l - PAD.r;
  const plotH = H - PAD.t - PAD.b;
  // Piecewise x-axis: the data-FREE sparse era [x0 → firstYr] is COMPRESSED into a
  // narrow strip (a broken axis) so the measured span gets the room; the data era
  // [firstYr → x1] is linear. Anchored at the earliest citation year either way.
  const hasSparse = firstYr > x0;
  const compW = hasSparse ? Math.min(46, plotW * 0.09) : 0;
  const px = (yr: number) =>
    yr <= firstYr
      ? PAD.l + ((yr - x0) / Math.max(firstYr - x0, 1)) * compW
      : PAD.l + compW + ((yr - firstYr) / Math.max(x1 - firstYr, 1)) * (plotW - compW);
  const complete = points.filter((p) => p.complete);
  const lastComplete = complete.length ? complete[complete.length - 1].year : x1;
  const xlabels = [x0, firstYr, lastComplete, x1].filter((v, i, a) => a.indexOf(v) === i);
  const cx = (hasSparse ? (px(x0) + px(firstYr)) / 2 : 0);

  // shared frame: compressed sparse-early strip [x0 → firstYr] + recent-immature band
  const frame = (
    <>
      {xlabels.map((yr) => (
        <text key={yr} x={px(yr)} y={H - PAD.b + 15} textAnchor="middle" style={{ font: "9px ui-monospace, monospace" }} fill="#8a8d82">{yr}</text>
      ))}
      {hasSparse && (
        <>
          <rect x={px(x0)} y={PAD.t} width={compW} height={plotH} fill="#8a8d82" opacity={0.1} />
          {/* axis-break marker + vertical label (the strip is too narrow for horizontal text) */}
          <line x1={px(firstYr)} x2={px(firstYr)} y1={PAD.t} y2={H - PAD.b} stroke="#8a8d82" strokeWidth={1} strokeDasharray="2 2" opacity={0.5} />
          <text x={cx} y={PAD.t + plotH / 2} textAnchor="middle" transform={`rotate(-90 ${cx} ${PAD.t + plotH / 2})`} style={{ font: "7px ui-sans-serif, system-ui" }} fill="#8a8d82">sparse · compressed</text>
        </>
      )}
      {x1 > lastComplete && (
        <>
          <rect x={px(lastComplete)} y={PAD.t} width={px(x1) - px(lastComplete)} height={plotH} fill="#8a8d82" opacity={0.06} />
          <text x={(px(lastComplete) + px(x1)) / 2} y={PAD.t + 10} textAnchor="middle" style={{ font: "8px ui-sans-serif, system-ui" }} fill="#8a8d82">still immature</text>
        </>
      )}
    </>
  );

  if (mode === "cumulative") {
    // compound (1+K/100) over complete points; index = 1.0 at the first complete year.
    // Compute each cumulative value independently (no render-scope mutation): y_i is
    // the product of (1+K_j/100) for j=1..i (complete is small — years, not rows).
    const cs = complete.map((p, i) => ({
      year: p.year,
      y: complete.slice(1, i + 1).reduce((acc, q) => acc * (1 + q.K / 100), 1),
    }));
    const yMax = Math.max(...cs.map((s) => s.y), 2);
    const logMax = Math.log10(yMax) || 1;
    const py = (v: number) => H - PAD.b - (Math.log10(Math.max(v, 1)) / logMax) * plotH;
    const decades: number[] = [];
    for (let e = 0; Math.pow(10, e) <= yMax * 1.05; e++) decades.push(Math.pow(10, e));
    const seg = cs.map((s, i) => `${i ? "L" : "M"}${px(s.year).toFixed(1)},${py(s.y).toFixed(1)}`).join(" ");
    return (
      <svg viewBox={`0 0 ${W} ${H}`} className="block w-full max-w-full h-auto" role="img" aria-label="cumulative improvement index over time">
        <text x={PAD.l} y={PAD.t - 8} textAnchor="middle" style={{ font: "8px ui-monospace, monospace" }} fill="#8a8d82">× since start</text>
        {decades.map((v) => (
          <g key={v}>
            <line x1={PAD.l} x2={W - PAD.r} y1={py(v)} y2={py(v)} stroke="#2a2d25" strokeWidth={1} />
            <text x={PAD.l - 6} y={py(v) + 3} textAnchor="end" style={{ font: "9px ui-monospace, monospace" }} fill="#8a8d82">{v >= 1000 ? `${v / 1000}k` : v}×</text>
          </g>
        ))}
        {frame}
        <path d={seg} fill="none" stroke="#d4ff3a" strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" />
      </svg>
    );
  }

  // rate mode (linear, with CI band)
  const rawMax = Math.max(...points.map((p) => p.K_hi ?? p.K), 1);
  const step = rawMax > 40 ? 20 : rawMax > 20 ? 10 : rawMax > 8 ? 5 : 2;
  const y1 = Math.ceil((rawMax * 1.08) / step) * step;
  const py = (k: number) => H - PAD.b - (k / y1) * plotH;
  const seg = (pts: Point[]) => pts.map((p, i) => `${i ? "L" : "M"}${px(p.year).toFixed(1)},${py(p.K).toFixed(1)}`).join(" ");
  const band = (pts: Point[]) => {
    const w = pts.filter((p) => p.K_hi != null && p.K_lo != null);
    if (w.length < 2) return "";
    const up = w.map((p, i) => `${i ? "L" : "M"}${px(p.year).toFixed(1)},${py(p.K_hi as number).toFixed(1)}`).join(" ");
    const dn = [...w].reverse().map((p) => `L${px(p.year).toFixed(1)},${py(p.K_lo as number).toFixed(1)}`).join(" ");
    return `${up} ${dn} Z`;
  };
  const tail = points.filter((p) => p.year >= lastComplete);
  const yticks: number[] = [];
  for (let v = 0; v <= y1 + 0.001; v += step) yticks.push(v);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="block w-full max-w-full h-auto" role="img" aria-label="TIR rate over time">
      <text x={PAD.l} y={PAD.t - 8} textAnchor="middle" style={{ font: "8px ui-monospace, monospace" }} fill="#8a8d82">%/yr</text>
      {yticks.map((v) => (
        <g key={v}>
          <line x1={PAD.l} x2={W - PAD.r} y1={py(v)} y2={py(v)} stroke="#2a2d25" strokeWidth={1} />
          <text x={PAD.l - 6} y={py(v) + 3} textAnchor="end" style={{ font: "9px ui-monospace, monospace" }} fill="#8a8d82">{v}</text>
        </g>
      ))}
      {frame}
      {band(complete) && <path d={band(complete)} fill="#d4ff3a" opacity={0.1} stroke="none" />}
      <path d={seg(complete)} fill="none" stroke="#d4ff3a" strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" />
      {tail.length >= 2 && <path d={seg(tail)} fill="none" stroke="#8a8d82" strokeWidth={1.5} strokeDasharray="3 3" strokeLinejoin="round" strokeLinecap="round" />}
    </svg>
  );
}

/* ---- tier activity sparkline ---- */
function Spark({ series }: { series: Record<string, number> }) {
  const X0 = 1990, X1 = 2026;
  const years = Array.from({ length: X1 - X0 + 1 }, (_, i) => X0 + i);
  const max = Math.max(1, ...Object.values(series));
  return (
    <svg width="100%" height={20} viewBox={`0 0 ${years.length} 20`} preserveAspectRatio="none" className="block w-full" role="img" aria-label={`activity ${X0}–${X1}`}>
      {years.map((y, i) => {
        const n = series[String(y)] ?? 0;
        if (!n) return null;
        const h = Math.max(1, (n / max) * 19);
        return <rect key={y} x={i + 0.1} y={20 - h} width={0.8} height={h} className="fill-accent/70"><title>{`${y}: ${n.toLocaleString("en-US")}`}</title></rect>;
      })}
    </svg>
  );
}

export default function TechnologyTool() {
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);   // full query (embed)
  const [rerun, setRerun] = useState(false);       // trajectory-only re-run
  const [res, setRes] = useState<Analysis | null>(null);
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [err, setErr] = useState<string | null>(null);
  const [mode, setMode] = useState<"rate" | "cumulative">("rate");
  const [elapsed, setElapsed] = useState(0);       // Sekunden seit Analyse-Start

  // `codes` = the user's field pick after an ambiguous verdict: same phrase,
  // analysis on exactly those classes (the gate is skipped server-side).
  async function run(phrase: string, codes?: string[]) {
    const query = phrase.trim();
    if (query.length < 4 || loading) return;
    setLoading(true); setErr(null); setRes(null); setSel(new Set());
    setElapsed(0);
    const tick = setInterval(() => setElapsed((s) => s + 1), 1000);
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 115_000);
    try {
      const pick = codes?.length ? `&codes=${encodeURIComponent(codes.join(","))}` : "";
      const r = await fetch(`/api/foresight/analyze?q=${encodeURIComponent(query)}${pick}`, { signal: ctrl.signal });
      const data = (await r.json()) as Analysis;
      if (!r.ok || data.error) setErr(data.error || "Analysis failed — please try again.");
      else { setRes(data); setSel(new Set(data.selection || [])); }
    } catch (e) {
      setErr(e instanceof DOMException && e.name === "AbortError" ? "This took too long — try a narrower phrase." : "Network error — please try again.");
    } finally { clearTimeout(timer); clearInterval(tick); setLoading(false); }
  }

  // toggle a CPC class → re-run ONLY the trajectory for the new selection (no GPU)
  async function toggle(symbol: string) {
    const next = new Set(sel);
    if (next.has(symbol)) next.delete(symbol); else next.add(symbol);
    if (next.size === 0) return; // never allow an empty domain
    setSel(next);
    if (!res) return;
    setRerun(true);
    try {
      const codes = Array.from(next).join(",");
      const r = await fetch(`/api/foresight/analyze?codes=${encodeURIComponent(codes)}`);
      const data = (await r.json()) as Analysis;
      if (r.ok && data.trajectory) setRes({ ...res, trajectory: data.trajectory, top_patents: data.top_patents });
    } catch { /* keep previous trajectory on transient error */ }
    finally { setRerun(false); }
  }

  const traj = res?.trajectory;
  const lead = res?.leadtime;
  const selN = res?.candidates?.filter((c) => sel.has(c.symbol)).reduce((s, c) => s + c.n, 0) ?? 0;
  const verdict = res ? gateVerdict(res) : null;
  const suggestions = suggestionQueries(res?.gate);
  const choices = clusterChoices(res?.gate);

  return (
    <section className="border border-accent/40 bg-accent/5 p-4 sm:p-6 overflow-x-clip">
      <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-2">
        —— Technology Analysis · Improvement Rate & Innovation Chain
      </div>
      <p className="font-sans text-sm text-text leading-relaxed mb-4 max-w-3xl">
        Describe a technology. We resolve it into fine-grained patent classes —{" "}
        <span className="text-paper">you choose which</span> — and show, for exactly
        that selection, the improvement rate over time and how far research ran ahead
        of the market. Built from the patent citation graph (1990–2026).
      </p>

      <form onSubmit={(e) => { e.preventDefault(); run(q); }} className="flex flex-col sm:flex-row gap-2">
        <label htmlFor="tech-analyze-query" className="sr-only">Technology to analyze</label>
        <input id="tech-analyze-query" value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. processed cheese" maxLength={200}
          className="flex-1 min-w-0 bg-ink border border-border px-3 py-2 font-sans text-sm text-paper placeholder:text-muted focus:border-accent" />
        <button type="submit" disabled={loading || q.trim().length < 4}
          className="font-mono text-xs uppercase tracking-[0.14em] px-4 py-2 border border-accent text-accent hover:bg-accent hover:text-card disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-accent transition-colors shrink-0">
          {loading ? "Analyzing…" : "Analyze"}
        </button>
      </form>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {EXAMPLES.map((ex) => (
          <button key={ex} onClick={() => { setQ(ex); run(ex); }} disabled={loading}
            className="font-mono text-[10px] text-muted border border-border px-2 py-1 hover:text-accent hover:border-accent/50 disabled:opacity-40">{ex}</button>
        ))}
        <details className="relative">
          <summary className="list-none cursor-pointer font-mono text-[10px] text-muted border border-dashed border-border px-2 py-1 hover:text-accent hover:border-accent/50 select-none [&::-webkit-details-marker]:hidden">
            ⓘ How to search well
          </summary>
          <div className="absolute left-0 z-20 mt-1 w-[min(22rem,80vw)] border border-border bg-card p-3 shadow-lg">
            <p className="font-sans text-[12px] text-text leading-relaxed">
              <span className="text-paper">Describe a concrete technology, material or
              process</span> in 2–6 words — e.g. &quot;solid-state battery&quot;,
              &quot;vertical farming&quot;, &quot;heat pump&quot;.
            </p>
            <ul className="mt-2 font-sans text-[12px] text-muted leading-relaxed list-disc pl-4 space-y-1">
              <li>No company or product names, no abstract trends (&quot;future of work&quot;).</li>
              <li>The search maps your words to the <span className="text-text">closest
                  patent class</span> — for niche topics this can miss.</li>
              <li>So check under <span className="text-text">&quot;Measuring&quot;</span> whether the
                  matched field is your topic — the classes on the left are deselectable.</li>
            </ul>
          </div>
        </details>
      </div>

      {loading && (
        <p role="status" className="mt-5 font-mono text-xs text-muted animate-pulse" aria-live="polite">
          {elapsed < 25
            ? "1/3 · Finding matching patent classes (GPU model loading)…"
            : elapsed < 60
            ? "2/3 · Measuring the citation network of the matched classes…"
            : "3/3 · Computing improvement rate & innovation chain — large fields can take ~2 min…"}
          {" "}<span className="tabular-nums">{elapsed}s</span>
        </p>
      )}
      {err && <p role="alert" className="mt-5 font-mono text-xs text-red-400">⚠ {err}</p>}

      {res && !loading && verdict === "off_topic" && (
        <div className="mt-6 border border-border bg-card/40 p-5" data-testid="gate-off-topic">
          <p className="font-sans text-base text-paper">{offTopicHeadline(res.query)}</p>
          <p className="font-sans text-sm text-text mt-2">
            {res.gate?.reason
              ? <>{res.gate.reason[0].toUpperCase() + res.gate.reason.slice(1)}. </>
              : null}
            Describe a concrete technology, material or process — no number is better than a
            number about the wrong field.
          </p>
          {suggestions.length > 0 && (
            <div className="mt-3">
              <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted mb-1.5">
                Did you mean one of the nearest real fields?
              </p>
              <div className="flex flex-wrap gap-1.5">
                {suggestions.map((s) => (
                  <button key={s} onClick={() => { setQ(s); run(s); }} disabled={loading}
                    className="font-mono text-[11px] text-accent border border-accent/40 px-2 py-1 hover:bg-accent hover:text-card disabled:opacity-40 text-left">
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {res && !loading && verdict === "ambiguous" && (
        <div className="mt-6 border border-accent/40 bg-card/40 p-5" data-testid="gate-ambiguous">
          <p className="font-sans text-base text-paper">
            Your phrase points to more than one patent field — which one do you mean?
          </p>
          {res.gate?.reason && (
            <p className="font-sans text-sm text-text mt-2">
              {res.gate.reason[0].toUpperCase() + res.gate.reason.slice(1)}. We don&rsquo;t guess:
              pick the field and we analyze exactly that.
            </p>
          )}
          <ul className="mt-3 space-y-1.5">
            {choices.map((c) => (
              <li key={c.subclass}>
                <button onClick={() => run(res.query || q, c.symbols)} disabled={loading}
                  className="w-full text-left border border-border px-3 py-2 hover:border-accent/60 hover:bg-accent/5 disabled:opacity-40">
                  <span className="block font-sans text-[13px] text-paper">{clusterHeadline(c)}</span>
                  {c.detail && <span className="block font-sans text-[11px] text-text mt-0.5">{cpcLabel(c.detail)}</span>}
                  <span className="block font-mono text-[10px] text-muted mt-0.5">{clusterHint(c)}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {res && !loading && verdict === "ok" && (
        <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,260px)_1fr]">
          {/* left: user-selectable CPC classes */}
          <div className="min-w-0">
            <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted mb-2">
              Patent classes — your selection ({sel.size})
            </div>
            <div className="space-y-1 max-h-[320px] overflow-y-auto pr-1">
              {res.candidates?.map((c) => {
                const on = sel.has(c.symbol);
                return (
                  <button key={c.symbol} onClick={() => toggle(c.symbol)} disabled={rerun} aria-pressed={on}
                    className={`w-full text-left flex items-start gap-2 px-2 py-1.5 border transition-colors ${on ? "border-accent/50 bg-accent/10" : "border-border hover:border-border/80"} disabled:opacity-60`}>
                    <span className={`mt-0.5 font-mono text-[11px] shrink-0 ${on ? "text-accent" : "text-muted"}`}>{on ? "☑" : "☐"}</span>
                    <span className="min-w-0 flex-1">
                      <span className="font-mono text-[11px] text-paper break-words">{c.symbol}</span>
                      <span className="block font-sans text-[11px] text-muted leading-tight break-words">{cpcLabel(c.title)}</span>
                    </span>
                    <span className="font-mono text-[10px] text-muted shrink-0 tabular-nums">{c.n.toLocaleString("en-US")}</span>
                  </button>
                );
              })}
            </div>
            <p className="mt-2 font-mono text-[10px] text-muted">
              {selN.toLocaleString("en-US")} patents selected · toggle classes to recalculate live
            </p>
          </div>

          {/* right: trajectory + lead-time */}
          <div className="min-w-0">
            {/* The measured field in plain language — makes a neighbouring-domain
                embedding mismatch immediately visible. */}
            {(() => {
              const selTitles = (res.candidates || [])
                .filter((c) => sel.has(c.symbol))
                .map((c) => cpcLabel(c.title))
                .filter(Boolean);
              if (!selTitles.length) return null;
              const shown = selTitles.slice(0, 3).join(" · ");
              const more = selTitles.length - 3;
              return (
                <p className="font-sans text-[12px] text-text mb-2 border-l-2 border-accent/50 pl-2">
                  <span className="text-muted">Measuring:</span>{" "}
                  <span className="text-paper">{shown}{more > 0 ? ` · +${more} more` : ""}</span>
                  <span className="text-muted"> — not what you meant? Adjust the selection on the left.</span>
                </p>
              );
            })()}
            {res.verdict && <p className="font-sans text-sm text-paper mb-3 leading-snug">{res.verdict}</p>}

            <div className="flex flex-wrap items-baseline gap-3 mb-1">
              {traj?.calibrated ? (
                <span className="font-sans text-text">
                  Technology Improvement Rate{" "}
                  <span className="font-mono text-lg text-paper tabular-nums">~{traj.K_median}%</span>
                  <span className="text-muted"> /year</span>
                </span>
              ) : traj?.calibrated === false ? (
                <span className="font-sans text-sm text-muted">
                  Improving faster than we can reliably quantify (outside the calibrated range)
                </span>
              ) : (
                /* calibrated == null → data too thin, NOT "too fast" */
                <span className="font-sans text-sm text-muted">
                  Not enough patent data for a reliable rate — extend the selection on the left.
                </span>
              )}
              {traj?.earliest_year && (
                <span className="font-mono text-[10px] text-muted">
                  measured since {traj.earliest_year} · {2026 - traj.earliest_year} yrs of data
                </span>
              )}
              {rerun && <span role="status" className="font-mono text-[10px] text-muted animate-pulse">updating…</span>}
            </div>
            <p className="font-sans text-[11px] text-muted mb-2 max-w-3xl">
              TIR = how fast this field&rsquo;s patented performance improves per year
              (MIT method: SPNP citation centrality, Singh/Triulzi/Magee 2021). How to
              read it is up to you.
            </p>

            {traj?.points && traj.points.length >= 2 ? (
              <>
                {/* rate ↔ cumulative toggle */}
                <div className="flex gap-1 mb-2">
                  {(["rate", "cumulative"] as const).map((m) => (
                    <button key={m} onClick={() => setMode(m)} aria-pressed={mode === m}
                      className={`font-mono text-[10px] uppercase tracking-[0.12em] px-2 py-1 border transition-colors ${mode === m ? "border-accent/60 text-accent bg-accent/10" : "border-border text-muted hover:text-text"}`}>
                      {m === "rate" ? "Rate %/yr" : "Cumulative ×"}
                    </button>
                  ))}
                </div>
                <Chart points={traj.points} mode={mode} earliestYear={traj.earliest_year} />
              </>
            ) : (
              <p className="font-sans text-sm text-muted border-l-2 border-border pl-3">Not enough patent data in this selection for a trajectory — select more classes on the left.</p>
            )}

            <p className="font-sans text-[11px] text-muted mt-2 max-w-3xl">
              {mode === "cumulative"
                ? <>Cumulative progress index (start = 1× at the earliest citation year), the integral of the rate — log scale, so the slope matches the TIR and maturity shows up as flattening. A relative index, not absolute performance.</>
                : <>The x-axis starts at the earliest citation year; the data-sparse early era is <span className="text-text">compressed</span> as a broken axis and greyed out, as are the most recent immature years. Band = calibration uncertainty (~68%). The TIR value is the median over the measured history.</>}
            </p>

            {/* cross-tier lead time */}
            {lead && (
              <div className="mt-5 border-t border-border pt-4">
                <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted mb-3">Innovation chain — when it appeared in each tier</div>
                <div className="space-y-2">
                  {(["science", "patent", "funding", "market"] as const).map((t) => {
                    const tr = lead.tiers?.[t];
                    if (!tr) return null;
                    return (
                      <div key={t} className="grid grid-cols-[52px_1fr_auto] sm:grid-cols-[70px_1fr_auto] items-center gap-2 sm:gap-3">
                        <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-text">{TIER_LABEL[t]}</span>
                        <span className="min-w-0"><Spark series={tr.series} /></span>
                        <span className="font-mono text-[10px] text-muted tabular-nums shrink-0">{tr.median ? `~${tr.median}` : "—"}</span>
                      </div>
                    );
                  })}
                </div>
                <p className="font-sans text-[11px] text-muted mt-3">
                  {lead.established
                    ? "Established technology — research and patents already existed before our data window (1990). A research-to-market lead can't be measured here."
                    : <>
                        {lead.lead_science_market ? <>Research ran ~<span className="text-text">{lead.lead_science_market} years</span> ahead of the market. </> : null}
                        {lead.lead_patent_market ? <>Patents ~<span className="text-text">{lead.lead_patent_market} years</span> ahead of the market. </> : null}
                        {lead.concurrent ? "Research and market are moving in step." : null}
                        {!lead.lead_science_market && !lead.lead_patent_market && !lead.concurrent ? "No clear lead between tiers is measurable." : null}
                      </>}
                </p>
              </div>
            )}

            {/* most-cited (landmark) patents in the selection */}
            {res.top_patents && res.top_patents.length > 0 && (
              <div className="mt-5 border-t border-border pt-4">
                <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted mb-3">
                  Most-cited patents in this selection
                </div>
                <ul className="space-y-1.5">
                  {res.top_patents.map((p) => (
                    <li key={p.pub} className="flex items-start gap-3">
                      <span className="font-mono text-[11px] text-accent tabular-nums shrink-0 w-14 text-right">{p.cites}×</span>
                      <a href={p.url} target="_blank" rel="noopener noreferrer" className="min-w-0 flex-1 group">
                        <span className="font-sans text-[12px] text-text group-hover:text-paper break-words">{p.title || p.pub}</span>{" "}
                        <span className="font-mono text-[10px] text-muted whitespace-nowrap">{p.pub}{p.year ? ` · ${p.year}` : ""} ↗</span>
                      </a>
                    </li>
                  ))}
                </ul>
                <p className="mt-2 font-mono text-[10px] text-muted">Forward citations within the corpus · click opens Espacenet</p>
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
