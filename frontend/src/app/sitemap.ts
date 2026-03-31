import type { MetadataRoute } from "next";
import { getTrends, getMegaTrends } from "@/lib/db";

export const dynamic = "force-dynamic";

export default function sitemap(): MetadataRoute.Sitemap {
  const baseUrl = "https://catandary.de";

  const trends = getTrends({ limit: 500 });
  const megaTrends = getMegaTrends();

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

  return [
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
      url: `${baseUrl}/trends/cross-vertical`,
      lastModified: new Date(),
      changeFrequency: "weekly",
      priority: 0.9,
    },
    {
      url: `${baseUrl}/trends/newsletter`,
      lastModified: new Date(),
      changeFrequency: "monthly",
      priority: 0.5,
    },
    ...megaUrls,
    ...trendUrls,
  ];
}
