import type { MetadataRoute } from "next";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/trends/",
      disallow: ["/api/", "/_next/"],
    },
    sitemap: "https://catandary.de/sitemap.xml",
  };
}
