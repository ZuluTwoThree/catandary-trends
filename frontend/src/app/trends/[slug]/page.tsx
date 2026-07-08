import { notFound } from "next/navigation";
import { getTrendBySlug, getTrends } from "@/lib/db";
import { getTrendTechContext } from "@/lib/technology";
import { TrendArticleJsonLd } from "@/components/JsonLd";
import TrendArticle from "@/components/TrendArticle";
import type { Metadata } from "next";

export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const trend = await getTrendBySlug(slug);
  if (!trend) return { title: "Trend not found" };

  return {
    title: `${trend.title_en} — Catandary Trends`,
    description: trend.summary_en || undefined,
    openGraph: {
      title: trend.title_en,
      description: trend.summary_en || undefined,
      type: "article",
    },
  };
}

export default async function TrendArticlePage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const trend = await getTrendBySlug(slug);
  if (!trend) notFound();

  const [relatedRaw, tech] = await Promise.all([
    getTrends({
      status: "published",
      vertical: trend.primary_vertical,
      limit: 4,
    }),
    getTrendTechContext(trend.id),
  ]);
  const related = relatedRaw.filter((t) => t.id !== trend.id).slice(0, 3);

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <TrendArticleJsonLd trend={trend} />
      <TrendArticle trend={trend} related={related} tech={tech} />
    </div>
  );
}
