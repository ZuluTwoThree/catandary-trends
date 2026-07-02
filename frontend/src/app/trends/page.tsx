import { Suspense } from "react";
import {
  getTrendsFiltered,
  getTrendsFilteredCount,
  getTrendsCount,
  getVerticalCounts,
  getVerticalCountsScoped,
  getMegaTrends,
  getTopSourcesByCount,
} from "@/lib/db";
import { parseFilterParams } from "@/lib/filter-params";
import TrendCard from "@/components/TrendCard";
import TrendRow from "@/components/TrendRow";
import Pagination from "@/components/Pagination";
import TrendsHero from "@/components/TrendsHero";
import TrendsEmpty from "@/components/TrendsEmpty";
import ForesightCta from "@/components/ForesightCta";
import FilterBar from "@/components/filters/FilterBar";
import ActiveChips from "@/components/filters/ActiveChips";
import { TrendsListJsonLd } from "@/components/JsonLd";

export const dynamic = "force-dynamic";

export default async function TrendsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const raw = await searchParams;
  const filters = parseFilterParams(raw);

  // Main result set
  const trends = getTrendsFiltered(filters);
  const total = getTrendsFilteredCount(filters);

  // Counts for filter controls
  const scopedVerticalCounts = getVerticalCountsScoped(filters);
  const globalVerticalCounts = getVerticalCounts("published");
  const totalPublished = Object.values(globalVerticalCounts).reduce(
    (a, b) => a + b,
    0
  );
  // Full analyzed corpus (all pipeline signals, not just published) — the real
  // scale, a trust signal that the published-count alone undersells.
  const analyzedTotal = getTrendsCount();

  // Mega trend options (top 12 by count, respecting status)
  const megaOptions = getMegaTrends("published")
    .slice(0, 12)
    .map((m) => ({
      key: m.mega_trend,
      name: m.name_en,
      count: m.count,
    }));

  // Source options (top 20 for exclude dropdown)
  const sourceOptions = getTopSourcesByCount(20, "published");

  return (
    <div className="mx-auto max-w-7xl px-6 md:px-10 py-10">
      <TrendsListJsonLd />
      <TrendsHero
        totalSignals={totalPublished}
        analyzedTotal={analyzedTotal}
        verticalCounts={globalVerticalCounts}
      />

      {/* Filter controls */}
      <Suspense fallback={null}>
        <div className="mb-6">
          <FilterBar
            filters={filters}
            verticalCounts={scopedVerticalCounts}
            megaOptions={megaOptions}
            sourceOptions={sourceOptions}
          />
        </div>
      </Suspense>

      {/* Active-chips strip */}
      <Suspense fallback={null}>
        <div className="mb-6">
          <ActiveChips filters={filters} />
        </div>
      </Suspense>

      {/* Result count */}
      <div className="mb-6 flex items-baseline justify-between">
        <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted">
          <span className="text-accent tabular-nums">
            {total.toLocaleString("en-US")}
          </span>
          <span className="text-muted/70"> / Signals</span>
        </div>
        <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted">
          —— 02
        </div>
      </div>

      {/* Results */}
      {trends.length === 0 ? (
        <Suspense fallback={null}>
          <TrendsEmpty filters={filters} />
        </Suspense>
      ) : filters.view === "list" ? (
        <div className="border border-border">
          {trends.map((trend) => (
            <TrendRow key={trend.id} trend={trend} />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {trends.map((trend) => (
            <TrendCard key={trend.id} trend={trend} />
          ))}
        </div>
      )}

      {trends.length > 0 && (
        <Suspense fallback={null}>
          <Pagination
            total={total}
            page={filters.page}
            perPage={filters.limit ?? 12}
          />
        </Suspense>
      )}

      <ForesightCta />
    </div>
  );
}
