import type { TierName, TierPoint } from "@/lib/foresight";

/**
 * Four-tier lead-time curves (#3/#9): research → patents → funding → market,
 * each as a Share-of-Voice line over time (SoV = the tech's share of that
 * tier's yearly volume, so tiers of different corpus depth are comparable).
 * Server-rendered SVG; every line is direct-labeled (identity never by colour
 * alone), and a values table backs it for accessibility.
 *
 * Palette validated on the #0a0c0a surface (dataviz skill): CVD ΔE 14 worst
 * adjacent, mirrors the site vertical hues.
 */

// Research + Market define the lead; patents/funding are context — so the two
// lead tiers get full weight and the other two are recessive (identity still
// direct-labeled, so this is emphasis, not hiding).
const TIER_META: { key: TierName; label: string; color: string; lead: boolean }[] = [
  { key: "science", label: "Research", color: "#22d3ee", lead: true },
  { key: "patent", label: "Patents", color: "#a78bfa", lead: false },
  { key: "funding", label: "Funding", color: "#fb923c", lead: false },
  { key: "market", label: "Market", color: "#bde63a", lead: true },
];

/** Centered 3-point moving average — reveals each tier's S-curve trend through
 *  the small-count noise without shifting the timing (the lead-time signal). */
function smooth(pts: TierPoint[]): TierPoint[] {
  if (pts.length < 3) return pts;
  return pts.map((p, i) => {
    const a = pts[Math.max(0, i - 1)].sov;
    const b = pts[i].sov;
    const c = pts[Math.min(pts.length - 1, i + 1)].sov;
    return { ...p, sov: (a + b + c) / 3 };
  });
}

const W = 720;
const H = 300;
const PAD = { top: 18, right: 96, bottom: 28, left: 16 };

export default function TierCurveChart({
  tiers,
  scienceTakeoff,
  marketTakeoff,
}: {
  tiers: Record<TierName, TierPoint[]>;
  scienceTakeoff?: number | null;
  marketTakeoff?: number | null;
}) {
  const sm: Record<TierName, TierPoint[]> = {
    science: smooth(tiers.science),
    patent: smooth(tiers.patent),
    funding: smooth(tiers.funding),
    market: smooth(tiers.market),
  };
  const all = TIER_META.flatMap((t) => sm[t.key]);
  if (all.length === 0) {
    return (
      <div className="border border-border bg-card/40 p-8 text-center font-sans text-sm text-muted">
        No cross-tier signal for this technology yet.
      </div>
    );
  }
  const years = all.map((p) => p.year);
  const y0 = Math.min(...years);
  const y1 = Math.max(...years);

  // Index EACH tier to its own peak (0..1). The tiers have different baseline
  // SoV levels (the market corpus is more concentrated than the research one),
  // so plotting raw SoV lets the highest-level tier dominate and hides the
  // TIMING — which is the whole point. Per-tier indexing makes every line share
  // the 0..1 range, so the chart shows purely WHEN each tier rose. (dataviz:
  // different-scale measures → index to a common base.)
  const peak: Record<TierName, number> = {
    science: Math.max(...sm.science.map((p) => p.sov), 1e-9),
    patent: Math.max(...sm.patent.map((p) => p.sov), 1e-9),
    funding: Math.max(...sm.funding.map((p) => p.sov), 1e-9),
    market: Math.max(...sm.market.map((p) => p.sov), 1e-9),
  };

  const px = (yr: number) =>
    PAD.left + ((yr - y0) / Math.max(y1 - y0, 1)) * (W - PAD.left - PAD.right);
  const py = (frac: number) =>
    H - PAD.bottom - frac * (H - PAD.top - PAD.bottom);

  // gridlines: ~4 year ticks
  const step = Math.max(1, Math.round((y1 - y0) / 5));
  const ticks: number[] = [];
  for (let yy = y0; yy <= y1; yy += step) ticks.push(yy);

  // smoothed end-label y-positions so labels don't overlap
  const ends = TIER_META.map((t) => {
    const pts = sm[t.key];
    const last = pts[pts.length - 1];
    return { ...t, y: last ? py(last.sov / peak[t.key]) : H - PAD.bottom, has: pts.length > 0 };
  })
    .filter((e) => e.has)
    .sort((a, b) => a.y - b.y);
  for (let i = 1; i < ends.length; i++) {
    if (ends[i].y - ends[i - 1].y < 14) ends[i].y = ends[i - 1].y + 14;
  }

  return (
    <figure className="m-0">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label="Share-of-voice curves for research, patents, funding and market over time"
        className="w-full h-auto"
      >
        {/* lead-time band: shade the gap between research and market takeoff so
            the whole point of the chart is visible, not inferred */}
        {scienceTakeoff != null &&
          marketTakeoff != null &&
          marketTakeoff > scienceTakeoff &&
          scienceTakeoff >= y0 &&
          marketTakeoff <= y1 && (
            <g>
              <rect
                x={px(scienceTakeoff)}
                y={PAD.top}
                width={px(marketTakeoff) - px(scienceTakeoff)}
                height={H - PAD.top - PAD.bottom}
                fill="#d4ff3a"
                opacity={0.06}
              />
              {[
                { yr: scienceTakeoff, c: "#22d3ee", t: "research takes off" },
                { yr: marketTakeoff, c: "#bde63a", t: "market takes off" },
              ].map((m) => (
                <line
                  key={m.t}
                  x1={px(m.yr)}
                  x2={px(m.yr)}
                  y1={PAD.top}
                  y2={H - PAD.bottom}
                  stroke={m.c}
                  strokeWidth={1.5}
                  strokeDasharray="3 3"
                  opacity={0.8}
                />
              ))}
              <text
                x={(px(scienceTakeoff) + px(marketTakeoff)) / 2}
                y={PAD.top + 11}
                textAnchor="middle"
                fill="#d4ff3a"
                style={{ font: "600 10px ui-sans-serif, system-ui" }}
              >
                ~{marketTakeoff - scienceTakeoff}y lead
              </text>
            </g>
          )}

        {/* gridlines + year labels */}
        {ticks.map((yy) => (
          <g key={yy}>
            <line
              x1={px(yy)}
              x2={px(yy)}
              y1={PAD.top}
              y2={H - PAD.bottom}
              stroke="#2a2d25"
              strokeWidth={1}
            />
            <text
              x={px(yy)}
              y={H - PAD.bottom + 16}
              textAnchor="middle"
              className="fill-muted"
              style={{ font: "10px ui-monospace, monospace" }}
            >
              {yy}
            </text>
          </g>
        ))}

        {/* tier lines */}
        {TIER_META.map((t) => {
          const pts = sm[t.key];
          if (pts.length === 0) return null;
          const d = pts.map((p, i) => `${i ? "L" : "M"}${px(p.year).toFixed(1)},${py(p.sov / peak[t.key]).toFixed(1)}`).join(" ");
          return (
            <path
              key={t.key}
              d={d}
              fill="none"
              stroke={t.color}
              strokeWidth={t.lead ? 2.5 : 1.5}
              strokeOpacity={t.lead ? 1 : 0.45}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          );
        })}

        {/* direct end labels (identity, never colour-alone) */}
        {ends.map((e) => (
          <text
            key={e.key}
            x={W - PAD.right + 8}
            y={e.y + 3}
            style={{ font: `${e.lead ? 600 : 400} 11px ui-sans-serif, system-ui` }}
            fill={e.color}
            fillOpacity={e.lead ? 1 : 0.6}
          >
            {e.label}
          </text>
        ))}
      </svg>

      <figcaption className="sr-only">
        <table>
          <thead>
            <tr>
              <th>Tier</th>
              <th>Peak SoV year</th>
            </tr>
          </thead>
          <tbody>
            {TIER_META.map((t) => {
              const pts = tiers[t.key];
              const peak = pts.reduce<TierPoint | null>(
                (m, p) => (!m || p.sov > m.sov ? p : m),
                null
              );
              return (
                <tr key={t.key}>
                  <td>{t.label}</td>
                  <td>{peak ? peak.year : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </figcaption>
    </figure>
  );
}
