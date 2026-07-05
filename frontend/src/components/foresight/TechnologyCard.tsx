import { espacenetUrl, TechInsight, TierName } from "@/lib/technology";

/**
 * One technology axis: the four-tier lead-time chain as labeled sparkline
 * rows (shared x range, per-row normalized y — magnitudes differ by 10^4),
 * a plain-language lead statement, and the patent-graph evidence.
 *
 * Chart rules: thin bar marks, one hue (identity lives in the row label, not
 * color), text in text tokens, native <title> tooltips per year.
 */

const X0 = 1990;
const X1 = 2026;
const YEARS = Array.from({ length: X1 - X0 + 1 }, (_, i) => X0 + i);

const TIER_LABEL: Record<TierName, string> = {
  science: "Research",
  patent: "Patents",
  funding: "Funding",
  market: "Market",
};

const TIER_ORDER: TierName[] = ["science", "patent", "funding", "market"];

function Sparkline({ series, takeoff }: { series: Record<string, number>; takeoff: number | null }) {
  const w = 222;
  const h = 22;
  const bw = w / YEARS.length;
  const max = Math.max(1, ...Object.values(series));
  return (
    <svg
      width={w}
      height={h}
      viewBox={`0 0 ${w} ${h}`}
      className="shrink-0"
      role="img"
      aria-label={`Signals per year, ${X0}–${X1}`}
    >
      {YEARS.map((y, i) => {
        const n = series[String(y)] ?? 0;
        if (n === 0) return null;
        const bh = Math.max(1.5, (n / max) * (h - 2));
        return (
          <rect
            key={y}
            x={i * bw + 0.5}
            y={h - bh}
            width={Math.max(1.5, bw - 1.2)}
            height={bh}
            rx={0.75}
            className="fill-accent/70"
          >
            <title>{`${y}: ${n.toLocaleString("en-US")} signals`}</title>
          </rect>
        );
      })}
      {takeoff && takeoff >= X0 && (
        <line
          x1={(takeoff - X0) * bw + bw / 2}
          y1={0}
          x2={(takeoff - X0) * bw + bw / 2}
          y2={h}
          className="stroke-paper/50"
          strokeWidth={1}
          strokeDasharray="2 2"
        >
          <title>{`Takeoff ${takeoff}`}</title>
        </line>
      )}
    </svg>
  );
}

function leadSentence(t: TechInsight): string {
  const sci = t.payload.lead_years_science_vs_market;
  const pat = t.payload.lead_years_patent_vs_market;
  if (sci && sci >= 2) {
    return `Research ran ~${sci} years ahead of market coverage.`;
  }
  if (pat && pat >= 2) {
    return `Patent activity ran ~${pat} years ahead of market coverage.`;
  }
  return "Signals move closely across the maturity chain.";
}

export default function TechnologyCard({ tech }: { tech: TechInsight }) {
  const { payload } = tech;
  const hub = payload.patent_dynamics.hub;
  const cycle = payload.patent_dynamics.cycle_time_years;
  const partners = (payload.convergence ?? []).slice(0, 3);

  return (
    <article className="border border-border bg-card/40 p-5 flex flex-col gap-4">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-xl text-paper leading-snug">{tech.name}</h2>
          <p className="font-sans text-sm text-text mt-1">{leadSentence(tech)}</p>
        </div>
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted border border-border px-2 py-1 shrink-0">
          {tech.vertical} · {tech.symbol}
        </span>
      </header>

      <div className="flex flex-col gap-1.5">
        {TIER_ORDER.map((tier) => {
          const lead = payload.lead_time[tier];
          if (!lead) return null;
          return (
            <div key={tier} className="flex items-center gap-3">
              <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted w-16 shrink-0">
                {TIER_LABEL[tier]}
              </span>
              <Sparkline series={lead.series} takeoff={lead.takeoff} />
              <span className="font-mono text-[11px] text-text tabular-nums whitespace-nowrap">
                {lead.n > 0
                  ? `${lead.n.toLocaleString("en-US")}${lead.takeoff ? ` · from ${lead.takeoff}` : ""}`
                  : "—"}
              </span>
            </div>
          );
        })}
        <div className="flex items-center gap-3">
          <span className="w-16 shrink-0" />
          <div className="flex justify-between font-mono text-[9px] text-muted" style={{ width: 222 }}>
            <span>{X0}</span>
            <span>{X1}</span>
          </div>
        </div>
      </div>

      <footer className="flex flex-col gap-2 border-t border-border pt-3">
        <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-[11px] text-text tabular-nums">
          <span>
            {payload.lead_time.patent.n.toLocaleString("en-US")}{" "}
            <span className="text-muted">patents</span>
          </span>
          {cycle !== undefined && (
            <span>
              {cycle} y <span className="text-muted">innovation cycle</span>
            </span>
          )}
          {hub && (
            <a
              href={espacenetUrl(hub.pub)}
              target="_blank"
              rel="noopener noreferrer"
              className="text-accent hover:underline"
              title={hub.title || hub.pub}
            >
              key patent · {hub.cites.toLocaleString("en-US")} citations ↗
            </a>
          )}
        </div>
        {partners.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
              converges with
            </span>
            {partners.map((p) => (
              <span
                key={p.cpc}
                className="font-mono text-[10px] text-text border border-border px-1.5 py-0.5"
                title={p.title}
              >
                {p.title ? p.title.toLowerCase().slice(0, 34) : p.cpc}
              </span>
            ))}
          </div>
        )}
      </footer>
    </article>
  );
}
