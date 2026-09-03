import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { exportStaticParams, isStaticExport, metadataSettled, afterMetadata } from "@/lib/renderMode";
import { editionExcerpt, editionPath, editionSlug, parseEditionSlug } from "@/lib/newsletterEditions";
import { loadPublicEdition, publicEditionIndex } from "@/lib/newsletterExport";
import StaticBriefing from "@/components/newsletter/StaticBriefing";

/**
 * /trends/newsletter/<year>-w<week> — one archived briefing, static export
 * only (Schritt E). The page list is the archive index (the last
 * PUBLIC_NEWSLETTER_EDITIONS editions); on the workstation there is no
 * generateStaticParams (exportStaticParams → undefined) and the route is a
 * 404 — the workstation reads editions through /trends/newsletter?year=&week=
 * (client page) as before, one URL per page per instance.
 */
export const generateStaticParams = exportStaticParams(async () => {
  const editions = await publicEditionIndex();
  return editions.map((e) => ({ edition: editionSlug(e.year, e.week) }));
});

export async function generateMetadata({
  params,
}: {
  params: Promise<{ edition: string }>;
}): Promise<Metadata> {
  try {
    if (!isStaticExport()) return { title: "Not found" };
    const { edition: slug } = await params;
    const key = parseEditionSlug(slug);
    if (!key) return { title: "Briefing not found" };
    const edition = await loadPublicEdition(key.year, key.week);
    if (!edition) return { title: "Briefing not found" };
    const title = `Trend Briefing — Week ${edition.week}/${edition.year} — Catandary Trends`;
    const description = editionExcerpt(edition.editorial) || undefined;
    const canonical = editionPath(edition.year, edition.week);
    return {
      title,
      description,
      alternates: { canonical },
      openGraph: { title, description, type: "article", url: canonical },
    };
  } finally {
    metadataSettled(); // export determinism, see lib/renderMode.ts
  }
}

export default async function NewsletterEditionPage({
  params,
}: {
  params: Promise<{ edition: string }>;
}) {
  if (!isStaticExport()) notFound();
  const { edition: slug } = await params;
  const key = parseEditionSlug(slug);
  if (!key) notFound();

  const [editions, edition] = await Promise.all([
    publicEditionIndex(),
    loadPublicEdition(key.year, key.week),
  ]);
  // Only editions inside the archive window exist as pages.
  if (!edition || !editions.some((e) => e.year === key.year && e.week === key.week)) notFound();
  await afterMetadata(); // export determinism, see lib/renderMode.ts

  return <StaticBriefing edition={edition} editions={editions} variant="edition" />;
}
