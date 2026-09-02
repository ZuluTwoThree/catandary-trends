import type { MetadataRoute } from "next";

// Route handlers must be `force-static` (a literal) for `output: "export"`;
// the file is content-free anyway, so the workstation build is unaffected.
export const dynamic = "force-static";

const SITE_URL = process.env.PUBLIC_SITE_URL || "https://catandary.de";

/**
 * PUBLIC_NOINDEX=1 (pre-launch switch, on until 2026-10-01 — owner decides
 * when to flip it): no crawling, no sitemap advertised; layout.tsx sets the
 * matching `noindex, nofollow` meta. Unset: the launch rules.
 */
export default function robots(): MetadataRoute.Robots {
  if (process.env.PUBLIC_NOINDEX === "1") {
    return { rules: { userAgent: "*", disallow: "/" } };
  }
  return {
    rules: {
      userAgent: "*",
      allow: "/trends/",
      disallow: ["/api/", "/_next/", "/trends/expired"],
    },
    sitemap: `${SITE_URL}/trends/sitemap.xml`,
  };
}
