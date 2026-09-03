import { Suspense } from "react";
import { redirect } from "next/navigation";
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
import { archiveWindowDays } from "@/lib/archiveWindow";
import TrendCard from "@/components/TrendCard";
import TrendRow from "@/components/TrendRow";
import Pagination from "@/components/Pagination";
import TrendsHero from "@/components/TrendsHero";
import TrendsEmpty from "@/components/TrendsEmpty";
import ForesightCta from "@/components/ForesightCta";
import MovingNow from "@/components/MovingNow";
import FilterBar from "@/components/filters/FilterBar";
import ActiveChips from "@/components/filters/ActiveChips";
import { TrendsListJsonLd } from "@/components/JsonLd";
import { dynamicUnlessStatic, isStaticExport } from "@/lib/renderMode";
import StaticFeed, { staticListingMetadata } from "@/components/StaticFeed";
import type { Metadata } from "next";

/**
 * Static export: /trends is page 1 of the static listing
 * (components/StaticFeed.tsx — /trends/page/[n], /trends/v/[vertical] are
 * its siblings). The search-param feed below cannot be exported (reading
 * `searchParams` makes a page dynamic) and stays the workstation's feed.
 * Outside the export the metadata falls back to the layout's.
 */
export async function generateMetadata(): Promise<Metadata> {
  if (!isStaticExport()) return {};
  return staticListingMetadata(null, 1);
}

export default async function TrendsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  if (isStaticExport()) return <StaticFeed vertical={null} page={1} />;

  await dynamicUnlessStatic();
  const raw = await searchParams;
  const filters = parseFilterParams(raw);

  // Public window (#93): PUBLIC_MODE caps how far back the feed reaches
  // (lib/archiveWindow.ts); null on the owner instance leaves it open.
  filters.max_age_days = archiveWindowDays();

  // One parallel round-trip instead of seven sequential ones (ARCH-11); the
  // aggregate queries are additionally TTL-cached in lib/db.
  const [
    trends,
    total,
    scopedVerticalCounts,
    globalVerticalCounts,
    analyzedTotal,
    megaTrends,
    sourceOptions,
  ] = await Promise.all([
    getTrendsFiltered(filters),
    getTrendsFilteredCount(filters),
    getVerticalCountsScoped(filters),
    getVerticalCounts("published"),
    // Full analyzed corpus (all pipeline signals, not just published) — the
    // real scale, a trust signal the published-count alone undersells.
    getTrendsCount(),
    getMegaTrends("published"),
    getTopSourcesByCount(20, "published"),
  ]);

  // A page number beyond the end is a dead end (KEY-10) — snap to the last
  // real page instead of rendering a misleading "no trends match" state.
  const perPage = filters.limit ?? 12;
  const lastPage = Math.max(1, Math.ceil(total / perPage));
  if (filters.page > lastPage) {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(raw)) {
      if (typeof v === "string" && k !== "page") params.set(k, v);
    }
    if (lastPage > 1) params.set("page", String(lastPage));
    const qs = params.toString();
    redirect(`/trends${qs ? `?${qs}` : ""}`);
  }

  const totalPublished = Object.values(globalVerticalCounts).reduce(
    (a, b) => a + b,
    0
  );

  // Mega trend options (top 12 by count, respecting status)
  const megaOptions = megaTrends.slice(0, 12).map((m) => ({
    key: m.mega_trend,
    name: m.name_en,
    count: m.count,
  }));

  return (
    <div className="mx-auto max-w-7xl px-6 md:px-10 py-10">
      <TrendsListJsonLd />
      <TrendsHero
        totalSignals={totalPublished}
        analyzedTotal={analyzedTotal}
        verticalCounts={globalVerticalCounts}
      />

      {/* Value-first: what's moving right now (rising clusters) above the feed */}
      <Suspense fallback={null}>
        <MovingNow />
      </Suspense>

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
      <h2 className="sr-only">Latest signals</h2>
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
