"use client";

import Link from "next/link";
import type { Trend } from "@/lib/types";
import { getVerticalInfo } from "@/lib/types";
import { useLocale } from "@/lib/locale-context";
import { translations, type TranslationKey } from "@/lib/i18n";
import PestelBadge from "./PestelBadge";
import VerticalBadge from "./VerticalBadge";
import TrendScore from "./TrendScore";
import ForesightCta from "./ForesightCta";

export default function TrendArticle({
  trend,
  related,
}: {
  trend: Trend;
  related: Trend[];
}) {
  const { locale, t } = useLocale();
  const vertical = getVerticalInfo(trend.primary_vertical);

  const title =
    locale === "de" ? trend.title_de || trend.title_en : trend.title_en;
  const summary =
    locale === "de" ? trend.summary_de || trend.summary_en : trend.summary_en;
  const body = locale === "de" ? trend.body_de || trend.body_en : trend.body_en;

  const date = trend.published_at || trend.created_at;
  const formattedDate = date
    ? new Date(date).toLocaleDateString(locale === "de" ? "de-DE" : "en-US", {
        day: "numeric",
        month: "long",
        year: "numeric",
      })
    : null;

  const signalTypeKey = trend.trend_signal_type as TranslationKey | undefined;
  const signalTypeLabel =
    signalTypeKey && signalTypeKey in translations[locale]
      ? t(signalTypeKey)
      : trend.trend_signal_type?.replace("_", " ") ?? null;

  return (
    <>
      {/* Breadcrumb */}
      <nav className="flex items-center gap-2 text-sm text-muted mb-6">
        <Link
          href="/trends"
          className="hover:text-foreground transition-colors"
        >
          {t("trends")}
        </Link>
        <span>/</span>
        <Link
          href={`/trends?vertical=${trend.primary_vertical}`}
          className="hover:text-foreground transition-colors"
          style={{ color: vertical.color }}
        >
          {vertical.icon} {vertical.label}
        </Link>
        <span>/</span>
        <span className="text-foreground truncate max-w-xs">{title}</span>
      </nav>

      <article>
        {/* Header */}
        <header className="mb-8">
          <div className="flex flex-wrap items-center gap-2 mb-4">
            <VerticalBadge vertical={trend.primary_vertical} size="md" />
            {trend.verticals
              .filter((v) => v !== trend.primary_vertical)
              .map((v) => (
                <VerticalBadge key={v} vertical={v} />
              ))}
          </div>

          <h1 className="text-3xl md:text-4xl font-bold tracking-tight leading-tight mb-4">
            {title}
          </h1>

          <div className="flex flex-wrap items-center gap-4 text-sm text-muted">
            {formattedDate && <time>{formattedDate}</time>}
            {trend.source_name && (
              <>
                <span>|</span>
                <span>
                  {t("source")}: {trend.source_name}
                </span>
              </>
            )}
            <TrendScore score={trend.trend_score} />
          </div>
        </header>

        {/* PESTEL */}
        <div className="flex flex-wrap gap-2 mb-6">
          {trend.pestel.map((p) => (
            <PestelBadge key={p} dimension={p} />
          ))}
        </div>

        {/* Summary */}
        {summary && (
          <div className="rounded-lg bg-card border border-border p-4 mb-8">
            <p className="text-foreground leading-relaxed font-medium">
              {summary}
            </p>
          </div>
        )}

        {/* Body */}
        {body && (
          <div className="prose prose-invert max-w-none mb-8">
            <div className="text-foreground/90 leading-relaxed whitespace-pre-line">
              {body}
            </div>
          </div>
        )}

        {/* Meta info */}
        <div className="border-t border-border pt-6 mt-8 grid grid-cols-2 md:grid-cols-4 gap-4">
          {trend.trend_signal_type && (
            <div>
              <dt className="text-xs text-muted mb-1">{t("signalType")}</dt>
              <dd className="text-sm capitalize">{signalTypeLabel}</dd>
            </div>
          )}
          {trend.mega_trend && (
            <div>
              <dt className="text-xs text-muted mb-1">{t("megaTrend")}</dt>
              <dd className="text-sm">{trend.mega_trend}</dd>
            </div>
          )}
          {trend.brands.length > 0 && (
            <div>
              <dt className="text-xs text-muted mb-1">{t("brands")}</dt>
              <dd className="text-sm">{trend.brands.join(", ")}</dd>
            </div>
          )}
          {trend.regions.length > 0 && (
            <div>
              <dt className="text-xs text-muted mb-1">{t("regions")}</dt>
              <dd className="text-sm">{trend.regions.join(", ")}</dd>
            </div>
          )}
        </div>

        {/* Tags */}
        {trend.tags.length > 0 && (
          <div className="mt-6 flex flex-wrap gap-2">
            {trend.tags.map((tag) => (
              <span
                key={tag}
                className="text-xs bg-card border border-border px-2.5 py-1 rounded-full text-muted"
              >
                #{tag}
              </span>
            ))}
          </div>
        )}

        {/* Source Link */}
        {trend.source_url && (
          <div className="mt-8 p-4 rounded-lg bg-card border border-border">
            <p className="text-sm text-muted">
              {t("originalSource")}:{" "}
              <a
                href={trend.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-accent hover:underline"
              >
                {trend.source_name || trend.source_url}
              </a>
            </p>
          </div>
        )}
      </article>

      {/* Related Trends */}
      {related.length > 0 && (
        <section className="mt-12">
          <h2 className="text-xl font-semibold mb-4">
            {t("relatedTrends")} {vertical.label}
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {related.map((r) => {
              const rTitle =
                locale === "de"
                  ? r.title_de || r.title_en
                  : r.title_en;
              const rSummary =
                locale === "de"
                  ? r.summary_de || r.summary_en
                  : r.summary_en;
              return (
                <Link
                  key={r.id}
                  href={`/trends/${r.slug}`}
                  className="rounded-lg border border-border bg-card p-4 hover:bg-card-hover hover:border-accent/30 transition-all"
                >
                  <h3 className="text-sm font-medium leading-snug line-clamp-2 mb-2">
                    {rTitle}
                  </h3>
                  <p className="text-xs text-muted line-clamp-2">{rSummary}</p>
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
