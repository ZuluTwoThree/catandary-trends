import type { MetadataRoute } from "next";
import { getTrends } from "@/lib/db";

export const dynamic = "force-dynamic";

export default function sitemap(): MetadataRoute.Sitemap {
  const baseUrl = "https://catandary.de";

  const trends = getTrends({ limit: 500 });

  const trendUrls: MetadataRoute.Sitemap = trends.map((trend) => ({
    url: `${baseUrl}/trends/${trend.slug}`,
    lastModified: trend.published_at || trend.created_at,
    changeFrequency: "weekly",
    priority: 0.8,
  }));

  return [
    {
      url: `${baseUrl}/trends`,
      lastModified: new Date(),
      changeFrequency: "daily",
      priority: 1,
    },
    {
      url: `${baseUrl}/trends/newsletter`,
      lastModified: new Date(),
      changeFrequency: "monthly",
      priority: 0.5,
    },
    ...trendUrls,
  ];
}
