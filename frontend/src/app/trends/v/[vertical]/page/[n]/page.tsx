import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { getTrendsCount } from "@/lib/db";
import { PUBLIC_ARCHIVE_DAYS } from "@/lib/entitlement";
import { VERTICALS } from "@/lib/types";
import { exportStaticParams } from "@/lib/renderMode";
import {
  pageCount,
  parsePageParam,
  verticalFromSlug,
  verticalSlug,
} from "@/lib/staticListing";
import StaticFeed, { staticListingMetadata } from "@/components/StaticFeed";

/** /trends/v/[vertical]/page/[n] — page n (>= 2) of one vertical. */
export const generateStaticParams = exportStaticParams(async () => {
  const params: { vertical: string; n: string }[] = [];
  for (const v of VERTICALS) {
    const total = await getTrendsCount({
      status: "published",
      vertical: v.id,
      max_age_days: PUBLIC_ARCHIVE_DAYS,
    });
    for (let n = 2; n <= pageCount(total); n++) {
      params.push({ vertical: verticalSlug(v.id), n: String(n) });
    }
  }
  return params;
});

export async function generateMetadata({
  params,
}: {
  params: Promise<{ vertical: string; n: string }>;
}): Promise<Metadata> {
  const { vertical, n } = await params;
  const v = verticalFromSlug(vertical);
  return staticListingMetadata(v, v ? parsePageParam(n) : null);
}

export default async function VerticalPageN({
  params,
}: {
  params: Promise<{ vertical: string; n: string }>;
}) {
  const { vertical, n } = await params;
  const v = verticalFromSlug(vertical);
  const page = parsePageParam(n);
  if (!v || page === null) notFound();
  return <StaticFeed vertical={v} page={page} />;
}
