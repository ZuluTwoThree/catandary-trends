"use client";

import { useEffect } from "react";
import Link from "next/link";
import type { Trend } from "@/lib/types";
import { getVerticalInfo, getMegaTrendInfo } from "@/lib/types";
import PestelBadge from "./PestelBadge";
import VerticalBadge from "./VerticalBadge";
import TrendScore from "./TrendScore";
import ForesightCta from "./ForesightCta";

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
}: {
  trend: Trend;
  related: Trend[];
}) {
  const vertical = getVerticalInfo(trend.primary_vertical);

  useEffect(() => {
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
      <nav className="flex items-center gap-3 font-mono text-[10px] uppercase tracking-[0.14em] text-muted mb-8">
        <Link href="/trends" className="hover:text-paper transition-colors">
          Trends
        </Link>
        <span className="text-border">/</span>
        <Link
          href={`/trends?vertical=${trend.primary_vertical}`}
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
        <div className="border-t border-border pt-6 mt-10 grid grid-cols-2 md:grid-cols-4 gap-6">
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
                  Mega Trend
                </dt>
                <dd className="text-sm">
                  <Link
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
        </div>

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

        {/* Source Link */}
        {trend.source_url && (
          <div className="mt-10 border border-border p-5">
            <div className="font-mono text-[9px] uppercase tracking-[0.18em] text-muted mb-2">
              Original Source
            </div>
            <a
              href={trend.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-accent hover:underline font-sans text-sm break-all"
            >
              {trend.source_name || trend.source_url}
            </a>
          </div>
        )}
      </article>

      {/* Related Trends */}
      {related.length > 0 && (
        <section className="mt-16">
          <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted mb-4">
            —— Related in {vertical.label}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {related.map((r) => {
              const rv = getVerticalInfo(r.primary_vertical);
              return (
                <Link
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
