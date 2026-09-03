import { q1 } from "@/lib/pg";
import { getTechnologies } from "@/lib/technology";
import TechnologyCard from "@/components/foresight/TechnologyCard";
import TechnologyTool from "@/components/foresight/TechnologyTool";

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
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-4">
          —— Technology Axes
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

      {/* Merged on-demand tool (#28/#36/#42/#43): one input → user-selectable CPC
          domain → one canonical TIR trajectory + cross-tier lead time. */}
      <div className="mb-10">
          <TechnologyTool />
      </div>

      <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-4">
        —— Curated technologies
      </div>

      {technologies.length === 0 ? (
        <div className="border border-border bg-card/40 p-10 text-center">
          <p className="font-sans text-text mb-2">Technology insights are being computed.</p>
          <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
            Check back shortly — the first analysis run has not been persisted yet.
          </p>
        </div>
      ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
            {technologies.map((t) => (
              <TechnologyCard key={t.symbol} tech={t} />
            ))}
          </div>
      )}

      {/* Methodology / trust — the USP: improvement rates on the actual MIT method */}
      <div className="mt-8 border border-border bg-card/40 px-5 py-4">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-2">
          —— How we predict improvement rates
        </div>
        <p className="font-sans text-sm text-text leading-relaxed max-w-3xl">
          Technology Improvement Rates use the peer-reviewed{" "}
          <span className="text-paper">Search Path Node Pair (SPNP) patent-network centrality</span>{" "}
          method of{" "}
          <a
            href="https://doi.org/10.1016/j.respol.2021.104294"
            target="_blank"
            rel="noopener noreferrer"
            className="text-accent hover:underline"
          >
            Singh, Triulzi &amp; Magee (MIT), Research Policy 2021 ↗
          </a>
          , computed on our worldwide 145M-edge citation graph and calibrated against the
          original MIT ground-truth performance series (Spearman 0.76, R² 0.57 on their exact
          benchmark patent sets; our estimates reproduce the 1,757 published MIT domain
          forecasts at rank correlation 0.68). The rate is a{" "}
          <span className="text-paper">relative measure of development speed</span> — use it to
          compare fields against each other, not as an early-warning signal for adoption booms.
          These are estimates from patent-network structure, not measured product performance;
          very fast software fields and thinly-covered classes carry wider uncertainty. We show
          the rate and its evidence — the interpretation is yours.
        </p>
      </div>
    </div>
  );
}
