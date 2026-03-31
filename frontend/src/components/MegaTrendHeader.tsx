"use client";

import Link from "next/link";
import { useLocale } from "@/lib/locale-context";
import { getVerticalInfo } from "@/lib/types";
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
  const { t } = useLocale();

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
        <span className="text-foreground">{megaTrend}</span>
      </nav>

      <div className="mb-8">
        <h1 className="text-3xl md:text-4xl font-bold tracking-tight mb-3">
          {megaTrend}
        </h1>
        <p className="text-muted mb-4">
          {count} {t("megaTrendTrends")}
        </p>
        <div className="flex flex-wrap gap-2 mb-4">
          {verticals.map((v) => {
            const info = getVerticalInfo(v as Vertical);
            return (
              <Link
                key={v}
                href={`/trends?vertical=${v}`}
                className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-full border border-border hover:border-accent/30 transition-colors"
                style={{ color: info.color }}
              >
                {info.icon} {info.label}
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
