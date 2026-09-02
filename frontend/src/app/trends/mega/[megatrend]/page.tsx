import { notFound } from "next/navigation";
import { archiveWindowDays } from "@/lib/entitlement";
import { getMegaTrends, getTrendsByMegaTrend } from "@/lib/db";
import { getMegaTrendInfo, megaTrendSlug } from "@/lib/types";
import TrendCard from "@/components/TrendCard";
import ForesightCta from "@/components/ForesightCta";
import MegaTrendHeader from "@/components/MegaTrendHeader";
import {
  dynamicUnlessStatic,
  isStaticExport,
  metadataSettled,
  afterMetadata,
} from "@/lib/renderMode";
import { isPublicMode } from "@/lib/publicMode";
import type { Metadata } from "next";

/**
 * Static export: one page per mega-trend key (28). On the workstation the
 * list is empty and the page renders per request (dynamicUnlessStatic);
 * `dynamicParams` stays default — see trends/[slug]/page.tsx.
 */
export async function generateStaticParams() {
  if (!isStaticExport()) return [];
  const all = await getMegaTrends();
  return all.map((m) => ({ megatrend: megaTrendSlug(m.mega_trend) }));
}

function findMegaTrend(slug: string, allMega: { mega_trend: string; count: number; verticals: string[] }[]) {
  const decoded = decodeURIComponent(slug);
  // Try direct match: URL uses hyphens, DB keys use underscores
  const asKey = decoded.replace(/-/g, "_");
  const match = allMega.find(
    (m) => m.mega_trend === asKey || m.mega_trend.toLowerCase() === asKey.toLowerCase()
  );
  if (match) return match;
  // Fallback: match with spaces (for any legacy URLs)
  const asSpaces = decoded.replace(/-/g, " ");
  return allMega.find(
    (m) => m.mega_trend.toLowerCase() === asSpaces.toLowerCase()
  );
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ megatrend: string }>;
}): Promise<Metadata> {
  try {
    const { megatrend } = await params;
    const allMega = await getMegaTrends();
    const match = findMegaTrend(megatrend, allMega);
    if (!match) return { title: "Mega-trend not found" };

    const info = getMegaTrendInfo(match.mega_trend);
    const displayName = info?.name_en ?? match.mega_trend;

    return {
      title: `${displayName} — Catandary Mega-Trends`,
      description: info?.description_en ?? `Trend signals for mega-trend "${displayName}" across ${match.verticals.length} industries.`,
      alternates: { canonical: `/trends/mega/${megaTrendSlug(match.mega_trend)}` },
    };
  } finally {
    metadataSettled(); // export determinism, see lib/renderMode.ts
  }
}

export default async function MegaTrendPage({
  params,
}: {
  params: Promise<{ megatrend: string }>;
}) {
  await dynamicUnlessStatic();
  const { megatrend } = await params;
  const allMega = await getMegaTrends();
  const match = findMegaTrend(megatrend, allMega);
  if (!match) notFound();

  const windowDays = await archiveWindowDays(); // issue #70
  let trends = await getTrendsByMegaTrend(match.mega_trend, {
    status: "published",
    max_age_days: windowDays,
  });
  // Workstation-only fallback to unpublished rows for a theme with nothing
  // published in the window. Never on a public deployment: it put draft
  // payloads into three exported mega pages (export gate, 2026-09-02).
  if (trends.length === 0 && !isPublicMode()) {
    trends = await getTrendsByMegaTrend(match.mega_trend, { max_age_days: windowDays });
  }
  await afterMetadata(); // export determinism, see lib/renderMode.ts

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <MegaTrendHeader
        megaTrend={match.mega_trend}
        count={match.count}
        verticals={match.verticals}
      />

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 mt-8">
        {trends.map((trend) => (
          <TrendCard key={trend.id} trend={trend} />
        ))}
      </div>

      <ForesightCta />
    </div>
  );
}
