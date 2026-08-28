import type { MetadataRoute } from "next";
import { getTrends, getMegaTrends } from "@/lib/db";
import { getAllAnalyses } from "@/lib/analyses";

export const dynamic = "force-dynamic";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const baseUrl = "https://catandary.de";

  const trends = await getTrends({ limit: 5000 });
  const megaTrends = await getMegaTrends();
  const analyses = getAllAnalyses();

  const analysisUrls: MetadataRoute.Sitemap = analyses.map((a) => ({
    url: `${baseUrl}/analysis/${a.slug}`,
    lastModified: a.date,
    changeFrequency: "monthly" as const,
    priority: 0.7,
  }));

  const trendUrls: MetadataRoute.Sitemap = trends.map((trend) => ({
    url: `${baseUrl}/trends/${trend.slug}`,
    lastModified: trend.published_at || trend.created_at,
    changeFrequency: "weekly" as const,
    priority: 0.8,
  }));

  const megaUrls: MetadataRoute.Sitemap = megaTrends.map((mt) => ({
    url: `${baseUrl}/trends/mega/${encodeURIComponent(mt.mega_trend.toLowerCase().replace(/\s+/g, "-"))}`,
    lastModified: new Date(),
    changeFrequency: "weekly" as const,
    priority: 0.7,
  }));

  const foresightUrls: MetadataRoute.Sitemap = [
    "clusters",
    "technology",
    "lead-time",
    "evolution",
    "dossier",
  ].map((page) => ({
    url: `${baseUrl}/trends/foresight/${page}`,
    lastModified: new Date(),
    changeFrequency: "weekly" as const,
    priority: 0.8,
  }));

  return [
    {
      url: `${baseUrl}/`,
      lastModified: new Date(),
      changeFrequency: "weekly",
      priority: 1,
    },
    {
      url: `${baseUrl}/trends`,
      lastModified: new Date(),
      changeFrequency: "daily",
      priority: 1,
    },
    {
      url: `${baseUrl}/trends/mega`,
      lastModified: new Date(),
      changeFrequency: "weekly",
      priority: 0.9,
    },
    {
      url: `${baseUrl}/analysis`,
      lastModified: new Date(),
      changeFrequency: "weekly",
      priority: 0.8,
    },
    {
      url: `${baseUrl}/enquiry`,
      lastModified: new Date(),
      changeFrequency: "monthly",
      priority: 0.6,
    },
    {
      url: `${baseUrl}/trends/foresight`,
      lastModified: new Date(),
      changeFrequency: "daily",
      priority: 0.9,
    },
    ...foresightUrls,
    {
      url: `${baseUrl}/trends/pricing`,
      lastModified: new Date(),
      changeFrequency: "monthly",
      priority: 0.6,
    },
    {
      url: `${baseUrl}/trends/methodology`,
      lastModified: new Date(),
      changeFrequency: "monthly",
      priority: 0.6,
    },
    {
      url: `${baseUrl}/trends/newsletter`,
      lastModified: new Date(),
      changeFrequency: "monthly",
      priority: 0.5,
    },
    {
      url: `${baseUrl}/imprint`,
      lastModified: new Date(),
      changeFrequency: "yearly",
      priority: 0.2,
    },
    {
      url: `${baseUrl}/privacy`,
      lastModified: new Date(),
      changeFrequency: "yearly",
      priority: 0.2,
    },
    ...megaUrls,
    ...analysisUrls,
    ...trendUrls,
  ];
}
