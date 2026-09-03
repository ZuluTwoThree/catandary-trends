import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { getTrendsCount } from "@/lib/db";
import { PUBLIC_ARCHIVE_DAYS } from "@/lib/entitlement";
import { exportStaticParams } from "@/lib/renderMode";
import { pageCount, parsePageParam } from "@/lib/staticListing";
import StaticFeed, { staticListingMetadata } from "@/components/StaticFeed";

/**
 * /trends/page/[n] — page n (>= 2) of the static listing (lib/staticListing.ts).
 * Export: one file per page of the public window. Workstation: no
 * generateStaticParams at all (exportStaticParams), rendered per request
 * (see trends/[slug]/page.tsx on why `dynamicParams` stays default).
 */
export const generateStaticParams = exportStaticParams(async () => {
  const total = await getTrendsCount({
    status: "published",
    max_age_days: PUBLIC_ARCHIVE_DAYS,
  });
  // NB: Next aborts an export on an EMPTY list here — that needs a window
  // with <= 24 articles, i.e. a test window far below the 30-day default.
  return Array.from({ length: pageCount(total) - 1 }, (_, i) => ({
    n: String(i + 2),
  }));
});

export async function generateMetadata({
  params,
}: {
  params: Promise<{ n: string }>;
}): Promise<Metadata> {
  const { n } = await params;
  return staticListingMetadata(null, parsePageParam(n));
}

export default async function TrendsPageN({
  params,
}: {
  params: Promise<{ n: string }>;
}) {
  const { n } = await params;
  const page = parsePageParam(n);
  if (page === null) notFound();
  return <StaticFeed vertical={null} page={page} />;
}
