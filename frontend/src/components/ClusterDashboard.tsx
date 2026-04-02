"use client";

import Link from "next/link";
import { useLocale } from "@/lib/locale-context";
import type { Trend, VerticalInfo } from "@/lib/types";
import { getMegaTrendInfo } from "@/lib/types";
import TrendCard from "./TrendCard";

interface MegaTrendItem {
  mega_trend: string;
  count: number;
  verticals: string[];
  verticalInfos: VerticalInfo[];
}

export default function ClusterDashboard({
  megaTrends,
  crossVerticalTrends,
  topTrends,
}: {
  megaTrends: MegaTrendItem[];
  crossVerticalTrends: Trend[];
  topTrends: Trend[];
}) {
  const { locale, mounted, t } = useLocale();
  const effectiveLocale = mounted ? locale : "de";

  return (
    <>
      <div className="mb-10">
        <h1 className="text-3xl md:text-4xl font-bold tracking-tight mb-3">
          {t("clusterDashboard")}
        </h1>
        <p className="text-muted text-lg max-w-2xl">
          {t("clusterSubtitle")}
        </p>
      </div>

      {/* Mega-Trends Overview */}
      <section className="mb-12">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-xl font-semibold">{t("megaTrends")}</h2>
          <Link
            href="/trends/mega"
            className="text-sm text-accent hover:underline"
          >
            {t("viewAllMegaTrends")} →
          </Link>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {megaTrends.map((mt) => {
            const info = getMegaTrendInfo(mt.mega_trend);
            const displayName = info
              ? effectiveLocale === "de"
                ? info.name_de
                : info.name_en
              : mt.mega_trend;
            const icon = info?.icon ?? "📊";

            return (
              <Link
                key={mt.mega_trend}
                href={`/trends/mega/${encodeURIComponent(mt.mega_trend.toLowerCase().replace(/\s+/g, "-"))}`}
                className="rounded-xl border border-border bg-card p-5 hover:bg-card-hover hover:border-accent/30 transition-all"
              >
                <div className="flex items-start gap-2 mb-2">
                  <span className="text-lg">{icon}</span>
                  <h3 className="text-sm font-semibold line-clamp-2">
                    {displayName}
                  </h3>
                </div>
                <p className="text-xs text-muted mb-3">
                  {mt.count} {t("megaTrendTrends")}
                </p>
                <div className="flex flex-wrap gap-1">
                  {mt.verticalInfos.slice(0, 4).map((v) => (
                    <span
                      key={v.id}
                      className="text-xs"
                      style={{ color: v.color }}
                      title={v.label}
                    >
                      {v.icon}
                    </span>
                  ))}
                  {mt.verticalInfos.length > 4 && (
                    <span className="text-xs text-muted">
                      +{mt.verticalInfos.length - 4}
                    </span>
                  )}
                </div>
              </Link>
            );
          })}
        </div>
      </section>

      {/* Cross-Vertical Trends */}
      {crossVerticalTrends.length > 0 && (
        <section className="mb-12">
          <div className="flex items-center justify-between mb-5">
            <h2 className="text-xl font-semibold">
              {t("crossVerticalTitle")}
            </h2>
            <Link
              href="/trends/cross-vertical"
              className="text-sm text-accent hover:underline"
            >
              {t("viewAll")} →
            </Link>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {crossVerticalTrends.map((trend) => (
              <TrendCard key={trend.id} trend={trend} />
            ))}
          </div>
        </section>
      )}

      {/* Top Trends by Engagement */}
      {topTrends.length > 0 && (
        <section className="mb-12">
          <h2 className="text-xl font-semibold mb-5">{t("topTrends")}</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {topTrends.map((trend) => (
              <TrendCard key={trend.id} trend={trend} />
            ))}
          </div>
        </section>
      )}
    </>
  );
}
