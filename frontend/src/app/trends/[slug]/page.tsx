import { notFound } from "next/navigation";
import Link from "next/link";
import { getTrendBySlug, getTrends } from "@/lib/db";
import { getVerticalInfo } from "@/lib/types";
import PestelBadge from "@/components/PestelBadge";
import VerticalBadge from "@/components/VerticalBadge";
import TrendScore from "@/components/TrendScore";
import { TrendArticleJsonLd } from "@/components/JsonLd";
import type { Metadata } from "next";

export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const trend = getTrendBySlug(slug);
  if (!trend) return { title: "Trend nicht gefunden" };

  return {
    title: `${trend.title_de || trend.title_en} — Catandary Trends`,
    description: trend.summary_de || trend.summary_en || undefined,
    openGraph: {
      title: trend.title_de || trend.title_en,
      description: trend.summary_de || trend.summary_en || undefined,
      type: "article",
    },
  };
}

export default async function TrendArticlePage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const trend = getTrendBySlug(slug);
  if (!trend) notFound();

  const vertical = getVerticalInfo(trend.primary_vertical);
  const date = trend.published_at || trend.created_at;
  const formattedDate = date
    ? new Date(date).toLocaleDateString("de-DE", {
        day: "numeric",
        month: "long",
        year: "numeric",
      })
    : null;

  // Related trends from same vertical
  const related = getTrends({
    vertical: trend.primary_vertical,
    limit: 4,
  }).filter((t) => t.id !== trend.id).slice(0, 3);

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-2 text-sm text-muted mb-6">
        <Link href="/trends" className="hover:text-foreground transition-colors">
          Trends
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
        <span className="text-foreground truncate max-w-xs">
          {trend.title_de || trend.title_en}
        </span>
      </nav>

      <TrendArticleJsonLd trend={trend} />
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
            {trend.title_de || trend.title_en}
          </h1>

          <div className="flex flex-wrap items-center gap-4 text-sm text-muted">
            {formattedDate && <time>{formattedDate}</time>}
            {trend.source_name && (
              <>
                <span>|</span>
                <span>Quelle: {trend.source_name}</span>
              </>
            )}
            <TrendScore score={trend.trend_score} />
          </div>
        </header>

        {/* PESTEL + Tags */}
        <div className="flex flex-wrap gap-2 mb-6">
          {trend.pestel.map((p) => (
            <PestelBadge key={p} dimension={p} />
          ))}
        </div>

        {/* Summary */}
        {(trend.summary_de || trend.summary_en) && (
          <div className="rounded-lg bg-card border border-border p-4 mb-8">
            <p className="text-foreground leading-relaxed font-medium">
              {trend.summary_de || trend.summary_en}
            </p>
          </div>
        )}

        {/* Body DE */}
        {trend.body_de && (
          <div className="prose prose-invert max-w-none mb-8">
            <div className="flex items-center gap-2 mb-3">
              <span className="text-xs font-medium bg-card border border-border px-2 py-0.5 rounded">
                DE
              </span>
            </div>
            <div className="text-foreground/90 leading-relaxed whitespace-pre-line">
              {trend.body_de}
            </div>
          </div>
        )}

        {/* Body EN */}
        {trend.body_en && (
          <div className="prose prose-invert max-w-none mb-8">
            <div className="flex items-center gap-2 mb-3">
              <span className="text-xs font-medium bg-card border border-border px-2 py-0.5 rounded">
                EN
              </span>
            </div>
            <div className="text-foreground/90 leading-relaxed whitespace-pre-line">
              {trend.body_en}
            </div>
          </div>
        )}

        {/* Meta info */}
        <div className="border-t border-border pt-6 mt-8 grid grid-cols-2 md:grid-cols-4 gap-4">
          {trend.trend_signal_type && (
            <div>
              <dt className="text-xs text-muted mb-1">Signal-Typ</dt>
              <dd className="text-sm capitalize">
                {trend.trend_signal_type.replace("_", " ")}
              </dd>
            </div>
          )}
          {trend.mega_trend && (
            <div>
              <dt className="text-xs text-muted mb-1">Mega-Trend</dt>
              <dd className="text-sm">{trend.mega_trend}</dd>
            </div>
          )}
          {trend.brands.length > 0 && (
            <div>
              <dt className="text-xs text-muted mb-1">Marken</dt>
              <dd className="text-sm">{trend.brands.join(", ")}</dd>
            </div>
          )}
          {trend.regions.length > 0 && (
            <div>
              <dt className="text-xs text-muted mb-1">Regionen</dt>
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
              Originalquelle:{" "}
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
            Weitere Trends in {vertical.label}
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {related.map((r) => (
              <Link
                key={r.id}
                href={`/trends/${r.slug}`}
                className="rounded-lg border border-border bg-card p-4 hover:bg-card-hover hover:border-accent/30 transition-all"
              >
                <h3 className="text-sm font-medium leading-snug line-clamp-2 mb-2">
                  {r.title_de || r.title_en}
                </h3>
                <p className="text-xs text-muted line-clamp-2">
                  {r.summary_de || r.summary_en}
                </p>
              </Link>
            ))}
          </div>
        </section>
      )}

      {/* Foresight CTA */}
      <div className="mt-12 rounded-xl border border-accent/20 bg-accent/5 p-6 text-center">
        <p className="text-sm text-muted mb-3">
          Vollständige Mega/Macro/Micro-Einordnung und strategische Prognosen
        </p>
        <a
          href="https://catandary.de"
          className="inline-flex items-center gap-2 bg-accent text-background px-4 py-2 rounded-lg text-sm font-medium hover:bg-accent/90 transition-colors"
        >
          Catandary Foresight
        </a>
      </div>
    </div>
  );
}
