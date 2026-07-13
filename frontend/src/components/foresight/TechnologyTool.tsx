"use client";

import { useState } from "react";

/**
 * Merged Technology tool (#28/#36/#42/#43). ONE input → ONE resolved domain (the
 * user picks the CPC classes) → ONE canonical TIR. Two complementary views over the
 * same selection: the K(t) improvement-rate trajectory, and the cross-tier lead
 * time (research→patent→funding→market). Replaces the two divergent tools.
 */

interface Point { year: number; K: number; K_lo?: number; K_hi?: number; n: number; complete: boolean; early_sparse?: boolean }
interface Traj {
  points?: Point[]; direction?: string; direction_de?: string;
  K_latest?: number | null; K_median?: number | null; K_recent?: number | null;
  calibrated?: boolean | null; n_total?: number; reason?: string | null;
  earliest_year?: number | null; earliest_dense_year?: number | null;
}
interface Candidate { symbol: string; title: string; dist: number; n: number; default: boolean }
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
  candidates?: Candidate[]; selection?: string[];
  trajectory?: Traj | null; leadtime?: Lead | null; verdict?: string | null;
  top_patents?: HubPatent[]; error?: string;
}

const DIR_LABEL: Record<string, string> = {
  accelerating: "beschleunigt", steady: "stetig", maturing: "reift",
  decelerating: "verlangsamt sich", uncertain: "Richtung unsicher",
  insufficient_data: "zu wenig Daten",
};
const DIR_COLOR: Record<string, string> = {
  accelerating: "#bde63a", steady: "#8a8d82", maturing: "#fb923c",
  decelerating: "#fb7185", uncertain: "#8a8d82", insufficient_data: "#8a8d82",
};
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

/* ---- K(t) trajectory chart (with calibration uncertainty band) ---- */
function Chart({ points }: { points: Point[] }) {
  const W = 720, H = 240, PAD = { t: 22, r: 16, b: 26, l: 40 };
  if (points.length < 2) return null;
  const xs = points.map((p) => p.year);
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  const rawMax = Math.max(...points.map((p) => p.K_hi ?? p.K), 1);
  const step = rawMax > 40 ? 20 : rawMax > 20 ? 10 : rawMax > 8 ? 5 : 2;
  const y1 = Math.ceil((rawMax * 1.08) / step) * step;
  const px = (yr: number) => PAD.l + ((yr - x0) / Math.max(x1 - x0, 1)) * (W - PAD.l - PAD.r);
  const py = (k: number) => H - PAD.b - (k / y1) * (H - PAD.t - PAD.b);
  const complete = points.filter((p) => p.complete);
  const lastComplete = complete.length ? complete[complete.length - 1].year : x0;
  const seg = (pts: Point[]) => pts.map((p, i) => `${i ? "L" : "M"}${px(p.year).toFixed(1)},${py(p.K).toFixed(1)}`).join(" ");
  const band = (pts: Point[]) => {
    const w = pts.filter((p) => p.K_hi != null && p.K_lo != null);
    if (w.length < 2) return "";
    const up = w.map((p, i) => `${i ? "L" : "M"}${px(p.year).toFixed(1)},${py(p.K_hi as number).toFixed(1)}`).join(" ");
    const dn = [...w].reverse().map((p) => `L${px(p.year).toFixed(1)},${py(p.K_lo as number).toFixed(1)}`).join(" ");
    return `${up} ${dn} Z`;
  };
  const tail = points.filter((p) => p.year >= lastComplete);
  // left-edge "sparse early citations" boundary: first year that is no longer flagged
  const firstDense = points.find((p) => !p.early_sparse)?.year ?? x0;
  const yticks: number[] = [];
  for (let v = 0; v <= y1 + 0.001; v += step) yticks.push(v);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="block w-full max-w-full h-auto" role="img" aria-label="TIR trajectory over time">
      <text x={PAD.l} y={PAD.t - 8} textAnchor="middle" style={{ font: "8px ui-monospace, monospace" }} fill="#8a8d82">%/yr</text>
      {yticks.map((v) => (
        <g key={v}>
          <line x1={PAD.l} x2={W - PAD.r} y1={py(v)} y2={py(v)} stroke="#2a2d25" strokeWidth={1} />
          <text x={PAD.l - 6} y={py(v) + 3} textAnchor="end" style={{ font: "9px ui-monospace, monospace" }} fill="#8a8d82">{v}</text>
        </g>
      ))}
      {[x0, Math.round((x0 + lastComplete) / 2), lastComplete, x1].map((yr) => (
        <text key={yr} x={px(yr)} y={H - PAD.b + 15} textAnchor="middle" style={{ font: "9px ui-monospace, monospace" }} fill="#8a8d82">{yr}</text>
      ))}
      {firstDense > x0 && (
        <>
          <rect x={px(x0)} y={PAD.t} width={px(firstDense) - px(x0)} height={H - PAD.t - PAD.b} fill="#8a8d82" opacity={0.06} />
          <text x={(px(x0) + px(firstDense)) / 2} y={PAD.t + 10} textAnchor="middle" style={{ font: "8px ui-sans-serif, system-ui" }} fill="#8a8d82">frühe Zitationen spärlich</text>
        </>
      )}
      {x1 > lastComplete && (
        <>
          <rect x={px(lastComplete)} y={PAD.t} width={px(x1) - px(lastComplete)} height={H - PAD.t - PAD.b} fill="#8a8d82" opacity={0.06} />
          <text x={(px(lastComplete) + px(x1)) / 2} y={PAD.t + 10} textAnchor="middle" style={{ font: "8px ui-sans-serif, system-ui" }} fill="#8a8d82">Zitationen noch unreif</text>
        </>
      )}
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

  async function run(phrase: string) {
    const query = phrase.trim();
    if (query.length < 4 || loading) return;
    setLoading(true); setErr(null); setRes(null); setSel(new Set());
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 115_000);
    try {
      const r = await fetch(`/api/foresight/analyze?q=${encodeURIComponent(query)}`, { signal: ctrl.signal });
      const data = (await r.json()) as Analysis;
      if (!r.ok || data.error) setErr(data.error || "Analyse fehlgeschlagen");
      else { setRes(data); setSel(new Set(data.selection || [])); }
    } catch (e) {
      setErr(e instanceof DOMException && e.name === "AbortError" ? "Zeitüberschreitung — versuch eine engere Phrase" : "Netzwerkfehler");
    } finally { clearTimeout(timer); setLoading(false); }
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
  const dir = traj?.direction || "";
  const lead = res?.leadtime;
  const selN = res?.candidates?.filter((c) => sel.has(c.symbol)).reduce((s, c) => s + c.n, 0) ?? 0;

  return (
    <section className="border border-accent/40 bg-accent/5 p-4 sm:p-6 overflow-x-clip">
      <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-2">
        —— Technologie-Analyse · Verbesserungsrate & Innovationskette
      </div>
      <p className="font-sans text-sm text-text leading-relaxed mb-4 max-w-3xl">
        Beschreibe eine Technologie. Wir lösen sie auf feine Patentklassen auf —{" "}
        <span className="text-paper">du wählst, welche</span> — und zeigen für genau
        diese Auswahl die Verbesserungsrate über die Zeit und wie früh Forschung dem
        Markt vorausging. Aus dem Patent-Zitationsgraphen (1990–2026).
      </p>

      <form onSubmit={(e) => { e.preventDefault(); run(q); }} className="flex flex-col sm:flex-row gap-2">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="z. B. processed cheese" maxLength={200}
          className="flex-1 min-w-0 bg-ink border border-border px-3 py-2 font-sans text-sm text-paper placeholder:text-muted focus:outline-none focus:border-accent" />
        <button type="submit" disabled={loading || q.trim().length < 4}
          className="font-mono text-xs uppercase tracking-[0.14em] px-4 py-2 border border-accent text-accent hover:bg-accent hover:text-card disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-accent transition-colors shrink-0">
          {loading ? "Analysiere…" : "Analysieren"}
        </button>
      </form>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {EXAMPLES.map((ex) => (
          <button key={ex} onClick={() => { setQ(ex); run(ex); }} disabled={loading}
            className="font-mono text-[10px] text-muted border border-border px-2 py-1 hover:text-accent hover:border-accent/50 disabled:opacity-40">{ex}</button>
        ))}
      </div>

      {loading && <p className="mt-5 font-mono text-xs text-muted animate-pulse">Phrase wird eingebettet und auf Patentklassen aufgelöst… (~10–30s)</p>}
      {err && <p className="mt-5 font-mono text-xs text-red-400">⚠ {err}</p>}

      {res && !loading && res.off_topic && (
        <div className="mt-6 border border-border bg-card/40 p-5">
          <p className="font-sans text-base text-paper">Das sieht nicht nach einer Technologie aus.</p>
          <p className="font-sans text-sm text-text mt-2">Beschreibe einen Prozess, ein Material oder eine Methode (nächste Klasse {res.nearest_dist} zu weit entfernt).</p>
        </div>
      )}

      {res && !loading && !res.off_topic && (
        <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,260px)_1fr]">
          {/* left: user-selectable CPC classes */}
          <div className="min-w-0">
            <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted mb-2">
              Patentklassen — deine Auswahl ({sel.size})
            </div>
            <div className="space-y-1 max-h-[320px] overflow-y-auto pr-1">
              {res.candidates?.map((c) => {
                const on = sel.has(c.symbol);
                return (
                  <button key={c.symbol} onClick={() => toggle(c.symbol)} disabled={rerun}
                    className={`w-full text-left flex items-start gap-2 px-2 py-1.5 border transition-colors ${on ? "border-accent/50 bg-accent/10" : "border-border hover:border-border/80"} disabled:opacity-60`}>
                    <span className={`mt-0.5 font-mono text-[11px] shrink-0 ${on ? "text-accent" : "text-muted"}`}>{on ? "☑" : "☐"}</span>
                    <span className="min-w-0 flex-1">
                      <span className="font-mono text-[11px] text-paper break-words">{c.symbol}</span>
                      <span className="block font-sans text-[11px] text-muted leading-tight break-words">{cpcLabel(c.title)}</span>
                    </span>
                    <span className="font-mono text-[10px] text-muted shrink-0 tabular-nums">{c.n.toLocaleString("de")}</span>
                  </button>
                );
              })}
            </div>
            <p className="mt-2 font-mono text-[10px] text-muted">
              {selN.toLocaleString("de")} Patente gewählt · Häkchen ändern rechnet live neu
            </p>
          </div>

          {/* right: trajectory + lead-time */}
          <div className="min-w-0">
            {res.verdict && <p className="font-sans text-sm text-paper mb-3 leading-snug">{res.verdict}</p>}

            <div className="flex flex-wrap items-baseline gap-3 mb-2">
              <span className="font-mono text-[10px] uppercase tracking-[0.14em] px-2 py-0.5 border" style={{ color: DIR_COLOR[dir], borderColor: DIR_COLOR[dir] + "80" }}>
                {traj?.direction_de || DIR_LABEL[dir] || "—"}
              </span>
              <span className="font-sans text-sm text-text">
                {traj?.calibrated
                  ? <>typischer TIR <span className="text-paper">~{traj.K_median}%/Jahr</span></>
                  : <span className="text-muted">außerhalb des kalibrierten Bereichs</span>}
              </span>
              {traj?.earliest_year && (
                <span className="font-mono text-[10px] text-muted">früheste Zitation {traj.earliest_year}</span>
              )}
              {rerun && <span className="font-mono text-[10px] text-muted animate-pulse">aktualisiere…</span>}
            </div>

            {traj?.points && traj.points.length >= 2
              ? <Chart points={traj.points} />
              : <p className="font-sans text-sm text-muted border-l-2 border-border pl-3">Zu wenig Patentdaten in dieser Auswahl für eine Trajektorie — wähle mehr Klassen links.</p>}

            <p className="font-sans text-[11px] text-muted mt-2 max-w-3xl">
              Die Kurve beginnt am frühesten dichten Jahr dieser Technologie. Schattiert
              links = frühe Zitationen spärlich (vor ~1976), rechts = jüngste Jahre noch
              unreif. Band = Kalibrierungs-Unsicherheit (~68 %). „Typischer TIR" = Median
              über die gemessene Historie (robust gegen den Immaturitäts-Ausschlag der
              jüngsten Jahre); die Richtung zeigt den aktuellen Trend.
            </p>

            {/* cross-tier lead time */}
            {lead && (
              <div className="mt-5 border-t border-border pt-4">
                <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted mb-3">Innovationskette — wann tauchte es je Tier auf</div>
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
                    ? "Etablierte Technologie — Forschung und Patente existierten schon vor unserem Datenfenster (1990). Ein Research-→-Markt-Vorlauf ist hier nicht messbar."
                    : <>
                        {lead.lead_science_market ? <>Forschung lief ~<span className="text-text">{lead.lead_science_market} Jahre</span> vor dem Markt. </> : null}
                        {lead.lead_patent_market ? <>Patente ~<span className="text-text">{lead.lead_patent_market} Jahre</span> vor dem Markt. </> : null}
                        {lead.concurrent ? "Forschung und Markt bewegen sich zeitgleich." : null}
                        {!lead.lead_science_market && !lead.lead_patent_market && !lead.concurrent ? "Kein klarer Tier-Vorlauf messbar." : null}
                      </>}
                </p>
              </div>
            )}

            {/* most-cited (landmark) patents in the selection */}
            {res.top_patents && res.top_patents.length > 0 && (
              <div className="mt-5 border-t border-border pt-4">
                <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted mb-3">
                  Meistzitierte Patente in dieser Auswahl
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
                <p className="mt-2 font-mono text-[10px] text-muted">Vorwärts-Zitationen im Korpus · Klick öffnet Espacenet</p>
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
