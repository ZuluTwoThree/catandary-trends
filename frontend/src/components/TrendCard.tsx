"use client";

import Link from "next/link";
import type { Trend } from "@/lib/types";
import { getVerticalInfo } from "@/lib/types";
import { useLocale } from "@/lib/locale-context";
import PestelBadge from "./PestelBadge";
import TrendScore from "./TrendScore";

export default function TrendCard({ trend }: { trend: Trend }) {
  const { locale, mounted, t } = useLocale();
  const vertical = getVerticalInfo(trend.primary_vertical);

  // Always use "de" before mount to match server render
  const effectiveLocale = mounted ? locale : "de";

  const title =
    effectiveLocale === "de"
      ? trend.title_de || trend.title_en
      : trend.title_en;
  const summary =
    effectiveLocale === "de"
      ? trend.summary_de || trend.summary_en
      : trend.summary_en;

  const date = trend.source_date || trend.published_at || trend.created_at;
  const formattedDate = mounted && date
    ? new Date(date).toLocaleDateString(effectiveLocale === "de" ? "de-DE" : "en-US", {
        day: "numeric",
        month: "short",
        year: "numeric",
      })
    : null;

  return (
    <Link href={`/trends/${trend.slug}`}>
      <article className="group rounded-xl border border-border bg-card p-5 hover:bg-card-hover hover:border-accent/30 transition-all duration-200 h-full flex flex-col">
        {/* Header: Vertical + Date */}
        <div className="flex items-center justify-between mb-3">
          <span
            className="inline-flex items-center gap-1 text-xs font-medium"
            style={{ color: vertical.color }}
          >
            <span>{vertical.icon}</span>
            <span>{vertical.label}</span>
          </span>
          {formattedDate && (
            <time className="text-xs text-muted">{formattedDate}</time>
          )}
        </div>

        {/* Title */}
        <h3 className="text-base font-semibold leading-snug mb-2 group-hover:text-accent transition-colors line-clamp-2">
          {title}
        </h3>

        {/* Summary */}
        <p className="text-sm text-muted leading-relaxed mb-4 line-clamp-3 flex-grow">
          {summary}
        </p>

        {/* Footer */}
        <div className="flex flex-col gap-2 mt-auto">
          {trend.pestel.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {trend.pestel.map((p) => (
                <PestelBadge key={p} dimension={p} />
              ))}
            </div>
          )}

          <div className="flex items-center justify-between">
            <TrendScore score={trend.trend_score} />
            <span className="text-xs text-muted truncate ml-2">
              {(() => {
                const icon =
                  trend.source_type === "trade_media" ? "📰" :
                  trend.source_type === "press_wire" ? "📋" :
                  trend.source_type === "radar" ? "📡" :
                  trend.trend_signal_type === "research" ? "🔬" :
                  trend.source_type === "brand" ? "🏷" :
                  trend.source_type === "api" ? "📊" : "📰";
                const labelKey =
                  trend.source_type === "trade_media" ? "sourceType_trade_media" :
                  trend.source_type === "press_wire" ? "sourceType_press_wire" :
                  trend.source_type === "radar" ? "sourceType_radar" :
                  trend.trend_signal_type === "research" ? "sourceType_research" :
                  trend.source_type === "brand" ? "sourceType_brand" :
                  trend.source_type === "api" ? "sourceType_api" :
                  "sourceType_trade_media";
                return `${icon} ${t(labelKey as any)}`;
              })()}
            </span>
          </div>

          {trend.verticals.length > 1 && (
            <div className="flex items-center gap-1 text-xs text-accent/70">
              <span>{t("crossIndustry")}:</span>
              {trend.verticals
                .filter((v) => v !== trend.primary_vertical)
                .map((v) => {
                  const vi = getVerticalInfo(v);
                  return (
                    <span key={v} title={vi.label}>
                      {vi.icon}
                    </span>
                  );
                })}
            </div>
          )}
        </div>
      </article>
    </Link>
  );
}
