import { notFound } from "next/navigation";
import { getMegaTrends, getTrendsByMegaTrend } from "@/lib/db";
import TrendCard from "@/components/TrendCard";
import ForesightCta from "@/components/ForesightCta";
import MegaTrendHeader from "@/components/MegaTrendHeader";
import type { Metadata } from "next";

export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ megatrend: string }>;
}): Promise<Metadata> {
  const { megatrend } = await params;
  const decoded = decodeURIComponent(megatrend).replace(/-/g, " ");
  const allMega = getMegaTrends();
  const match = allMega.find(
    (m) => m.mega_trend.toLowerCase() === decoded.toLowerCase()
  );
  if (!match) return { title: "Mega-Trend nicht gefunden" };

  return {
    title: `${match.mega_trend} — Catandary Mega-Trends`,
    description: `Trend-Signale zum Mega-Trend "${match.mega_trend}" aus ${match.verticals.length} Branchen.`,
  };
}

export default async function MegaTrendPage({
  params,
}: {
  params: Promise<{ megatrend: string }>;
}) {
  const { megatrend } = await params;
  const decoded = decodeURIComponent(megatrend).replace(/-/g, " ");
  const allMega = getMegaTrends();
  const match = allMega.find(
    (m) => m.mega_trend.toLowerCase() === decoded.toLowerCase()
  );
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
