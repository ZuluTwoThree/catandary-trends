import { notFound } from "next/navigation";
import { getTrendBySlug, getTrends } from "@/lib/db";
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
  const trend = getTrendBySlug(slug);
  if (!trend) return { title: "Trend nicht gefunden" };

  return {
    title: `${trend.title_de || trend.title_en} — Catandary Trends`,
    description: trend.summary_de || trend.summary_en || undefined,
    openGraph: {
      title: trend.title_de || trend.title_en,
      description: trend.summary_de || trend.summary_en || undefined,
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
  const trend = getTrendBySlug(slug);
  if (!trend) notFound();

  const related = getTrends({
    vertical: trend.primary_vertical,
    limit: 4,
  })
    .filter((t) => t.id !== trend.id)
    .slice(0, 3);

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <TrendArticleJsonLd trend={trend} />
      <TrendArticle trend={trend} related={related} />
    </div>
  );
}
