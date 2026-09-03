import Link from "next/link";
import { notFound } from "next/navigation";
import {
  getLeadTimeTechnologies,
  getTierCurves,
  cpcDisplayName,
} from "@/lib/foresight";
import TierCurveChart from "@/components/foresight/TierCurveChart";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Lead Time — Catandary Foresight",
  description:
    "Where research runs ahead of the market: the four innovation tiers — research, patents, funding, market — for a technology over time.",
};

/**
 * Lead-time view (#3 Phase 2 / #23 USP). Low-threshold: opens on the clearest
 * real case with its four-tier curves already drawn, no query needed. A
 * headline "N years ahead" is shown ONLY where the corpus can prove it
 * (reliable emergence in both tiers); everything else is the curves alone.
 */
export default async function LeadTimePage({
  searchParams,
}: {
  searchParams: Promise<{ cpc?: string }>;
}) {
  const techs = await getLeadTimeTechnologies(12);
  if (techs.length === 0) notFound();

  const { cpc } = await searchParams;
  const active = techs.find((t) => t.cpc === cpc?.toUpperCase()) ?? techs[0];
  const { tiers, lead } = await getTierCurves(active.cpc);
  const name = cpcDisplayName(active.title, active.curated_name);
  const leadYears = active.lead_science_vs_market;

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-3">
        —— Foresight · Lead time
      </div>
      <h1 className="font-display text-3xl md:text-[40px] leading-[1.08] tracking-tight text-paper mb-4">
        Where research runs <span className="italic">ahead</span> of the market
      </h1>
      <p className="font-sans text-text text-lg leading-relaxed max-w-2xl mb-8">
        For a technology we line up when each part of the innovation chain started
        talking about it — <span className="text-paper">research, patents, funding, the market</span>{" "}
        — measured as each tier&apos;s share of its own yearly volume, so tiers of
        different size are comparable.
      </p>

      {/* Active technology + honest headline */}
      <div className="border border-border bg-card/40 p-5 mb-6">
        <div className="flex flex-wrap items-baseline justify-between gap-3 mb-1">
          <h2 className="font-display text-2xl text-paper">{name}</h2>
          <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
            patent class {active.cpc}
          </span>
        </div>
        {leadYears != null && active.reliable ? (
          <p className="font-sans text-text leading-relaxed">
            Research activity took off around{" "}
            <span className="text-paper">{active.science_takeoff}</span>, the market
            around <span className="text-paper">{active.market_takeoff}</span> —{" "}
            <span className="text-accent">
              research led the market by ~{leadYears} years
            </span>{" "}
            for this technology.
          </p>
        ) : (
          <p className="font-sans text-muted leading-relaxed">
            An established field — activity is present across all tiers over the
            whole window, so a single &ldquo;years ahead&rdquo; number isn&apos;t
            meaningful. The curves below show how the conversation moved.
          </p>
        )}
      </div>

      <div className="border border-border bg-card/40 p-4 sm:p-6 mb-4">
        <TierCurveChart
          tiers={tiers}
          scienceTakeoff={active.reliable ? active.science_takeoff : null}
          marketTakeoff={active.reliable ? active.market_takeoff : null}
        />
      </div>
      <p className="font-sans text-xs text-muted mb-10 max-w-2xl">
        Each line is scaled to its own peak, so the chart compares <span className="text-text">timing,
        not volume</span>: when the research curve rises years before the market curve, that gap is
        the lead time — the window the Foresight layer turns into a forecast.
      </p>

      {/* Pick another technology (single visible control — low-threshold). */}
      <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-3">
        —— Technologies where research measurably led the market
      </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {techs.map((t) => {
            const tn = cpcDisplayName(t.title, t.curated_name);
            const on = t.cpc === active.cpc;
            return (
              <Link
                key={t.cpc}
                href={`/trends/foresight/lead-time?cpc=${t.cpc}`}
                scroll={false}
                className={`border p-4 transition-colors ${
                  on
                    ? "border-accent/60 bg-accent/5"
                    : "border-border bg-card/40 hover:bg-card"
                }`}
              >
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-display text-[17px] text-paper leading-snug">
                    {tn}
                  </span>
                  {t.lead_science_vs_market != null && (
                    <span className="font-mono text-[11px] text-accent whitespace-nowrap">
                      ~{t.lead_science_vs_market}y
                    </span>
                  )}
                </div>
                <div className="font-mono text-[9px] uppercase tracking-[0.12em] text-muted mt-1">
                  research {t.science_takeoff} → market {t.market_takeoff}
                </div>
              </Link>
            );
          })}
        </div>

      <div className="mt-10 border border-border bg-card/40 px-5 py-4">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-2">
          —— How we keep this honest
        </div>
        <p className="font-sans text-sm text-text leading-relaxed max-w-3xl">
          Our market coverage runs back to ~2006 while research and patents reach
          to 1990, so a raw &ldquo;years ahead&rdquo; would exaggerate the lead. We
          only headline a lead time where both tiers demonstrably emerged inside the
          window they share; for older technologies we show the curves and say so.
          This is the corpus being honest about what it can prove.
        </p>
      </div>
    </div>
  );
}
