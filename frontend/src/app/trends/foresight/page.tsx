import ForesightCockpit from "@/components/ForesightCockpit";
import { getLatestClusterRun } from "@/lib/foresight";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Foresight Cockpit — Catandary Trends",
  description:
    "Semantische Trend-Suche mit Signal-Timeline, Lead-Time-Analyse und Cross-Vertical-Insights.",
};

export default async function ForesightRoute() {
  // Default content for the empty state: the top rising clusters, so the page
  // shows value before any query (value-first, low-threshold UX).
  const run = await getLatestClusterRun("global");
  const topClusters = (run?.clusters ?? [])
    .slice()
    .sort((a, b) => b.sov_delta_pp - a.sov_delta_pp || b.size - a.size)
    .slice(0, 4);

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <ForesightCockpit topClusters={topClusters} />
    </div>
  );
}
