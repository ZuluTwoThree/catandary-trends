import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { VERTICALS } from "@/lib/types";
import { isStaticExport } from "@/lib/renderMode";
import { verticalFromSlug, verticalSlug } from "@/lib/staticListing";
import StaticFeed, { staticListingMetadata } from "@/components/StaticFeed";

/**
 * /trends/v/[vertical] — page 1 of one vertical (lowercase id in the URL,
 * lib/staticListing.ts). Replaces the redirect-only /trends/vertical/[v]
 * route on the static site (Apache 301s the legacy and any-case forms,
 * public-export/trends/.htaccess).
 */
export async function generateStaticParams() {
  if (!isStaticExport()) return [];
  return VERTICALS.map((v) => ({ vertical: verticalSlug(v.id) }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ vertical: string }>;
}): Promise<Metadata> {
  const { vertical } = await params;
  const v = verticalFromSlug(vertical);
  return staticListingMetadata(v, v ? 1 : null);
}

export default async function VerticalPage({
  params,
}: {
  params: Promise<{ vertical: string }>;
}) {
  const { vertical } = await params;
  const v = verticalFromSlug(vertical);
  if (!v) notFound();
  return <StaticFeed vertical={v} page={1} />;
}
