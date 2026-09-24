"use client";

import Link from "next/link";
import { linkPrefetch } from "@/lib/renderMode";
import type { Trend } from "@/lib/types";
import { getVerticalInfo } from "@/lib/types";
import PestelBadge from "./PestelBadge";
import TrendScore from "./TrendScore";
import { SIGNAL_TYPE_LABELS } from "@/lib/filter-params";

const SOURCE_TYPE_LABELS: Record<string, string> = {
  trade_media: "Trade",
  press_wire: "Press",
  radar: "Radar",
  research: "Research",
  brand: "Brand",
  api: "Data",
};

export default function TrendCard({ trend }: { trend: Trend }) {
  const vertical = getVerticalInfo(trend.primary_vertical);
  const title = trend.title_en;
  const summary = trend.summary_en;

  const date = trend.source_date || trend.published_at || trend.created_at;
  const formattedDate = date
    ? new Date(date).toLocaleDateString("en-GB", {
        day: "2-digit",
        month: "short",
        year: "numeric",
      }).toUpperCase()
    : null;

  const sourceLabel =
    SOURCE_TYPE_LABELS[
      trend.trend_signal_type === "research"
        ? "research"
        : trend.source_type ?? "trade_media"
    ] ?? "Trade";

  // Signal type (#110) next to the source — omitted when it would only repeat
  // the source label ("Research / Research").
  const signalLabel = SIGNAL_TYPE_LABELS[trend.trend_signal_type] ?? null;
  const showSignal = !!signalLabel && signalLabel !== sourceLabel;

  return (
    <Link prefetch={linkPrefetch()} href={`/trends/${trend.slug}`} className="block h-full">
      <article
        className="brackets group h-full flex flex-col border border-border border-l-[3px] bg-transparent hover:bg-accent/[0.02] transition-colors px-6 py-7"
        style={{ borderLeftColor: vertical.color }}
      >
        {/* Header: Vertical code + Date */}
        <div className="flex items-center justify-between mb-4">
          <span className="flex items-center gap-2 font-mono text-[9px] uppercase tracking-[0.15em]">
            <span
              className="inline-block w-2 h-[3px]"
              style={{ backgroundColor: vertical.color }}
              aria-hidden="true"
            />
            <span style={{ color: vertical.color }}>{vertical.code}</span>
          </span>
          {formattedDate && (
            <time className="font-mono text-[10px] text-muted tracking-wider">
              {formattedDate}
            </time>
          )}
        </div>

        {/* Title */}
        <h3 className="font-display text-[19px] leading-[1.3] tracking-[-0.01em] text-paper mb-3 line-clamp-3 group-hover:text-accent transition-colors">
          {title}
        </h3>

        {/* Summary */}
        <p className="text-[13px] leading-[1.55] text-muted line-clamp-3 mb-4 flex-grow">
          {summary}
        </p>

        {/* PESTEL row */}
        {trend.pestel.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mb-3">
            {trend.pestel.map((p) => (
              <PestelBadge key={p} dimension={p} />
            ))}
          </div>
        )}

        {/* Footer — dashed rule, source + CRS bar */}
        <div className="flex items-center justify-between pt-3 border-t border-dashed border-border">
          <span className="font-mono text-[10px] uppercase tracking-wider text-muted">
            {showSignal ? (
              <span className="text-paper/80">{signalLabel} · </span>
            ) : null}
            {sourceLabel}
            {trend.source_name ? (
              <span className="text-muted"> / {trend.source_name}</span>
            ) : null}
          </span>
          <TrendScore score={trend.trend_score} />
        </div>

        {/* Cross-industry row (optional) */}
        {trend.verticals.length > 1 && (
          <div className="mt-2 flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-[0.12em] text-muted">
            <span className="opacity-70">Cross:</span>
            {trend.verticals
              .filter((v) => v !== trend.primary_vertical)
              .map((v) => {
                const vi = getVerticalInfo(v);
                return (
                  <span
                    key={v}
                    title={vi.label}
                    style={{ color: vi.color }}
                  >
                    {vi.code}
                  </span>
                );
              })}
          </div>
        )}
      </article>
    </Link>
  );
}
