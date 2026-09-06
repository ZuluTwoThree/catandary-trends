import { cache } from "react";
import { notFound } from "next/navigation";
import {
  getTrendBySlug,
  getPublicWindowSlugs,
  getRelatedPredecessors,
  isSourceLinkDead,
} from "@/lib/db";
import { getTrendTechContext } from "@/lib/technology";
import { archiveWindowDays, withinWindow, PUBLIC_ARCHIVE_DAYS } from "@/lib/archiveWindow";
import { isPublicMode } from "@/lib/publicMode";
import {
  exportStaticParams,
  dynamicUnlessStatic,
  isStaticExport,
  metadataSettled,
  afterMetadata,
} from "@/lib/renderMode";
import { ARTICLE_GENERATOR_META } from "@/lib/aiDisclosure";
import { TrendArticleJsonLd } from "@/components/JsonLd";
import TrendArticle from "@/components/TrendArticle";
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
      // #99: names the pipeline that wrote this page. `other` is MERGED into
      // the layout's (Object.assign in Next's resolve-metadata), so the site's
      // tdm-reservation/tdm-policy/robots tags survive this addition — and the
      // generator tag stays on article pages only, which are the only pages a
      // machine writes. It is a convention, not a standard; the disclosure
      // that counts is the visible one (components/AiArticleDisclosure.tsx).
      other: { generator: ARTICLE_GENERATOR_META },
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

  // Public window (#93): on the public showcase (PUBLIC_MODE preview) an
  // out-of-window article is a hard 404 — the public dataset simply ends at
  // the window, mirroring the real deploy, where the row is absent from the
  // exported slice altogether. On the owner instance the window is null and
  // every published article renders. (Until 2026-09-03 this was the #70
  // free-tier archive gate with an upgrade card; gone with the SaaS model.)
  //
  // In the static export the slug list IS the window (generateStaticParams
  // applied the same bound in SQL), so the per-article check is skipped —
  // it could only ever disagree by a timezone edge and turn a listed page
  // into a build-time notFound().
  const windowDays = archiveWindowDays();
  if (
    !isStaticExport() &&
    !withinWindow(trend.sort_date ?? trend.published_at, windowDays)
  ) {
    notFound();
  }

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

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <TrendArticleJsonLd trend={trend} />
      <TrendArticle trend={trend} related={related} tech={tech} sourceDead={sourceDead} />
    </div>
  );
}
