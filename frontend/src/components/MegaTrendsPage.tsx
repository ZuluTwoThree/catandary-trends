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
}

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
                <div className="flex items-center gap-4 text-sm text-muted mb-4">
                  <span>
                    {mt.count} {t("megaTrendTrends")}
                  </span>
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
