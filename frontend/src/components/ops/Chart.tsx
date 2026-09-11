import {
  fmtTime, jobColor, niceMax, seriesPath, timeTicks, xOf, type Band, type SeriesPoint,
} from "@/lib/ops";

export interface ChartSeries {
  label: string;
  points: SeriesPoint[];
  color?: string;
}

interface Props {
  title: string;
  unit: string;
  series: ChartSeries[];
  from: Date;
  to: Date;
  bands?: Band[];
  /** Fixed axis top (e.g. total VRAM); otherwise a nice max over the data. */
  yMax?: number;
  /** Axis bottom; default 0. With `yAuto` both bounds hug the data (DB size). */
  yMin?: number;
  yAuto?: boolean;
  format?: (v: number) => string;
  /** Horizontal guide (threshold) in data units. */
  guide?: number;
  current?: string;
}

const W = 640;
const H = 140;
const BOX = { x: 4, y: 8, w: W - 56, h: H - 30 };

/**
 * Server-rendered SVG line chart: no client JS, no chart library. Runs of the
 * cron jobs appear as translucent bands behind the line so "the disk was busy
 * at 04:30" reads as "the cycle was running".
 */
export default function Chart({
  title, unit, series, from, to, bands = [], yMax, yMin = 0, yAuto = false, format, guide, current,
}: Props) {
  const values = series.flatMap((s) => s.points.map((p) => p.v)).filter((v): v is number => v != null);
  let top = yMax ?? niceMax(Math.max(0, ...values) || 1);
  let bottom = yMin;
  if (yAuto && values.length) {
    const lo = Math.min(...values);
    const hi = Math.max(...values);
    const pad = Math.max((hi - lo) * 0.15, hi * 0.002, 1);
    bottom = lo - pad;
    top = hi + pad;
  }
  const fmt = format ?? ((v: number) => (Number.isInteger(v) ? String(v) : v.toFixed(1)));
  const yOf = (v: number) => BOX.y + BOX.h - ((Math.min(Math.max(v, bottom), top) - bottom) / (top - bottom)) * BOX.h;
  const ticks = timeTicks(from, to);
  const gridVals = [bottom, bottom + (top - bottom) / 2, top];

  return (
    <figure className="border border-border p-3 bg-card">
      <figcaption className="flex items-baseline justify-between gap-3 mb-1">
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
          {title} <span className="text-border-strong">· {unit}</span>
        </span>
        {current && <span className="font-mono text-[11px] text-paper">{current}</span>}
      </figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto block" role="img" aria-label={title}>
        {bands.map((b, i) => {
          const x0 = xOf(b.start, from, to, BOX);
          const x1 = xOf(b.end ?? to, from, to, BOX);
          if (x1 - x0 < 0.5) return null;
          return (
            <rect key={i} x={x0} y={BOX.y} width={Math.max(1, x1 - x0)} height={BOX.h}
                  fill={jobColor(b.job)} opacity={b.end ? 0.14 : 0.24}>
              <title>{`${b.job} · ${fmtTime(b.start, true)}${b.end ? ` – ${fmtTime(b.end)}` : " – running"}`}</title>
            </rect>
          );
        })}
        {gridVals.map((g, i) => (
          <g key={i}>
            <line x1={BOX.x} x2={BOX.x + BOX.w} y1={yOf(g)} y2={yOf(g)} stroke="currentColor"
                  className="text-border" strokeWidth={0.5} />
            <text x={BOX.x + BOX.w + 4} y={yOf(g) + 3} fontSize={9} fontFamily="ui-monospace, monospace"
                  fill="currentColor" className="text-muted">{fmt(g)}</text>
          </g>
        ))}
        {guide != null && guide > bottom && guide < top && (
          <line x1={BOX.x} x2={BOX.x + BOX.w} y1={yOf(guide)} y2={yOf(guide)} stroke="#ff6b3a"
                strokeWidth={0.8} strokeDasharray="3 3" />
        )}
        {ticks.map((t, i) => {
          const x = xOf(t, from, to, BOX);
          return (
            <g key={i}>
              <line x1={x} x2={x} y1={BOX.y} y2={BOX.y + BOX.h} stroke="currentColor" className="text-border"
                    strokeWidth={0.5} />
              <text x={x} y={H - 4} fontSize={9} textAnchor="middle" fontFamily="ui-monospace, monospace"
                    fill="currentColor" className="text-muted">
                {ticks.length > 6 ? fmtTime(t, true).slice(0, 6) : fmtTime(t)}
              </text>
            </g>
          );
        })}
        {series.map((s, i) => (
          <path key={i} d={seriesPath(s.points, from, to, top, BOX, bottom)} fill="none"
                stroke={s.color ?? "#d4ff3a"} strokeWidth={1.4} strokeLinejoin="round" />
        ))}
      </svg>
      {series.length > 1 && (
        <div className="mt-1 flex flex-wrap gap-x-4 font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
          {series.map((s) => (
            <span key={s.label} className="inline-flex items-center gap-1">
              <span className="inline-block w-3 h-[2px]" style={{ background: s.color ?? "#d4ff3a" }} />
              {s.label}
            </span>
          ))}
        </div>
      )}
    </figure>
  );
}
