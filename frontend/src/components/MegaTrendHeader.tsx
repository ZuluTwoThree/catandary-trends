"use client";

import Link from "next/link";
import { useLocale } from "@/lib/locale-context";
import { getVerticalInfo, getMegaTrendInfo } from "@/lib/types";
import type { Vertical } from "@/lib/types";

export default function MegaTrendHeader({
  megaTrend,
  count,
  verticals,
}: {
  megaTrend: string;
  count: number;
  verticals: string[];
}) {
  const { locale, mounted, t } = useLocale();
  const effectiveLocale = mounted ? locale : "de";

  const info = getMegaTrendInfo(megaTrend);
  const displayName = info
    ? effectiveLocale === "de"
      ? info.name_de
      : info.name_en
    : megaTrend;
  const description = info
    ? effectiveLocale === "de"
      ? info.description_de
      : info.description_en
    : null;
  const icon = info?.icon ?? "📊";

  return (
    <>
      <nav className="flex items-center gap-2 text-sm text-muted mb-6">
        <Link
          href="/trends"
          className="hover:text-foreground transition-colors"
        >
          {t("trends")}
        </Link>
        <span>/</span>
        <Link
          href="/trends/mega"
          className="hover:text-foreground transition-colors"
        >
          {t("megaTrends")}
        </Link>
        <span>/</span>
        <span className="text-foreground">{displayName}</span>
      </nav>

      <div className="mb-8">
        <div className="flex items-center gap-3 mb-3">
          <span className="text-3xl">{icon}</span>
          <h1 className="text-3xl md:text-4xl font-bold tracking-tight">
            {displayName}
          </h1>
        </div>
        {description && (
          <p className="text-muted text-lg max-w-2xl mb-4">{description}</p>
        )}
        <p className="text-muted mb-4">
          {count} {t("megaTrendTrends")}
        </p>
        <div className="flex flex-wrap gap-2 mb-4">
          {verticals.map((v) => {
            const vInfo = getVerticalInfo(v as Vertical);
            return (
              <Link
                key={v}
                href={`/trends?vertical=${v}`}
                className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-full border border-border hover:border-accent/30 transition-colors"
                style={{ color: vInfo.color }}
              >
                {vInfo.icon} {vInfo.label}
              </Link>
            );
          })}
        </div>
        <div className="rounded-lg bg-card border border-accent/20 p-4">
          <p className="text-sm text-accent/80">{t("megaTrendCta")}</p>
        </div>
      </div>
    </>
  );
}
