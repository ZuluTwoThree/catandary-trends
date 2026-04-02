import { getMegaTrends } from "@/lib/db";
import { getVerticalInfo } from "@/lib/types";
import MegaTrendsPage from "@/components/MegaTrendsPage";
import ForesightCta from "@/components/ForesightCta";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Mega-Trends — Catandary Trends",
  description:
    "Langfristige Cross-Industry Mega-Trends. Zeithorizont: 10–25 Jahre.",
};

export default function MegaTrendsRoute() {
  const megaTrends = getMegaTrends("published");
  const displayMegaTrends =
    megaTrends.length > 0 ? megaTrends : getMegaTrends();

  const enriched = displayMegaTrends.map((mt) => ({
    ...mt,
    verticalInfos: mt.verticals.map((v) =>
      getVerticalInfo(v as Parameters<typeof getVerticalInfo>[0])
    ),
    // Canonical keys use underscores; URL slugs use hyphens
    slug: encodeURIComponent(mt.mega_trend.replace(/_/g, "-")),
  }));

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <MegaTrendsPage megaTrends={enriched} />
      <ForesightCta />
    </div>
  );
}
