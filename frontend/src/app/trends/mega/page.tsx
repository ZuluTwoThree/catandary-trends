import { getMegaTrends } from "@/lib/db";
import { getVerticalInfo } from "@/lib/types";
import MegaTrendsPage from "@/components/MegaTrendsPage";
import ForesightCta from "@/components/ForesightCta";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Mega-Trends — Catandary Trends",
  description:
    "Langfristige Cross-Industry Mega-Trends mit Momentum-Tracking aus dem Catandary-Signalnetzwerk.",
};

export default async function MegaTrendsRoute() {
  const megaTrends = await getMegaTrends("published");
  const displayMegaTrends =
    megaTrends.length > 0 ? megaTrends : await getMegaTrends();

  const MOMENTUM_ORDER = { emerging: 0, rising: 1, stable: 2, declining: 3 };

  const enriched = displayMegaTrends.map((mt) => ({
    ...mt,
    verticalInfos: mt.verticals.map((v) =>
      getVerticalInfo(v as Parameters<typeof getVerticalInfo>[0])
    ),
    slug: encodeURIComponent(mt.mega_trend.replace(/_/g, "-")),
    momentum: mt.momentum,
    cluster_strength: mt.cluster_strength,
    horizon: mt.horizon,
  })).sort((a, b) => {
    const ma = MOMENTUM_ORDER[a.momentum ?? "stable"] ?? 2;
    const mb = MOMENTUM_ORDER[b.momentum ?? "stable"] ?? 2;
    if (ma !== mb) return ma - mb;
    return b.count - a.count;
  });

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <MegaTrendsPage megaTrends={enriched} />
      <ForesightCta />
    </div>
  );
}
