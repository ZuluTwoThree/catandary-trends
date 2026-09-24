"use client";

import { useEffect } from "react";
import Link from "next/link";
import { linkPrefetch } from "@/lib/renderMode";
import type { Trend, Vertical } from "@/lib/types";
import { verticalFeedHref } from "@/lib/staticListing";
import type { TrendTechMatch } from "@/lib/technology";
import { getVerticalInfo, getMegaTrendInfo } from "@/lib/types";
import { archiveUrl, DEAD_SOURCE_NOTICE } from "@/lib/deadLinks";
import { safeHref } from "@/lib/safeHref";
import { sourceLicenseNotice } from "@/lib/sourceLicense";
import { isStaticExport } from "@/lib/renderMode";
import AiArticleDisclosure from "./AiArticleDisclosure";
import PestelBadge from "./PestelBadge";
import VerticalBadge from "./VerticalBadge";
import TrendScore from "./TrendScore";
import ForesightCta from "./ForesightCta";
import TechContext from "./TechContext";

const SIGNAL_TYPE_LABELS: Record<string, string> = {
  product_launch: "Product Launch",
  research: "Research",
  market_shift: "Market Shift",
  consumer_behavior: "Consumer Behavior",
  regulation: "Regulation",
  funding: "Funding",
  partnership: "Partnership",
  patent: "Patent",
};

export default function TrendArticle({
  trend,
  related,
  tech = [],
  sourceDead = false,
  story = [],
}: {
  trend: Trend;
  related: Trend[];
  /** #109: the other reports of the same story (oldest first), or empty. */
  story?: Trend[];
  tech?: TrendTechMatch[];
  /** #48: true once check_source_links.py --mark has confirmed (2 strikes)
   *  the source_url is gone. Missing dead_links table degrades to false. */
  sourceDead?: boolean;
}) {
  const vertical = getVerticalInfo(trend.primary_vertical);
  // Feed-sourced URL: only http(s) becomes a link (F-3); anything else is
  // shown as text so the attribution stays visible but inert.
  const sourceHref = safeHref(trend.source_url);
  const licenseNotice = sourceLicenseNotice(trend.source_name);

  useEffect(() => {
    // No API on the static hosting (design 4.3): the page-view ping would
    // only be a 404 in every visitor's console. Server logs cover it there.
    if (isStaticExport()) return;
    fetch("/api/track", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ trend_id: trend.id, event: "page_view" }),
    }).catch(() => {});
  }, [trend.id]);

  const title = trend.title_en;
  const summary = trend.summary_en;
  const body = trend.body_en;

  const date = trend.source_date || trend.published_at || trend.created_at;
  const formattedDate = date
    ? new Date(date).toLocaleDateString("en-US", {
        day: "numeric",
        month: "long",
        year: "numeric",
      })
    : null;

  const signalTypeLabel =
    SIGNAL_TYPE_LABELS[trend.trend_signal_type] ??
    trend.trend_signal_type?.replace("_", " ") ??
    null;

  return (
    <>
      {/* Breadcrumb */}
      <nav
        aria-label="Breadcrumb"
        className="flex items-center gap-3 font-mono text-[10px] uppercase tracking-[0.14em] text-muted mb-8"
      >
        <Link prefetch={linkPrefetch()} href="/trends" className="hover:text-paper transition-colors">
          Trends
        </Link>
        <span className="text-border">/</span>
        <Link
          prefetch={linkPrefetch()}
          href={verticalFeedHref(trend.primary_vertical as Vertical)}
          className="inline-flex items-center gap-2 transition-colors hover:opacity-80"
          style={{ color: vertical.color }}
        >
          <span
            className="inline-block w-2 h-[3px]"
            style={{ backgroundColor: vertical.color }}
            aria-hidden="true"
          />
          <span>{vertical.code}</span>
        </Link>
        <span className="text-border">/</span>
        <span className="text-paper truncate max-w-xs normal-case tracking-normal font-sans">
          {title}
        </span>
      </nav>

      <article>
        {/* Header */}
        <header className="mb-10">
          <div className="flex flex-wrap items-center gap-2 mb-6">
            <VerticalBadge vertical={trend.primary_vertical} size="md" />
            {trend.verticals
              .filter((v) => v !== trend.primary_vertical)
              .map((v) => (
                <VerticalBadge key={v} vertical={v} />
              ))}
          </div>

          <h1 className="font-display text-4xl md:text-[44px] leading-[1.1] tracking-tight text-paper mb-6">
            {title}
          </h1>

          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 font-mono text-[10px] uppercase tracking-[0.14em] text-muted pt-4 border-t border-border">
            {formattedDate && <time>{formattedDate}</time>}
            {trend.source_name && (
              <>
                <span className="text-border">——</span>
                <span>
                  <span className="text-muted/70">Source /</span>{" "}
                  <span className="text-paper">{trend.source_name}</span>
                </span>
              </>
            )}
            <span className="ml-auto">
              <TrendScore score={trend.trend_score} />
            </span>
          </div>
        </header>

        {/* AI label (#99, EU AI Act Art. 50 (4)) — directly under the title
            block, because these articles reach the reader through automatic
            gates only. Not in the footer: the label has to be there at first
            sight. Wording + reasoning in lib/aiDisclosure.ts. */}
        <AiArticleDisclosure />

        {/* PESTEL */}
        {trend.pestel.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-8">
            {trend.pestel.map((p) => (
              <PestelBadge key={p} dimension={p} />
            ))}
          </div>
        )}

        {/* Summary */}
        {summary && (
          <div className="border-l-[3px] pl-5 py-1 mb-10" style={{ borderColor: vertical.color }}>
            <p className="font-display text-xl md:text-[22px] leading-[1.45] text-paper italic">
              {summary}
            </p>
          </div>
        )}

        {/* Body */}
        {body && (
          <div className="max-w-none mb-10">
            <div className="text-text leading-[1.75] whitespace-pre-line text-[15px] font-sans">
              {body}
            </div>
          </div>
        )}

        {/* Meta info */}
        <dl className="border-t border-border pt-6 mt-10 grid grid-cols-2 md:grid-cols-4 gap-6">
          {trend.trend_signal_type && (
            <div>
              <dt className="font-mono text-[9px] uppercase tracking-[0.18em] text-muted mb-2">
                Signal Type
              </dt>
              <dd className="text-sm text-paper">{signalTypeLabel}</dd>
            </div>
          )}
          {trend.mega_trend && (() => {
            const mtInfo = getMegaTrendInfo(trend.mega_trend);
            const mtName = mtInfo ? mtInfo.name_en : trend.mega_trend;
            return (
              <div>
                <dt className="font-mono text-[9px] uppercase tracking-[0.18em] text-muted mb-2">
                  Signal Theme
                </dt>
                <dd className="text-sm">
                  <Link
                    prefetch={linkPrefetch()}
                    href={`/trends/mega/${encodeURIComponent(trend.mega_trend.replace(/_/g, "-"))}`}
                    className="text-accent hover:underline"
                  >
                    {mtName}
                  </Link>
                </dd>
              </div>
            );
          })()}
          {trend.brands.length > 0 && (
            <div>
              <dt className="font-mono text-[9px] uppercase tracking-[0.18em] text-muted mb-2">
                Brands
              </dt>
              <dd className="text-sm text-paper">{trend.brands.join(", ")}</dd>
            </div>
          )}
          {trend.regions.length > 0 && (
            <div>
              <dt className="font-mono text-[9px] uppercase tracking-[0.18em] text-muted mb-2">
                Regions
              </dt>
              <dd className="text-sm text-paper">{trend.regions.join(", ")}</dd>
            </div>
          )}
        </dl>

        {/* Tags */}
        {trend.tags.length > 0 && (
          <div className="mt-8 flex flex-wrap gap-2">
            {trend.tags.map((tag) => (
              <span
                key={tag}
                className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted border border-border px-2 py-1"
              >
                #{tag}
              </span>
            ))}
          </div>
        )}

        {/* Technology context (#28) — plain-language bridge into the Foresight backbone */}
        <TechContext matches={tech} />

        {/* Source Link */}
        {trend.source_url && (
          <div className="mt-10 border border-border p-5">
            <h2 className="font-mono text-[9px] uppercase tracking-[0.18em] text-muted mb-2">
              Original Source
            </h2>
            {sourceHref ? (
              <a
                href={sourceHref}
                target="_blank"
                rel="noopener noreferrer"
                className="text-accent hover:underline font-sans text-sm break-all"
              >
                {trend.source_name || trend.source_url}
              </a>
            ) : (
              <span className="font-sans text-sm break-all">
                {trend.source_name || trend.source_url}
              </span>
            )}
            {licenseNotice && (
              <p className="mt-3 text-xs text-muted leading-relaxed" data-testid="source-license">
                {licenseNotice.text}{" "}
                <a
                  href={licenseNotice.licenseUrl}
                  target="_blank"
                  rel="noopener noreferrer license"
                  className="text-accent hover:underline"
                >
                  {licenseNotice.licenseName}
                </a>
              </p>
            )}
            {sourceDead && sourceHref && (
              <p className="mt-3 text-xs text-muted leading-relaxed">
                {DEAD_SOURCE_NOTICE}.{" "}
                <a
                  href={archiveUrl(sourceHref)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-accent hover:underline"
                >
                  View archived copy
                </a>
              </p>
            )}
          </div>
        )}
      </article>

      {/* Same story, other outlets (#109) — the oldest report leads */}
      {story.length > 0 && (
        <section className="mt-12" aria-labelledby="story-heading">
          <h2 id="story-heading" className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted mb-3">
            <span aria-hidden="true">—— </span>Also reported by
          </h2>
          <ul className="border-t border-dashed border-border divide-y divide-dashed divide-border">
            {story.map((r) => {
              const first =
                !!r.sort_date && !!trend.sort_date && r.sort_date < trend.sort_date && r.id === story[0].id;
              return (
                <li key={r.id} className="py-2.5 flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  <span className="font-mono text-[10px] uppercase tracking-wider text-muted shrink-0">
                    {r.source_name ?? "Source"}
                    {first ? <span className="text-accent"> · first report</span> : null}
                  </span>
                  <Link
                    prefetch={linkPrefetch()}
                    href={`/trends/${r.slug}`}
                    className="font-display text-[15px] leading-snug text-paper hover:text-accent transition-colors"
                  >
                    {r.title_en}
                  </Link>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {/* Related Trends */}
      {related.length > 0 && (
        <section className="mt-16">
          <h2 className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted mb-4">
            <span aria-hidden="true">—— </span>Related in {vertical.label}
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {related.map((r) => {
              const rv = getVerticalInfo(r.primary_vertical);
              return (
                <Link
                  prefetch={linkPrefetch()}
                  key={r.id}
                  href={`/trends/${r.slug}`}
                  className="border border-border border-l-[3px] bg-card/40 p-4 hover:bg-card transition-colors"
                  style={{ borderLeftColor: rv.color }}
                >
                  <div className="font-mono text-[9px] uppercase tracking-[0.18em] mb-2" style={{ color: rv.color }}>
                    {rv.code}
                  </div>
                  <h3 className="font-display text-[17px] leading-snug line-clamp-2 mb-2 text-paper">
                    {r.title_en}
                  </h3>
                  <p className="text-xs text-muted line-clamp-2 font-sans">
                    {r.summary_en}
                  </p>
                </Link>
              );
            })}
          </div>
        </section>
      )}

      <ForesightCta compact />
    </>
  );
}
