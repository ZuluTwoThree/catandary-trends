import { cache } from "react";
import { notFound } from "next/navigation";
import {
  getTrendBySlug,
  getPublicWindowSlugs,
  getRelatedPredecessors,
  isSourceLinkDead,
} from "@/lib/db";
import { getTrendTechContext } from "@/lib/technology";
import {
  archiveWindowDays,
  withinArchiveWindow,
  FREE_ARCHIVE_DAYS,
  PUBLIC_ARCHIVE_DAYS,
} from "@/lib/entitlement";
import { isPublicMode } from "@/lib/publicMode";
import {
  exportStaticParams,
  dynamicUnlessStatic,
  isStaticExport,
  metadataSettled,
  afterMetadata,
} from "@/lib/renderMode";
import { TrendArticleJsonLd } from "@/components/JsonLd";
import TrendArticle from "@/components/TrendArticle";
import TierGate from "@/components/TierGate";
import type { Metadata } from "next";

/**
 * Static export (design Schritt 3): the page list is every published slug in
 * the public window (PUBLIC_WINDOW_DAYS, default 30 — lib/archiveWindow.ts);
 * anything else does not exist as a file and is Apache's 410/404. On the
 * workstation there is NO generateStaticParams (exportStaticParams returns
 * undefined) — the route is plain dynamic and renders per request as before
 * (dynamicUnlessStatic below), so a slug published after the last build is
 * never a 404 there. An empty list would not do: Next then treats the route
 * as SSG and renders unknown slugs on demand as static pages, where the
 * `connection()` call is a DYNAMIC_SERVER_USAGE 500 (2026-09-03).
 * `dynamicParams` stays at its default: Next only accepts a static boolean
 * there, and `false` would 404 every slug on the workstation — in the
 * export it is moot, there is no server to serve an unlisted param anyway.
 */
export const generateStaticParams = exportStaticParams(async () => {
  const rows = await getPublicWindowSlugs(PUBLIC_ARCHIVE_DAYS);
  return rows.map((r) => ({ slug: r.slug }));
});

/**
 * One lookup per request, shared by generateMetadata and the page body
 * (React request-scoped cache). Halves the queries — and keeps the export
 * deterministic: with two independent queries the metadata rows and the
 * page's client-component rows streamed in whichever order the pool
 * answered, and ~5 % of article payloads flipped between builds.
 */
const loadTrend = cache((slug: string) => getTrendBySlug(slug));

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  try {
    const { slug } = await params;
    const trend = await loadTrend(slug);
    if (!trend) return { title: "Trend not found" };

    // Path-relative: resolved against layout.tsx's metadataBase, so the
    // exported HTML carries absolute canonical/OG URLs on the public host.
    const canonical = `/trends/${trend.slug}`;
    return {
      title: `${trend.title_en} — Catandary Trends`,
      description: trend.summary_en || undefined,
      alternates: { canonical },
      openGraph: {
        title: trend.title_en,
        description: trend.summary_en || undefined,
        type: "article",
        url: canonical,
      },
    };
  } finally {
    metadataSettled(); // export determinism, see lib/renderMode.ts
  }
}

export default async function TrendArticlePage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  await dynamicUnlessStatic();
  const { slug } = await params;
  // Published-only lookup (default of getTrendBySlug): a draft, rejected or
  // signal row with this slug is a 404 here, not a page.
  const trend = await loadTrend(slug);
  if (!trend) notFound();

  // Free archive window (issue #70): articles older than the window are a
  // Starter+ feature. Deliberately NOT a 404 — the URL keeps its title,
  // summary and metadata (SEO, backlinks, shares stay intact); only the body
  // is replaced by the upgrade card. Related articles are windowed too, so
  // the teaser never links free viewers into more gated pages.
  //
  // In the static export the slug list IS the window (generateStaticParams
  // applied the same bound in SQL), so the per-article check is skipped —
  // it could only ever disagree by a timezone edge and turn a listed page
  // into a build-time notFound().
  const windowDays = await archiveWindowDays();
  const inArchive =
    !isStaticExport() &&
    !withinArchiveWindow(trend.sort_date ?? trend.published_at, windowDays);

  // #93: on the public showcase an out-of-window article is a hard 404 — the
  // public dataset simply ends at the window (no tiers exist there, so the
  // #70 upgrade card below would advertise a plan that cannot be bought and
  // link into the blocked /trends/pricing route). Mirrors the real deploy,
  // where the row is absent from the exported slice altogether.
  if (inArchive && isPublicMode()) notFound();

  // Related = the 3 predecessors of the same vertical (lib/db.ts) — stable
  // per article, which keeps exported pages byte-identical across builds.
  // The technology context is a pgvector query whose component renders
  // nothing in public mode, so it is not even asked for there.
  const [related, tech, sourceDead] = await Promise.all([
    getRelatedPredecessors(trend, { limit: 3, max_age_days: windowDays }),
    isPublicMode() ? Promise.resolve([]) : getTrendTechContext(trend.id),
    isSourceLinkDead(trend.source_url),
  ]);
  await afterMetadata(); // export determinism, see lib/renderMode.ts

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
