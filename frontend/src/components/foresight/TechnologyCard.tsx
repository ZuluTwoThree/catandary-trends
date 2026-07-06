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

function Sparkline({ shareSeries, label }: { shareSeries: Record<string, number>; label: string }) {
  const w = 222;
  const h = 22;
  const bw = w / YEARS.length;
  const max = Math.max(1, ...Object.values(shareSeries));
  return (
    <svg
      width="100%"
      height={h}
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="none"
      className="block w-full"
      role="img"
      aria-label={`Share of tier per year, ${X0}–${X1}`}
    >
      {YEARS.map((y, i) => {
        const bp = shareSeries[String(y)] ?? 0;
        if (bp === 0) return null;
        const bh = Math.max(1.5, (bp / max) * (h - 2));
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
            <title>{`${y}: ${(bp / 100).toFixed(2)}% of ${label.toLowerCase()} activity`}</title>
          </rect>
        );
      })}
    </svg>
  );
}

/**
 * Card headline sentence. The lead-time claim (the product's core promise) is
 * shown ONLY where it is genuinely measured: market takeoff must be clear of
 * the market corpus floor (≥2003). Science takeoff sits at the 1990 window
 * floor for every broad domain (research predates our window), so the lead is
 * a LOWER BOUND and always phrased "N+ years". Everything else falls back to
 * the dynamics statement (innovation cycle + patent center of gravity).
 */
function leadSentence(t: TechInsight): string {
  const sci = t.payload.lead_time.science?.takeoff;
  const mkt = t.payload.lead_time.market?.takeoff;
  const lead = t.payload.lead_years_science_vs_market;
  if (sci && mkt && lead && mkt >= 2003 && lead >= 5) {
    return `In our data, research ran ${lead}+ years ahead of market coverage.`;
  }
  const cycle = t.payload.patent_dynamics.cycle_time_years;
  const med = t.payload.lead_time.patent?.median;
  const parts: string[] = [];
  if (cycle !== undefined) {
    if (cycle <= 3) parts.push(`Fast-moving field — ideas turn into new patents in ~${cycle} years`);
    else if (cycle <= 6) parts.push(`Steady field — ~${cycle} years from idea to follow-on patent`);
    else parts.push(`Long-cycle field — ~${cycle} years between patent generations`);
  }
  if (med) {
    parts.push(med >= 2021 ? `activity centers on ${med}` : `activity centered around ${med}`);
  }
  return parts.length ? parts.join(", ") + "." : "Evidence across the full maturity chain.";
}

/** Convergence chips carry CPC legalese titles — keep the first clause and let
 *  CSS truncate handle the rest (full title in the tooltip). */
function shortPartnerLabel(p: { cpc: string; title: string }): string {
  if (!p.title) return p.cpc;
  return p.title.split(";")[0].toLowerCase();
}

export default function TechnologyCard({ tech }: { tech: TechInsight }) {
  const { payload } = tech;
  const cycle = payload.patent_dynamics.cycle_time_years;
  const tir = payload.patent_dynamics.tir_pct;
  const topPatents = payload.patent_dynamics.top_patents ?? [];
  const partners = (payload.convergence ?? []).slice(0, 3);

  return (
    <article className="border border-border bg-card/40 p-4 sm:p-5 flex flex-col gap-4 overflow-hidden">
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="font-display text-lg sm:text-xl text-paper leading-snug break-words">
            {tech.name}
          </h2>
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
          const hasShare = Object.keys(lead.share_series ?? {}).length > 0;
          return (
            <div key={tier} className="flex items-center gap-2 sm:gap-3">
              <span className="font-mono text-[9px] sm:text-[10px] uppercase tracking-[0.1em] text-muted w-14 sm:w-16 shrink-0">
                {TIER_LABEL[tier]}
              </span>
              <div className="flex-1 min-w-0">
                {hasShare ? (
                  <Sparkline shareSeries={lead.share_series} label={TIER_LABEL[tier]} />
                ) : (
                  <span className="font-mono text-[9px] text-muted italic flex items-center h-[22px]">
                    coverage building…
                  </span>
                )}
              </div>
              <span className="font-mono text-[10px] sm:text-[11px] text-text tabular-nums shrink-0 w-16 text-right">
                {lead.n > 0 ? lead.n.toLocaleString("en-US") : "—"}
              </span>
            </div>
          );
        })}
        <div className="flex items-center gap-2 sm:gap-3">
          <span className="w-14 sm:w-16 shrink-0" />
          <div className="flex-1 min-w-0 flex justify-between font-mono text-[9px] text-muted">
            <span>{X0}</span>
            <span>{X1}</span>
          </div>
          <span className="w-16 shrink-0" />
        </div>
        <p className="font-mono text-[9px] text-muted">
          share of each tier&apos;s activity per year · count at right
        </p>
      </div>

      <footer className="flex flex-col gap-2 border-t border-border pt-3">
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 font-mono text-[11px] text-text tabular-nums">
          {tir !== undefined && (
            <span title="Predicted Technology Improvement Rate — immediacy × importance from the citation graph, calibrated on published Benson–Magee domain rates">
              <span className="font-display text-lg text-paper">≈{tir}%</span>
              <span className="text-muted">/yr improvement (predicted)</span>
            </span>
          )}
          <span>
            {payload.lead_time.patent.n.toLocaleString("en-US")}{" "}
            <span className="text-muted">patents</span>
          </span>
          {cycle !== undefined && (
            <span>
              {cycle} y <span className="text-muted">cycle</span>
            </span>
          )}
        </div>
        {topPatents.length > 0 && (
          <details className="group">
            <summary className="cursor-pointer font-mono text-[11px] text-accent hover:underline list-none">
              top {topPatents.length} cited patents{" "}
              <span className="text-muted group-open:hidden">▸</span>
              <span className="text-muted hidden group-open:inline">▾</span>
            </summary>
            <ol className="mt-2 flex flex-col gap-1 max-h-56 overflow-y-auto pr-1">
              {topPatents.map((tp, i) => (
                <li key={tp.pub} className="flex items-baseline gap-2 font-mono text-[10px]">
                  <span className="text-muted w-4 shrink-0 text-right">{i + 1}.</span>
                  <a
                    href={espacenetUrl(tp.pub)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-accent hover:underline shrink-0"
                  >
                    {tp.pub} ↗
                  </a>
                  <span className="text-muted shrink-0 tabular-nums">
                    {tp.cites.toLocaleString("en-US")}×{tp.year ? ` · ${tp.year}` : ""}
                  </span>
                  <span className="text-text truncate min-w-0" title={tp.title}>
                    {tp.title || "—"}
                  </span>
                </li>
              ))}
            </ol>
          </details>
        )}
        {partners.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted shrink-0">
              converges with
            </span>
            {partners.map((p) => (
              <span
                key={p.cpc}
                className="font-mono text-[10px] text-text border border-border px-1.5 py-0.5 max-w-[180px] truncate"
                title={`${p.cpc} — ${p.title}`}
              >
                {shortPartnerLabel(p)}
              </span>
            ))}
          </div>
        )}
      </footer>
    </article>
  );
}
