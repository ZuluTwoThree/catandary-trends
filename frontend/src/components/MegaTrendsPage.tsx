"use client";

import Link from "next/link";
import { useLocale } from "@/lib/locale-context";
import type { VerticalInfo, MegaTrendInfo } from "@/lib/types";
import { getMegaTrendInfo } from "@/lib/types";

interface MegaTrendItem {
  mega_trend: string;
  count: number;
  verticals: string[];
  verticalInfos: VerticalInfo[];
  slug: string;
  momentum?: "rising" | "stable" | "declining" | "emerging";
  cluster_strength?: "strong" | "moderate" | "fragmented";
  horizon?: string;
  description?: string;
}

const MOMENTUM_CONFIG = {
  rising: {
    label_en: "Rising", label_de: "Steigend", color: "#22c55e", icon: "\u2197",
    tooltip_en: "Signal frequency is clearly increasing — the trend is gaining traction across sources.",
    tooltip_de: "Die Signalhäufigkeit nimmt deutlich zu — der Trend gewinnt quellenübergreifend an Momentum.",
  },
  stable: {
    label_en: "Stable", label_de: "Stabil", color: "#a3a3a3", icon: "\u2192",
    tooltip_en: "Signal frequency is steady — the trend is established with no clear up- or downward shift.",
    tooltip_de: "Die Signalhäufigkeit bleibt konstant — der Trend ist etabliert, ohne klaren Auf- oder Abwärtsimpuls.",
  },
  declining: {
    label_en: "Declining", label_de: "Abnehmend", color: "#ef4444", icon: "\u2198",
    tooltip_en: "Signal frequency is decreasing — the trend is losing momentum relative to earlier periods.",
    tooltip_de: "Die Signalhäufigkeit nimmt ab — der Trend verliert gegenüber früheren Perioden an Momentum.",
  },
  emerging: {
    label_en: "Emerging", label_de: "Aufkommend", color: "#a855f7", icon: "\u2728",
    tooltip_en: "Early-stage signal — small absolute volume but sharp recent growth, worth watching.",
    tooltip_de: "Früher Trend — geringe absolute Zahl an Signalen, aber starker Zuwachs, beobachtenswert.",
  },
} as const;

export default function MegaTrendsPage({
  megaTrends,
}: {
  megaTrends: MegaTrendItem[];
}) {
  const { locale, mounted, t } = useLocale();
  const effectiveLocale = mounted ? locale : "de";

  return (
    <>
      <div className="mb-10">
        <h1 className="text-3xl md:text-4xl font-bold tracking-tight mb-3">
          {t("megaTrends")}
        </h1>
        <p className="text-muted text-lg max-w-2xl">
          {t("megaTrendsSubtitle")}
        </p>
      </div>

      {megaTrends.length === 0 ? (
        <p className="text-muted">{t("emptySubtitle")}</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {megaTrends.map((mt) => {
            const info = getMegaTrendInfo(mt.mega_trend);
            const displayName = info
              ? effectiveLocale === "de"
                ? info.name_de
                : info.name_en
              : mt.mega_trend;
            const description = info
              ? effectiveLocale === "de"
                ? info.description_de
                : info.description_en
              : null;
            const icon = info?.icon ?? "📊";

            return (
              <Link
                key={mt.mega_trend}
                href={`/trends/mega/${mt.slug}`}
                className="rounded-xl border border-border bg-card p-6 hover:bg-card-hover hover:border-accent/30 transition-all group"
              >
                <div className="flex items-start gap-3 mb-3">
                  <span className="text-2xl">{icon}</span>
                  <div className="flex-1 min-w-0">
                    <h2 className="text-lg font-semibold group-hover:text-accent transition-colors">
                      {displayName}
                    </h2>
                    {description && (
                      <p className="text-sm text-muted mt-1 line-clamp-2">
                        {description}
                      </p>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-3 text-sm text-muted mb-4 flex-wrap">
                  <span>
                    {mt.count} {t("megaTrendTrends")}
                  </span>
                  {mt.momentum && (
                    <span
                      className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border cursor-help"
                      title={
                        effectiveLocale === "de"
                          ? MOMENTUM_CONFIG[mt.momentum].tooltip_de
                          : MOMENTUM_CONFIG[mt.momentum].tooltip_en
                      }
                      style={{
                        color: MOMENTUM_CONFIG[mt.momentum].color,
                        borderColor: MOMENTUM_CONFIG[mt.momentum].color + "40",
                        backgroundColor: MOMENTUM_CONFIG[mt.momentum].color + "10",
                      }}
                    >
                      {MOMENTUM_CONFIG[mt.momentum].icon}{" "}
                      {effectiveLocale === "de"
                        ? MOMENTUM_CONFIG[mt.momentum].label_de
                        : MOMENTUM_CONFIG[mt.momentum].label_en}
                    </span>
                  )}
                </div>
                <div>
                  <span className="text-xs text-muted block mb-2">
                    {t("megaTrendVerticals")}
                  </span>
                  <div className="flex flex-wrap gap-2">
                    {mt.verticalInfos.map((v) => (
                      <span
                        key={v.id}
                        className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-full border border-border"
                        style={{ color: v.color }}
                      >
                        {v.icon} {v.label}
                      </span>
                    ))}
                  </div>
                </div>
                <p className="text-xs text-accent/60 mt-4">
                  {t("megaTrendCta")} →
                </p>
              </Link>
            );
          })}
        </div>
      )}
    </>
  );
}
