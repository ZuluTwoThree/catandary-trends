import { getCrossVerticalTrends } from "@/lib/db";
import TrendCard from "@/components/TrendCard";
import CrossVerticalHeader from "@/components/CrossVerticalHeader";
import ForesightCta from "@/components/ForesightCta";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Cross-Industry Trends — Catandary Trends",
  description:
    "Trend-Signale, die mehrere Branchen gleichzeitig betreffen.",
};

export default function CrossVerticalPage() {
  let trends = getCrossVerticalTrends({ status: "published", limit: 50 });
  if (trends.length === 0) {
    trends = getCrossVerticalTrends({ limit: 50 });
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <CrossVerticalHeader count={trends.length} />

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
        {trends.map((trend) => (
          <TrendCard key={trend.id} trend={trend} />
        ))}
      </div>

      <ForesightCta />
    </div>
  );
}
