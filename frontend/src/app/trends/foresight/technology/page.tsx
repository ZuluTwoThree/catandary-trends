import Link from "next/link";
import { q1 } from "@/lib/pg";
import { getTechnologies } from "@/lib/technology";
import TechnologyCard from "@/components/foresight/TechnologyCard";
import TechQuery from "@/components/foresight/TechQuery";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Technology Axes — Catandary Foresight",
  description:
    "How fast each technology field iterates — innovation cycles, key patents and convergence, measured across 20M signals on the full innovation maturity chain.",
};

/**
 * Technology Explorer (frontend revamp test, issues #3/#23/#28).
 *
 * Low-threshold UX: loads as a finished editorial view — curated technology
 * axes sorted by research lead time, each card a plain-language statement
 * backed by the four-tier evidence. No filters, no configuration.
 *
 * Subscription gating is display-only for this test (visual concept for
 * free/starter/pro/super pro+; real auth/payment is issue #17).
 */

async function corpusStats() {
  // reltuples estimates — instant, close enough for a trust banner at 10^8 scale
  const row = await q1<{ patents: string; edges: string; signals: string }>(`
    SELECT
      (SELECT reltuples::bigint FROM pg_class WHERE relname = 'patent_links') AS edges,
      (SELECT reltuples::bigint FROM pg_class WHERE relname = 'raw_entries') AS patents,
      (SELECT COUNT(*) FROM trends WHERE embedding_1024 IS NOT NULL) AS signals
  `);
  return {
    raw: Number(row?.patents ?? 0),
    edges: Number(row?.edges ?? 0),
    signals: Number(row?.signals ?? 0),
  };
}

function fmtM(n: number): string {
  return n >= 1e6 ? `${(n / 1e6).toFixed(n >= 1e7 ? 0 : 1)}M` : `${Math.round(n / 1e3)}k`;
}

export default async function TechnologyExplorerPage() {
  const [technologies, stats] = await Promise.all([getTechnologies(), corpusStats()]);

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <div className="mb-10">
        <div className="flex items-center gap-3 mb-4">
          <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent">
            —— Technology Axes
          </div>
          <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-paper bg-accent/20 border border-accent/40 px-2 py-0.5">
            Pro preview
          </span>
        </div>
        <h1 className="font-display text-4xl md:text-[52px] leading-[1.05] tracking-tight text-paper mb-4">
          Where innovation moves <span className="italic">fastest</span>
        </h1>
        <p className="font-sans text-text text-lg leading-relaxed max-w-2xl">
          For each technology we overlay its evidence across{" "}
          <span className="text-paper">research, patents, funding and market coverage</span>{" "}
          and measure how fast the field iterates — from our own data, evidence
          one click away. Fastest-moving fields first.
        </p>

        {/* Trust banner (#23): the real corpus scale behind the claim */}
        <div className="mt-6 flex flex-wrap gap-x-8 gap-y-2 border border-border bg-card/40 px-5 py-3">
          {[
            [fmtM(stats.raw), "signals across the innovation chain"],
            [fmtM(stats.edges), "patent citations mapped"],
            [fmtM(stats.signals), "classified trend signals"],
            ["1990", "history depth, research & patents"],
          ].map(([v, label]) => (
            <div key={label} className="flex items-baseline gap-2">
              <span className="font-display text-2xl text-paper tabular-nums">{v}</span>
              <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
                {label}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Super Pro+ on-demand scope — ask any technology, computed live */}
      <div className="mb-10">
        <TechQuery />
      </div>

      <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-4">
        —— Curated technologies
      </div>

      {technologies.length === 0 ? (
        <div className="border border-border bg-card/40 p-10 text-center">
          <p className="font-sans text-text mb-2">Technology insights are being computed.</p>
          <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
            run scripts/build_cpc_insights.py
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
          {technologies.map((t) => (
            <TechnologyCard key={t.symbol} tech={t} />
          ))}
        </div>
      )}

      {/* Display-only tier concept (real gating = issue #17) */}
      <div className="mt-12 border border-border bg-card/40 p-6">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-3">
          —— Plans
        </div>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {[
            ["Free", "Curated trend articles, browsing, newsletter"],
            ["Starter", "Cluster explorer: momentum & source corroboration"],
            ["Pro", "Technology lead times, key patents, convergence axes"],
            ["Super Pro+", "Your own scopes on demand, API access, raw evidence graph"],
          ].map(([tier, desc], i) => (
            <div
              key={tier}
              className={`border p-4 ${i === 2 ? "border-accent/50 bg-accent/5" : "border-border"}`}
            >
              <div className="font-display text-lg text-paper mb-1">{tier}</div>
              <p className="font-sans text-sm text-text leading-snug">{desc}</p>
              {i === 2 && (
                <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-accent mt-2">
                  this page
                </p>
              )}
            </div>
          ))}
        </div>
        <p className="font-sans text-sm text-muted mt-4">
          You are viewing the Pro preview.{" "}
          <Link href="/trends/newsletter" className="text-accent hover:underline">
            Get notified when plans launch →
          </Link>
        </p>
      </div>
    </div>
  );
}
