import { Suspense } from "react";
import { getTrends, getVerticalCounts } from "@/lib/db";
import type { Vertical } from "@/lib/types";
import TrendCard from "@/components/TrendCard";
import VerticalFilter from "@/components/VerticalFilter";

export const dynamic = "force-dynamic";

export default async function TrendsPage({
  searchParams,
}: {
  searchParams: Promise<{ vertical?: string }>;
}) {
  const params = await searchParams;
  const vertical = (params.vertical as Vertical) || null;

  const trends = getTrends({
    status: "published",
    vertical: vertical ?? undefined,
    limit: 50,
  });

  // If no published trends, show all (including drafts) for development
  const displayTrends =
    trends.length > 0
      ? trends
      : getTrends({ vertical: vertical ?? undefined, limit: 50 });

  const counts = getVerticalCounts();

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      {/* Hero */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight mb-2">
          Cross-Industry Trend Intelligence
        </h1>
        <p className="text-muted text-lg max-w-2xl">
          Kuratierte Trend-Signale aus 10 Industrie-Vertikalen. Analysiert,
          klassifiziert und eingeordnet.
        </p>
      </div>

      {/* Vertical Filter */}
      <div className="mb-8">
        <Suspense fallback={null}>
          <VerticalFilter active={vertical} counts={counts} />
        </Suspense>
      </div>

      {/* Trend Grid */}
      {displayTrends.length === 0 ? (
        <div className="text-center py-20">
          <p className="text-muted text-lg">
            Noch keine Trends
            {vertical ? ` in ${vertical}` : ""} vorhanden.
          </p>
          <p className="text-muted text-sm mt-2">
            Die Pipeline läuft — bald erscheinen hier kuratierte Trend-Signale.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {displayTrends.map((trend) => (
            <TrendCard key={trend.id} trend={trend} />
          ))}
        </div>
      )}

      {/* CTA */}
      <div className="mt-16 rounded-xl border border-accent/20 bg-accent/5 p-8 text-center">
        <h2 className="text-xl font-semibold mb-2">
          Tiefere Analysen gefragt?
        </h2>
        <p className="text-muted mb-4 max-w-lg mx-auto">
          Catandary Foresight bietet vollständige Mega/Macro/Micro-Prognosen,
          Cross-Industry-Cluster und strategische Handlungsempfehlungen.
        </p>
        <a
          href="https://catandary.de"
          className="inline-flex items-center gap-2 bg-accent text-background px-5 py-2.5 rounded-lg font-medium hover:bg-accent/90 transition-colors"
        >
          Catandary Foresight entdecken
        </a>
      </div>
    </div>
  );
}
