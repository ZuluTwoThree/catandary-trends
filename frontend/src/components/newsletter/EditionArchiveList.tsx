import Link from "next/link";
import { linkPrefetch } from "@/lib/renderMode";
import {
  editionPath,
  isoWeekMondayIso,
  isoWeekRangeLabel,
  type EditionSummary,
} from "@/lib/newsletterEditions";

/**
 * The static briefing archive: one link per edition, newest first
 * (PUBLIC_NEWSLETTER_EDITIONS of them). Plain links — works without JS,
 * is crawlable, and every row is a real file in the export.
 */
export default function EditionArchiveList({
  editions,
  current,
}: {
  editions: EditionSummary[];
  current?: { year: number; week: number } | null;
}) {
  if (editions.length === 0) return null;
  return (
    <div className="border border-border bg-card/40">
      {editions.map((e, i) => {
        const isActive = current?.year === e.year && current?.week === e.week;
        return (
          <Link
            key={`${e.year}-${e.week}`}
            prefetch={linkPrefetch()}
            href={editionPath(e.year, e.week)}
            aria-current={isActive ? "page" : undefined}
            className={`flex flex-wrap items-center justify-between gap-x-4 gap-y-1 px-5 py-3 font-mono text-[10px] uppercase tracking-[0.14em] transition-colors ${
              i < editions.length - 1 ? "border-b border-dashed border-border" : ""
            } ${isActive ? "text-accent bg-accent/5" : "text-muted hover:text-paper hover:bg-card"}`}
          >
            <span>
              {isActive && "→ "}Trend Briefing · Week {e.week}/{e.year}
            </span>
            <span className="inline-flex items-center gap-4">
              <time dateTime={isoWeekMondayIso(e.year, e.week)} className="normal-case tracking-normal">
                {isoWeekRangeLabel(e.year, e.week)}
              </time>
              <span>{e.total_signals} signals</span>
            </span>
          </Link>
        );
      })}
    </div>
  );
}
