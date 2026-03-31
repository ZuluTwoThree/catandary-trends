import Link from "next/link";
import type { Trend } from "@/lib/types";
import { getVerticalInfo } from "@/lib/types";
import PestelBadge from "./PestelBadge";
import TrendScore from "./TrendScore";

export default function TrendCard({ trend }: { trend: Trend }) {
  const vertical = getVerticalInfo(trend.primary_vertical);
  const date = trend.published_at || trend.created_at;
  const formattedDate = date
    ? new Date(date).toLocaleDateString("de-DE", {
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
          {trend.title_de || trend.title_en}
        </h3>

        {/* Summary */}
        <p className="text-sm text-muted leading-relaxed mb-4 line-clamp-3 flex-grow">
          {trend.summary_de || trend.summary_en}
        </p>

        {/* Footer */}
        <div className="flex flex-col gap-2 mt-auto">
          {/* PESTEL Badges */}
          {trend.pestel.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {trend.pestel.map((p) => (
                <PestelBadge key={p} dimension={p} />
              ))}
            </div>
          )}

          {/* Score + Signal Type + Source */}
          <div className="flex items-center justify-between">
            <TrendScore score={trend.trend_score} />
            <span className="text-xs text-muted truncate ml-2">
              {trend.source_name}
            </span>
          </div>

          {/* Cross-vertical indicator */}
          {trend.verticals.length > 1 && (
            <div className="flex items-center gap-1 text-xs text-accent/70">
              <span>Cross-Industry:</span>
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
