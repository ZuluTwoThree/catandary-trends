import { notFound } from "next/navigation";
import { getTrendBySlug, getTrends, isSourceLinkDead } from "@/lib/db";
import { getTrendTechContext } from "@/lib/technology";
import {
  archiveWindowDays,
  withinArchiveWindow,
  FREE_ARCHIVE_DAYS,
} from "@/lib/entitlement";
import { TrendArticleJsonLd } from "@/components/JsonLd";
import TrendArticle from "@/components/TrendArticle";
import TierGate from "@/components/TierGate";
import type { Metadata } from "next";

export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const trend = await getTrendBySlug(slug);
  if (!trend) return { title: "Trend not found" };

  return {
    title: `${trend.title_en} — Catandary Trends`,
    description: trend.summary_en || undefined,
    openGraph: {
      title: trend.title_en,
      description: trend.summary_en || undefined,
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
  const trend = await getTrendBySlug(slug);
  if (!trend) notFound();

  // Free archive window (issue #70): articles older than the window are a
  // Starter+ feature. Deliberately NOT a 404 — the URL keeps its title,
  // summary and metadata (SEO, backlinks, shares stay intact); only the body
  // is replaced by the upgrade card. Related articles are windowed too, so
  // the teaser never links free viewers into more gated pages.
  const windowDays = await archiveWindowDays();
  const inArchive = !withinArchiveWindow(
    trend.sort_date ?? trend.published_at,
    windowDays
  );

  const [relatedRaw, tech, sourceDead] = await Promise.all([
    getTrends({
      status: "published",
      vertical: trend.primary_vertical,
      max_age_days: windowDays,
      limit: 4,
    }),
    getTrendTechContext(trend.id),
    isSourceLinkDead(trend.source_url),
  ]);
  const related = relatedRaw.filter((t) => t.id !== trend.id).slice(0, 3);

  if (inArchive) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-8">
        <TrendArticleJsonLd trend={trend} />
        <TierGate
          need="starter"
          feature="The full trend archive"
          benefit={`Free covers the most recent ${FREE_ARCHIVE_DAYS} days of trend articles. Upgrade to read the whole archive — every article with its primary source.`}
          teaser={
            <article>
              {trend.source_name && (
                <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">
                  {trend.source_name}
                  {trend.sort_date &&
                    ` · ${new Date(trend.sort_date).toLocaleDateString("en-GB", {
                      day: "numeric",
                      month: "short",
                      year: "numeric",
                    })}`}
                </p>
              )}
              <h1 className="font-display text-[32px] leading-[1.15] text-paper mt-3">
                {trend.title_en}
              </h1>
              {trend.summary_en && (
                <p className="mt-4 max-w-2xl text-[15px] leading-[1.7] text-muted">
                  {trend.summary_en}
                </p>
              )}
            </article>
          }
        >
          <TrendArticle trend={trend} related={related} tech={tech} sourceDead={sourceDead} />
        </TierGate>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <TrendArticleJsonLd trend={trend} />
      <TrendArticle trend={trend} related={related} tech={tech} sourceDead={sourceDead} />
    </div>
  );
}
