import type { MetadataRoute } from "next";
import { getTrends, getMegaTrends, getPublicWindowSlugs } from "@/lib/db";
import { getAllAnalyses } from "@/lib/analyses";
import { isPublicMode } from "@/lib/publicMode";
import { isStaticExport } from "@/lib/renderMode";
import { PUBLIC_ARCHIVE_DAYS } from "@/lib/archiveWindow";
import { megaTrendSlug, VERTICALS } from "@/lib/types";
import { listingPath } from "@/lib/staticListing";
import { sitePath } from "@/lib/sitePaths";
import { publicEditionIndex } from "@/lib/newsletterExport";
import { editionPath } from "@/lib/newsletterEditions";

/**
 * Route handlers need a literal `force-static` for `output: "export"`
 * (Next checks the segment config, an env ternary is not allowed). The
 * workstation build therefore renders the sitemap once at build time instead
 * of per request — acceptable, the public sitemap is the exported one.
 */
export const dynamic = "force-static";

const SITE_URL = process.env.PUBLIC_SITE_URL || "https://catandary.de";

/**
 * Deterministic on purpose (the export is diffed build against build): no
 * `new Date()` anywhere — every `lastModified` comes from the data, and the
 * hub pages take the newest article date. Public deployments (PUBLIC_MODE /
 * static export) list only what exists there: the article window, the
 * mega themes, analyses and the static pages. The workstation instance keeps
 * its wider listing including the Foresight suite.
 */
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const publicOnly = isPublicMode() || isStaticExport();

  let trendUrls: MetadataRoute.Sitemap = [];
  let megaTrends: Awaited<ReturnType<typeof getMegaTrends>> = [];
  // Briefing archive (Schritt E): only the public deployments have the
  // /trends/newsletter/<year>-w<week> pages; the workstation reads editions
  // through the client page.
  let editionUrls: MetadataRoute.Sitemap = [];
  let newest: Date | null = null;
  // DB timestamps arrive as Postgres text ("2026-09-02 09:15:06.3195");
  // as a Date, Next serializes them W3C-style (the sitemap spec's format).
  const asDate = (d: string | null | undefined): Date | undefined => {
    if (!d) return undefined;
    const t = new Date(d);
    return Number.isNaN(t.getTime()) ? undefined : t;
  };
  const touch = (d: string | null | undefined) => {
    const t = asDate(d);
    if (t && (!newest || t > newest)) newest = t;
  };

  try {
    if (publicOnly) {
      const rows = await getPublicWindowSlugs(PUBLIC_ARCHIVE_DAYS);
      trendUrls = rows.map((r) => {
        touch(r.published_at ?? r.sort_date);
        return {
          url: `${SITE_URL}/trends/${r.slug}`,
          lastModified: asDate(r.published_at ?? r.sort_date),
          changeFrequency: "weekly" as const,
          priority: 0.8,
        };
      });
    } else {
      const trends = await getTrends({ status: "published", limit: 5000 });
      trendUrls = trends.map((trend) => {
        touch(trend.published_at || trend.created_at);
        return {
          url: `${SITE_URL}/trends/${trend.slug}`,
          lastModified: asDate(trend.published_at || trend.created_at),
          changeFrequency: "weekly" as const,
          priority: 0.8,
        };
      });
    }
    megaTrends = await getMegaTrends();
    if (publicOnly) {
      editionUrls = (await publicEditionIndex()).map((e) => ({
        url: `${SITE_URL}${editionPath(e.year, e.week)}`,
        lastModified: asDate(e.created_at),
        changeFrequency: "monthly" as const,
        priority: 0.5,
      }));
    }
  } catch (err) {
    // No database at build time (CI builds the frontend without Postgres):
    // the static URL set below still ships. The export build never takes
    // this branch silently — build_public_static.sh fails on an empty
    // article count.
    if (isStaticExport()) throw err;
    console.warn("sitemap: database unavailable, static URLs only —", (err as Error).message);
  }

  const analyses = getAllAnalyses();
  for (const a of analyses) touch(a.date);
  // A fixed floor keeps the file stable even for an empty data set.
  const hubDate = newest ?? new Date("2026-01-01T00:00:00Z");

  const analysisUrls: MetadataRoute.Sitemap = analyses.map((a) => ({
    url: `${SITE_URL}/analysis/${a.slug}`,
    lastModified: a.date,
    changeFrequency: "monthly" as const,
    priority: 0.7,
  }));

  const megaUrls: MetadataRoute.Sitemap = megaTrends.map((mt) => ({
    url: `${SITE_URL}/trends/mega/${encodeURIComponent(megaTrendSlug(mt.mega_trend))}`,
    lastModified: hubDate,
    changeFrequency: "weekly" as const,
    priority: 0.7,
  }));

  const hub = (
    path: string,
    changeFrequency: "daily" | "weekly" | "monthly" | "yearly",
    priority: number
  ): MetadataRoute.Sitemap[number] => ({
    url: `${SITE_URL}${path}`,
    lastModified: hubDate,
    changeFrequency,
    priority,
  });

  // Page 1 of each vertical (static listing routes, lib/staticListing.ts);
  // deeper pages are reachable via rel=next and stay out of the sitemap.
  const verticalUrls: MetadataRoute.Sitemap = publicOnly
    ? VERTICALS.map((v) => hub(listingPath(v.id, 1), "daily", 0.8))
    : [];

  const foresightUrls: MetadataRoute.Sitemap = publicOnly
    ? []
    : [
        hub("/trends/foresight", "daily", 0.9),
        ...["clusters", "technology", "lead-time", "evolution"].map((page) =>
          hub(`/trends/foresight/${page}`, "weekly", 0.8)
        ),
      ];

  return [
    hub("/", "weekly", 1),
    hub("/trends", "daily", 1),
    ...verticalUrls,
    hub("/trends/mega", "weekly", 0.9),
    hub("/analysis", "weekly", 0.8),
    hub(sitePath("/enquiry"), "monthly", 0.6),
    ...foresightUrls,
    hub("/trends/methodology", "monthly", 0.6),
    hub("/trends/newsletter", "weekly", 0.5),
    ...editionUrls,
    hub(sitePath("/imprint"), "yearly", 0.2),
    hub(sitePath("/privacy"), "yearly", 0.2),
    ...megaUrls,
    ...analysisUrls,
    ...trendUrls,
  ];
}
