import { getMegaTrends, getCrossVerticalTrends, getTopTrendsByEngagement } from "@/lib/db";
import { getVerticalInfo } from "@/lib/types";
import ClusterDashboard from "@/components/ClusterDashboard";
import ForesightCta from "@/components/ForesightCta";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Trend-Cluster Dashboard — Catandary Trends",
  description:
    "Cross-Industry Trend-Cluster und Mega-Trend-Übersicht. Powered by Catandary Foresight.",
};

export default async function ClustersPage() {
  const megaTrends = (await getMegaTrends("published")).slice(0, 8);
  const displayMega = megaTrends.length > 0 ? megaTrends : (await getMegaTrends()).slice(0, 8);

  const crossVertical = await getCrossVerticalTrends({ status: "published", limit: 6 });
  const displayCross = crossVertical.length > 0
    ? crossVertical
    : await getCrossVerticalTrends({ limit: 6 });

  const topTrends = await getTopTrendsByEngagement(6);

  const enrichedMega = displayMega.map((mt) => ({
    ...mt,
    verticalInfos: mt.verticals.map((v) =>
      getVerticalInfo(v as Parameters<typeof getVerticalInfo>[0])
    ),
  }));

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <ClusterDashboard
        megaTrends={enrichedMega}
        crossVerticalTrends={displayCross}
        topTrends={topTrends}
      />
      <ForesightCta />
    </div>
  );
}
