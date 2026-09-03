import Link from "next/link";
import { getVerticalInfo, type Vertical } from "@/lib/types";
import { safeHref } from "@/lib/safeHref";
import { linkPrefetch } from "@/lib/renderMode";
import type { NewsletterEdition, TrendRef } from "@/lib/newsletterEditions";

/**
 * The body of one weekly briefing — editorial, vertical signals, signal-theme
 * radar. No hooks, so it renders in the workstation's client page
 * (NewsletterClient.tsx, data from /api/newsletter) and in the static
 * export's server pages (data from lib/db.ts, links pre-resolved by
 * lib/newsletterEditions.ts rewriteEditionForExport) alike.
 */

const VERTICAL_ORDER = ["TECH", "BIZ", "FOOD", "HEALTH", "ECO", "LIFESTYLE", "FASHION", "DESIGN"];

const MOMENTUM_GLYPHS: Record<string, string> = {
  rising: "↑",
  emerging: "↑↑",
  declining: "↓",
  stable: "→",
};

function isExternal(href: string): boolean {
  return /^https?:\/\//i.test(href);
}

/** Render text that may contain markdown links [text](url) as clickable elements. */
export function RichText({ text, className }: { text: string; className?: string }) {
  const parts = text.split(/(\[[^\]]+\]\([^)]+\))/g);
  const linkPattern = /^\[([^\]]+)\]\(([^)]+)\)$/;

  return (
    <span className={className}>
      {parts.map((part, i) => {
        const match = linkPattern.exec(part);
        if (match) {
          // Generated edition text: only http(s)/relative targets become links (F-3).
          const href = safeHref(match[2]);
          if (!href) return <span key={i}>{match[1]}</span>;
          if (isExternal(href)) {
            return (
              <a
                key={i}
                href={href}
                rel="noopener noreferrer"
                className="text-accent hover:underline transition-colors"
              >
                {match[1]}
              </a>
            );
          }
          return (
            <Link
              key={i}
              prefetch={linkPrefetch()}
              href={href}
              className="text-accent hover:underline transition-colors"
            >
              {match[1]}
            </Link>
          );
        }
        return <span key={i}>{part}</span>;
      })}
    </span>
  );
}

const REF_CLASS =
  "block font-mono text-[10px] uppercase tracking-[0.12em] text-accent hover:underline transition-colors";

/** A cited signal: internal link, source link, or — nowhere to link — text. */
function TrendRefLine({ item }: { item: TrendRef }) {
  // `href` undefined = the workstation default; the export resolves it.
  const href = item.href === undefined ? `/trends/${item.slug}` : item.href;
  if (href === null) {
    return (
      <span className="block font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
        → {item.title}
        {item.source_name ? <span className="text-muted/70"> · {item.source_name}</span> : null}
      </span>
    );
  }
  if (isExternal(href)) {
    return (
      <a href={href} rel="noopener noreferrer" className={REF_CLASS}>
        → {item.title}
        {item.source_name ? <span className="text-muted"> · {item.source_name} ↗</span> : null}
      </a>
    );
  }
  return (
    <Link prefetch={linkPrefetch()} href={href} className={REF_CLASS}>
      → {item.title}
    </Link>
  );
}

export default function EditionBody({ edition }: { edition: NewsletterEdition }) {
  return (
    <>
      {/* Editorial */}
      <section className="mb-12">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted mb-4">
          01 — Weekly Overview
        </div>
        <div className="border-l-[3px] border-accent pl-6 py-1">
          {edition.editorial?.split("\n\n").map((para, i) => (
            <p key={i} className="font-sans text-text leading-[1.75] mb-4 last:mb-0">
              <RichText text={para.trim()} />
            </p>
          ))}
        </div>
      </section>

      {/* Vertical summaries */}
      <section className="mb-12 space-y-3">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted mb-4">
          02 — Vertical Signals
        </div>
        {VERTICAL_ORDER.map((v) => {
          const summary = edition.vertical_summaries?.[v];
          if (!summary) return null;
          const info = getVerticalInfo(v as Vertical);
          const trends = edition.trend_refs?.[v] || [];

          return (
            <div
              key={v}
              className="border border-border border-l-[3px] bg-card/40"
              style={{ borderLeftColor: info.color }}
            >
              {/* Vertical header */}
              <div className="px-5 py-3 border-b border-dashed border-border flex items-center justify-between">
                <span className="inline-flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.14em]">
                  <span
                    className="inline-block w-2 h-[3px]"
                    style={{ backgroundColor: info.color }}
                    aria-hidden="true"
                  />
                  <span style={{ color: info.color }}>{info.code}</span>
                  <span className="text-muted/80 font-sans normal-case tracking-normal">
                    {info.label}
                  </span>
                </span>
                {trends.length > 0 && (
                  <span className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted">
                    {trends.length} signals
                  </span>
                )}
              </div>

              {/* Summary */}
              <div className="px-5 py-4">
                <p className="font-sans text-text leading-relaxed mb-3">
                  <RichText text={summary} />
                </p>

                {/* Top trend links */}
                {trends.length > 0 && (
                  <div className="space-y-1">
                    {trends.slice(0, 3).map((tr, i) => (
                      <TrendRefLine key={i} item={tr} />
                    ))}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </section>

      {/* Mega-Trend Radar */}
      {edition.mega_trend_radar && edition.mega_trend_radar.length > 0 && (
        <section className="mb-12">
          <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted mb-4">
            03 — Signal Themes Radar
          </div>
          <div className="border border-border bg-card/40 p-5">
            <div className="space-y-3">
              {edition.mega_trend_radar.map((mt) => {
                const glyph = mt.momentum ? MOMENTUM_GLYPHS[mt.momentum] ?? null : null;
                return (
                  <div
                    key={mt.key}
                    className="flex items-center justify-between gap-4 pb-2 border-b border-dashed border-border last:border-b-0 last:pb-0"
                  >
                    <span className="font-sans text-sm text-paper">{mt.name_en}</span>
                    <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted inline-flex items-center gap-2">
                      <span className="text-paper">{mt.signal_count}</span>
                      <span>Signals</span>
                      {glyph && <span className="text-accent">{glyph}</span>}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </section>
      )}
    </>
  );
}
