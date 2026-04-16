import Link from "next/link";
import type { Trend } from "@/lib/types";
import { getVerticalInfo } from "@/lib/types";

/**
 * Dense-row alternative to `TrendCard`. Optimised for scanning many signals
 * quickly — 3 columns: [Vertical + Title] / [Meta] / [Score bar]. Shares the
 * editorial language (sharp corners, mono meta, 3px vertical-color bar).
 */
export default function TrendRow({ trend }: { trend: Trend }) {
  const vertical = getVerticalInfo(trend.primary_vertical);
  const date = trend.source_date || trend.published_at || trend.created_at;
  const formattedDate = date
    ? new Date(date)
        .toLocaleDateString("en-GB", {
          day: "2-digit",
          month: "short",
          year: "2-digit",
        })
        .toUpperCase()
    : null;

  const scorePct =
    trend.trend_score != null ? Math.round(trend.trend_score * 100) : null;

  return (
    <Link
      href={`/trends/${trend.slug}`}
      className="group block border-b border-border last:border-b-0 hover:bg-accent/[0.02] transition-colors"
    >
      <article className="relative grid grid-cols-12 gap-4 items-center py-3 pl-5 pr-4">
        {/* 3px vertical-color stripe */}
        <span
          className="absolute left-0 top-0 bottom-0 w-[3px]"
          style={{ backgroundColor: vertical.color }}
          aria-hidden="true"
        />

        {/* Vertical code — col 1 */}
        <span
          className="col-span-2 sm:col-span-1 font-mono text-[10px] uppercase tracking-[0.15em] tabular-nums"
          style={{ color: vertical.color }}
        >
          {vertical.code}
        </span>

        {/* Title — col 2 */}
        <h3 className="col-span-10 sm:col-span-6 font-sans text-[14px] leading-[1.4] text-paper group-hover:text-accent transition-colors truncate">
          {trend.title_en}
        </h3>

        {/* Date — col 3 */}
        <span className="hidden sm:block col-span-2 font-mono text-[10px] uppercase tracking-[0.1em] text-muted tabular-nums">
          {formattedDate ?? "—"}
        </span>

        {/* PESTEL letters — col 4 */}
        <span className="hidden md:flex col-span-1 items-center gap-1 font-mono text-[10px] text-muted">
          {trend.pestel.slice(0, 3).map((p) => (
            <span key={p} className="opacity-70">
              {p}
            </span>
          ))}
        </span>

        {/* Score bar — col 5 */}
        <div className="col-span-12 sm:col-span-3 md:col-span-2 flex items-center gap-2">
          <div className="flex-1 h-[3px] bg-border relative overflow-hidden">
            {scorePct != null && (
              <span
                className="absolute inset-y-0 left-0 bg-accent"
                style={{ width: `${scorePct}%` }}
              />
            )}
          </div>
          <span className="font-mono text-[10px] tabular-nums text-muted w-7 text-right">
            {scorePct != null ? scorePct : "—"}
          </span>
        </div>
      </article>
    </Link>
  );
}
