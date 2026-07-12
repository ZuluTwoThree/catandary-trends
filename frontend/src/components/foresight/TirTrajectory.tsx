"use client";

import { useState } from "react";

/**
 * On-demand TIR trajectory (#36/#42/#43). A free-text technology is resolved to
 * the nearest fine CPC codes and its year-by-year improvement rate K(t) is drawn
 * on a time axis. Honest by construction: the last ~7 years (immature forward
 * citations) are greyed, the absolute value is hidden outside the calibrated
 * range (only the direction shown), and a too-thin domain says so.
 */

interface Point { year: number; K: number; K_lo?: number; K_hi?: number; n: number; complete: boolean }
interface Code { symbol: string; title: string; n_patents: number; dist: number }
interface Traj {
  query?: string;
  codes?: Code[];
  points?: Point[];
  direction?: string;
  direction_de?: string;
  rel_change?: number | null;
  K_latest?: number | null;
  K_median?: number | null;
  calibrated?: boolean | null;
  n_total?: number;
  reason?: string | null;
  error?: string;
}

const DIR_LABEL: Record<string, string> = {
  accelerating: "beschleunigt",
  steady: "stetig",
  maturing: "reift",
  decelerating: "verlangsamt sich",
  uncertain: "Richtung unsicher",
  insufficient_data: "zu wenig Daten",
};
const DIR_COLOR: Record<string, string> = {
  accelerating: "#bde63a",
  steady: "#8a8d82",
  maturing: "#fb923c",
  decelerating: "#fb7185",
  uncertain: "#8a8d82",
  insufficient_data: "#8a8d82",
};

function Chart({ points }: { points: Point[] }) {
  const W = 720, H = 240, PAD = { t: 22, r: 16, b: 26, l: 40 };
  if (points.length < 2) return null;
  const xs = points.map((p) => p.year);
  const ys = points.map((p) => p.K);
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  // round the axis top to a nice number so ticks read cleanly (no 30.8).
  // scale to the top of the uncertainty band so the envelope never clips.
  const rawMax = Math.max(...points.map((p) => p.K_hi ?? p.K), 1);
  const step = rawMax > 40 ? 20 : rawMax > 20 ? 10 : rawMax > 8 ? 5 : 2;
  const y1 = Math.ceil((rawMax * 1.08) / step) * step;
  const px = (yr: number) => PAD.l + ((yr - x0) / Math.max(x1 - x0, 1)) * (W - PAD.l - PAD.r);
  const py = (k: number) => H - PAD.b - (k / y1) * (H - PAD.t - PAD.b);

  const complete = points.filter((p) => p.complete);
  const lastComplete = complete.length ? complete[complete.length - 1].year : x0;
  const seg = (pts: Point[]) =>
    pts.map((p, i) => `${i ? "L" : "M"}${px(p.year).toFixed(1)},${py(p.K).toFixed(1)}`).join(" ");
  // filled envelope between K_hi (forward) and K_lo (back) — the calibration band
  const band = (pts: Point[]) => {
    const withCI = pts.filter((p) => p.K_hi != null && p.K_lo != null);
    if (withCI.length < 2) return "";
    const up = withCI.map((p, i) => `${i ? "L" : "M"}${px(p.year).toFixed(1)},${py(p.K_hi as number).toFixed(1)}`).join(" ");
    const dn = [...withCI].reverse().map((p) => `L${px(p.year).toFixed(1)},${py(p.K_lo as number).toFixed(1)}`).join(" ");
    return `${up} ${dn} Z`;
  };
  // solid = complete; dashed/grey = the truncated tail (join at lastComplete)
  const tail = points.filter((p) => p.year >= lastComplete);

  const yticks: number[] = [];
  for (let v = 0; v <= y1 + 0.001; v += step) yticks.push(v);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img"
         aria-label="TIR trajectory over time">
      {/* y-axis unit, above the plot so it never collides with a tick */}
      <text x={PAD.l} y={PAD.t - 8} textAnchor="middle"
            style={{ font: "8px ui-monospace, monospace" }} fill="#8a8d82">%/yr</text>
      {yticks.map((v) => (
        <g key={v}>
          <line x1={PAD.l} x2={W - PAD.r} y1={py(v)} y2={py(v)} stroke="#2a2d25" strokeWidth={1} />
          <text x={PAD.l - 6} y={py(v) + 3} textAnchor="end"
                style={{ font: "9px ui-monospace, monospace" }} fill="#8a8d82">{v}</text>
        </g>
      ))}
      {[x0, Math.round((x0 + lastComplete) / 2), lastComplete, x1].map((yr) => (
        <text key={yr} x={px(yr)} y={H - PAD.b + 15} textAnchor="middle"
              style={{ font: "9px ui-monospace, monospace" }} fill="#8a8d82">{yr}</text>
      ))}
      {/* truncation shading */}
      {x1 > lastComplete && (
        <>
          <rect x={px(lastComplete)} y={PAD.t} width={px(x1) - px(lastComplete)}
                height={H - PAD.t - PAD.b} fill="#8a8d82" opacity={0.06} />
          <text x={(px(lastComplete) + px(x1)) / 2} y={PAD.t + 10} textAnchor="middle"
                style={{ font: "8px ui-sans-serif, system-ui" }} fill="#8a8d82">
            Zitationen noch unreif
          </text>
        </>
      )}
      {/* calibration uncertainty band (~68%) under the complete line */}
      {band(complete) && (
        <path d={band(complete)} fill="#d4ff3a" opacity={0.1} stroke="none" />
      )}
      <path d={seg(complete)} fill="none" stroke="#d4ff3a" strokeWidth={2.5}
            strokeLinejoin="round" strokeLinecap="round" />
      {tail.length >= 2 && (
        <path d={seg(tail)} fill="none" stroke="#8a8d82" strokeWidth={1.5}
              strokeDasharray="3 3" strokeLinejoin="round" strokeLinecap="round" />
      )}
    </svg>
  );
}

export default function TirTrajectory() {
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);
  const [res, setRes] = useState<Traj | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function run(e?: React.FormEvent) {
    e?.preventDefault();
    if (q.trim().length < 4) return;
    setLoading(true); setErr(null); setRes(null);
    try {
      const r = await fetch(`/api/foresight/trajectory?q=${encodeURIComponent(q.trim())}`);
      const data: Traj = await r.json();
      if (data.error) setErr(data.error);
      else setRes(data);
    } catch {
      setErr("Anfrage fehlgeschlagen");
    } finally {
      setLoading(false);
    }
  }

  const dir = res?.direction || "";
  return (
    <div className="border border-border bg-card/40 p-5">
      <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-2">
        —— TIR-Trajektorie · beschleunigt oder reift eine Technologie?
      </div>
      <p className="font-sans text-sm text-text leading-relaxed mb-4 max-w-3xl">
        Beschreibe eine Technologie in eigenen Worten. Wir lösen sie auf die feinen
        Patentklassen auf und zeigen ihre Verbesserungsrate Jahr für Jahr — aus dem
        Patent-Zitationsgraphen (1990–2026), unabhängig von der Marktabdeckung.
      </p>
      <form onSubmit={run} className="flex gap-2 mb-4">
        <input
          value={q} onChange={(e) => setQ(e.target.value)}
          placeholder="z. B. protein recovery by electrodialysis"
          className="flex-1 bg-ink border border-border px-3 py-2 font-sans text-sm text-paper
                     placeholder:text-muted focus:border-accent outline-none"
        />
        <button type="submit" disabled={loading || q.trim().length < 4}
          className="font-mono text-[11px] uppercase tracking-[0.14em] text-accent border
                     border-accent bg-accent/5 hover:bg-accent/15 px-4 disabled:opacity-40">
          {loading ? "…" : "Zeigen"}
        </button>
      </form>

      {err && <p className="font-sans text-sm text-red-400">{err}</p>}

      {res && (
        <div>
          {/* resolved fine-code domain */}
          {res.codes && res.codes.length > 0 && (
            <div className="mb-3">
              <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted mb-1">
                Aufgelöste Technologie-Domäne (feine CPC-Codes)
              </div>
              <div className="flex flex-wrap gap-x-4 gap-y-1">
                {res.codes.slice(0, 6).map((c) => (
                  <span key={c.symbol} className="font-sans text-xs text-text">
                    <span className="font-mono text-accent">{c.symbol}</span>{" "}
                    <span className="text-muted">{(c.title || "").slice(0, 40)}</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          {dir === "insufficient_data" ? (
            <p className="font-sans text-sm text-muted border-l-2 border-border pl-3">
              Zu wenig belastbare Patentdaten für eine Trajektorie ({res.n_total?.toLocaleString("de")} Patente
              im Korpus). Ehrlich: hier sagen wir lieber nichts, als eine Zahl zu erfinden.
            </p>
          ) : (
            <>
              <div className="flex flex-wrap items-baseline gap-3 mb-2">
                <span className="font-mono text-[10px] uppercase tracking-[0.14em] px-2 py-0.5 border"
                      style={{ color: DIR_COLOR[dir], borderColor: DIR_COLOR[dir] + "80" }}>
                  {res.direction_de || DIR_LABEL[dir]}
                </span>
                <span className="font-sans text-sm text-text">
                  {res.calibrated
                    ? <>aktueller TIR <span className="text-paper">~{res.K_latest}%/Jahr</span></>
                    : <span className="text-muted">sehr schnell — außerhalb des kalibrierten Bereichs, nur Richtung</span>}
                </span>
                <span className="font-mono text-[10px] text-muted">
                  {res.n_total?.toLocaleString("de")} Patente
                </span>
              </div>
              {res.points && <Chart points={res.points} />}
              {dir === "uncertain" ? (
                <p className="font-sans text-[11px] text-muted mt-2 max-w-3xl border-l-2 border-border pl-3">
                  Die Trajektorie ist gemessen, aber die <span className="text-text">Trendrichtung
                  halten wir zurück</span>: in dieser Technologie sind zu wenige Patente pro Jahr,
                  um beschleunigt/reift verlässlich zu unterscheiden. Ehrlich: lieber keine Richtung
                  als eine geratene. (Mehr Patentabdeckung würde das auflösen.)
                </p>
              ) : (
                <p className="font-sans text-[11px] text-muted mt-2 max-w-3xl">
                  Durchgezogen = verlässlich gemessen; ausgegraut = letzte Jahre (Vorwärts-Zitationen
                  noch unreif, ~7-Jahre-Horizont). Das schattierte Band ist die Unsicherheit der
                  Kalibrierung (~68 %) — der TIR ist eine Schätzung mit Spanne, keine Punktzahl.
                  Richtung aus dem jüngsten verlässlichen Fenster.
                </p>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
