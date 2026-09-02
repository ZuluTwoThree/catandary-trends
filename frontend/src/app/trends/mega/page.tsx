import { getMegaTrends } from "@/lib/db";
import { getVerticalInfo } from "@/lib/types";
import MegaTrendsPage from "@/components/MegaTrendsPage";
import ForesightCta from "@/components/ForesightCta";
import { dynamicUnlessStatic } from "@/lib/renderMode";

export const metadata = {
  title: "Mega Signal Themes — Catandary Trends",
  description:
    "The curated signal themes every signal is mapped into — with measured momentum, and an earned Megatrend mark where reach, maturity and lead time back it.",
};

export default async function MegaTrendsRoute() {
  await dynamicUnlessStatic();
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
    // earned Megatrends lead the grid, faded hype sinks last, then momentum, then volume
    if (Boolean(a.megatrend) !== Boolean(b.megatrend)) return a.megatrend ? -1 : 1;
    const fa = Boolean(a.measured?.faded_hype), fb = Boolean(b.measured?.faded_hype);
    if (fa !== fb) return fa ? 1 : -1;
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
