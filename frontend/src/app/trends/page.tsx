import { Suspense } from "react";
import { getTrends, getTrendsCount, getVerticalCounts } from "@/lib/db";
import type { Vertical } from "@/lib/types";
import TrendCard from "@/components/TrendCard";
import VerticalFilter from "@/components/VerticalFilter";
import Pagination from "@/components/Pagination";
import TrendsHero from "@/components/TrendsHero";
import TrendsEmpty from "@/components/TrendsEmpty";
import ForesightCta from "@/components/ForesightCta";
import { TrendsListJsonLd } from "@/components/JsonLd";

export const dynamic = "force-dynamic";

const PER_PAGE = 12;

export default async function TrendsPage({
  searchParams,
}: {
  searchParams: Promise<{ vertical?: string; page?: string }>;
}) {
  const params = await searchParams;
  const vertical = (params.vertical as Vertical) || null;
  const page = Math.max(1, parseInt(params.page || "1"));
  const offset = (page - 1) * PER_PAGE;

  const trends = getTrends({
    status: "published",
    vertical: vertical ?? undefined,
    limit: PER_PAGE,
    offset,
  });

  const total = getTrendsCount({
    status: "published",
    vertical: vertical ?? undefined,
  });

  // If no published trends, show all (including drafts) for development
  const displayTrends =
    trends.length > 0
      ? trends
      : getTrends({ vertical: vertical ?? undefined, limit: PER_PAGE, offset });

  const displayTotal =
    trends.length > 0
      ? total
      : getTrendsCount({ vertical: vertical ?? undefined });

  const counts = getVerticalCounts("published");
  const totalPublished = Object.values(counts).reduce((a, b) => a + b, 0);

  return (
    <div className="mx-auto max-w-7xl px-6 md:px-10 py-10">
      <TrendsListJsonLd />
      <TrendsHero totalSignals={totalPublished} verticalCounts={counts} />

      {/* Vertical Filter */}
      <div className="mb-8">
        <Suspense fallback={null}>
          <VerticalFilter active={vertical} counts={counts} />
        </Suspense>
      </div>

      {/* Trend Grid */}
      {displayTrends.length === 0 ? (
        <TrendsEmpty vertical={vertical} />
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {displayTrends.map((trend) => (
              <TrendCard key={trend.id} trend={trend} />
            ))}
          </div>

          <Suspense fallback={null}>
            <Pagination total={displayTotal} page={page} perPage={PER_PAGE} />
          </Suspense>
        </>
      )}

      <ForesightCta />
    </div>
  );
}
