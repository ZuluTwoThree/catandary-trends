/**
 * Server-side loaders for the briefing archive of the static export
 * (Schritt E): the edition index and one edition with its article links
 * resolved against the public article window (lib/newsletterEditions.ts —
 * the rule; lib/db.ts — the queries). Request-scoped `cache()` so the
 * index page, the edition pages and generateStaticParams share one round
 * trip per render.
 */
import { cache } from "react";
import { getNewsletterEditionIndex, getNewsletterEdition, getTrendLinkTargets } from "./db";
import { PUBLIC_ARCHIVE_DAYS } from "./entitlement";
import { publicNewsletterEditions } from "./archiveWindow";
import {
  collectEditionSlugs,
  editionSources,
  rewriteEditionForExport,
  type EditionSummary,
  type NewsletterEdition,
} from "./newsletterEditions";

export const publicEditionIndex = cache(
  (): Promise<EditionSummary[]> => getNewsletterEditionIndex(publicNewsletterEditions())
);

/**
 * The edition as the export renders it, or null. Window membership comes
 * from the same predicate as the article pages (getTrendLinkTargets), so an
 * internal link never points at a slug this build did not write. Sources:
 * the edition's own `trend_refs.source_url` first (W32+), the trends row's
 * `source_url` otherwise.
 */
export const loadPublicEdition = cache(
  async (year: number, week: number): Promise<NewsletterEdition | null> => {
    const edition = await getNewsletterEdition(year, week);
    if (!edition) return null;
    const targets = await getTrendLinkTargets(collectEditionSlugs(edition), PUBLIC_ARCHIVE_DAYS);
    const inWindow = new Set<string>();
    const sourceBySlug = editionSources(edition);
    for (const t of targets) {
      if (t.in_window) inWindow.add(t.slug);
      if (t.source_url && !sourceBySlug.has(t.slug)) sourceBySlug.set(t.slug, t.source_url);
    }
    return rewriteEditionForExport(edition, { inWindow, sourceBySlug });
  }
);
