import { notFound } from "next/navigation";
import type { Metadata } from "next";
import {
  getTrendsFiltered,
  getTrendsCount,
  getVerticalCounts,
  getVerticalCountsWindowed,
  getPublicWindowNewest,
} from "@/lib/db";
import { archiveWindowDays } from "@/lib/entitlement";
import { getVerticalInfo, type Vertical } from "@/lib/types";
import { STATIC_PAGE_SIZE, listingPath, pageCount } from "@/lib/staticListing";
import {
  dynamicUnlessStatic,
  metadataSettled,
  afterMetadata,
} from "@/lib/renderMode";
import TrendCard from "./TrendCard";
import TrendsHero from "./TrendsHero";
import StaticFilterBar from "./StaticFilterBar";
import PaginationNav from "./PaginationNav";
import ForesightCta from "./ForesightCta";
import { TrendsListJsonLd } from "./JsonLd";

/**
 * The listing page of the static export (design Schritt 4) — one component
 * behind /trends, /trends/page/[n], /trends/v/[vertical] and
 * /trends/v/[vertical]/page/[n]. No search params: the page is fully
 * described by (vertical, page), and the data is the public window in
 * `sort_date DESC, id DESC` order, 24 per page.
 *
 * On the workstation the same routes render per request over the whole
 * archive (archiveWindowDays() = null there) — a preview of what the export
 * emits, nothing else links to them.
 *
 * Determinism (byte-equal builds): every number on the page derives from the
 * data (counts, the newest sort_date as the hero stamp); the metadata gate
 * (lib/renderMode.ts) keeps the RSC row order stable.
 */

async function listingTotal(
  vertical: Vertical | null
): Promise<{ total: number; totalPages: number }> {
  const windowDays = await archiveWindowDays();
  const total = await getTrendsCount({
    status: "published",
    vertical: vertical ?? undefined,
    max_age_days: windowDays,
  });
  return { total, totalPages: pageCount(total) };
}

/**
 * `generateMetadata` body of the four listing routes: title, description,
 * canonical and rel=prev/next (`pagination` resolves against metadataBase).
 * `page === null` = an unparseable page param (the page body 404s).
 */
export async function staticListingMetadata(
  vertical: Vertical | null,
  page: number | null
): Promise<Metadata> {
  try {
    if (page === null) return { title: "Page not found — Catandary Trends" };
    const { totalPages } = await listingTotal(vertical);
    const label = vertical ? getVerticalInfo(vertical).label : null;
    const scope = label ? `${label} trends` : "Latest trends";
    const pageSuffix = page > 1 ? ` — page ${page}` : "";
    const where = label
      ? `Curated ${label} trend signals from primary sources`
      : "Curated trend signals across eight industry verticals";
    return {
      title: `${scope}${pageSuffix} — Catandary Trends`,
      description: `${where}, newest first${
        page > 1 ? ` (page ${page} of ${totalPages})` : ""
      }.`,
      alternates: { canonical: listingPath(vertical, page) },
      pagination: {
        previous: page > 1 ? listingPath(vertical, page - 1) : null,
        next: page < totalPages ? listingPath(vertical, page + 1) : null,
      },
    };
  } finally {
    metadataSettled(); // export determinism, see lib/renderMode.ts
  }
}

export default async function StaticFeed({
  vertical,
  page,
}: {
  vertical: Vertical | null;
  page: number;
}) {
  await dynamicUnlessStatic();
  const windowDays = await archiveWindowDays();
  const { total, totalPages } = await listingTotal(vertical);
  // Beyond the last page there is nothing — and in the export no such file.
  if (page > totalPages) notFound();

  const [trends, tabCounts, globalCounts, analyzedTotal, newest] =
    await Promise.all([
      getTrendsFiltered({
        status: "published",
        verticals: vertical ? [vertical] : undefined,
        max_age_days: windowDays,
        sort_by: "date_desc",
        limit: STATIC_PAGE_SIZE,
        offset: (page - 1) * STATIC_PAGE_SIZE,
      }),
      getVerticalCountsWindowed(windowDays),
      getVerticalCounts("published"),
      // Full analyzed corpus (all pipeline signals) — the trust number the
      // hero shows next to the curated count, as on the workstation feed.
      getTrendsCount(),
      getPublicWindowNewest(windowDays),
    ]);
  await afterMetadata(); // export determinism, see lib/renderMode.ts

  const totalPublished = Object.values(globalCounts).reduce((a, b) => a + b, 0);
  const info = vertical ? getVerticalInfo(vertical) : null;

  return (
    <div className="mx-auto max-w-7xl px-6 md:px-10 py-10">
      {!vertical && page === 1 && <TrendsListJsonLd />}
      <TrendsHero
        totalSignals={totalPublished}
        analyzedTotal={analyzedTotal}
        verticalCounts={globalCounts}
        asOf={newest}
      />

      <div className="mb-6">
        <StaticFilterBar active={vertical} counts={tabCounts} />
      </div>

      <div className="mb-6 flex items-baseline justify-between">
        <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted">
          <span className="text-accent tabular-nums">
            {total.toLocaleString("en-US")}
          </span>
          <span className="text-muted/70">
            {" "}
            / Signals{info ? ` · ${info.label}` : ""}
          </span>
        </div>
        <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted">
          Page <span className="text-paper tabular-nums">{page}</span>
          <span className="text-muted/70"> / {totalPages}</span>
        </div>
      </div>

      <h2 className="sr-only">
        {info ? `${info.label} signals` : "Latest signals"}
      </h2>
      {trends.length === 0 ? (
        <div className="border border-border border-dashed px-8 py-16 text-center">
          <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted mb-4">
            —— 0 results
          </div>
          <h3 className="font-display text-[32px] leading-[1.1] text-paper">
            The signal channel is <span className="italic">quiet</span>.
          </h3>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {trends.map((trend) => (
            <TrendCard key={trend.id} trend={trend} />
          ))}
        </div>
      )}

      <PaginationNav
        page={page}
        totalPages={totalPages}
        hrefFor={(p) => listingPath(vertical, p)}
      />

      <ForesightCta />
    </div>
  );
}
