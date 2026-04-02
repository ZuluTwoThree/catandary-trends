import { notFound } from "next/navigation";
import { getMegaTrends, getTrendsByMegaTrend } from "@/lib/db";
import { getMegaTrendInfo } from "@/lib/types";
import TrendCard from "@/components/TrendCard";
import ForesightCta from "@/components/ForesightCta";
import MegaTrendHeader from "@/components/MegaTrendHeader";
import type { Metadata } from "next";

export const dynamic = "force-dynamic";

function findMegaTrend(slug: string, allMega: { mega_trend: string; count: number; verticals: string[] }[]) {
  const decoded = decodeURIComponent(slug);
  // Try direct match: URL uses hyphens, DB keys use underscores
  const asKey = decoded.replace(/-/g, "_");
  const match = allMega.find(
    (m) => m.mega_trend === asKey || m.mega_trend.toLowerCase() === asKey.toLowerCase()
  );
  if (match) return match;
  // Fallback: match with spaces (for any legacy URLs)
  const asSpaces = decoded.replace(/-/g, " ");
  return allMega.find(
    (m) => m.mega_trend.toLowerCase() === asSpaces.toLowerCase()
  );
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ megatrend: string }>;
}): Promise<Metadata> {
  const { megatrend } = await params;
  const allMega = getMegaTrends();
  const match = findMegaTrend(megatrend, allMega);
  if (!match) return { title: "Mega-Trend nicht gefunden" };

  const info = getMegaTrendInfo(match.mega_trend);
  const displayName = info?.name_en ?? match.mega_trend;

  return {
    title: `${displayName} — Catandary Mega-Trends`,
    description: info?.description_en ?? `Trend signals for mega-trend "${displayName}" across ${match.verticals.length} industries.`,
  };
}

export default async function MegaTrendPage({
  params,
}: {
  params: Promise<{ megatrend: string }>;
}) {
  const { megatrend } = await params;
  const allMega = getMegaTrends();
  const match = findMegaTrend(megatrend, allMega);
  if (!match) notFound();

  let trends = getTrendsByMegaTrend(match.mega_trend, { status: "published" });
  if (trends.length === 0) {
    trends = getTrendsByMegaTrend(match.mega_trend);
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <MegaTrendHeader
        megaTrend={match.mega_trend}
        count={match.count}
        verticals={match.verticals}
      />

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 mt-8">
        {trends.map((trend) => (
          <TrendCard key={trend.id} trend={trend} />
        ))}
      </div>

      <ForesightCta />
    </div>
  );
}
