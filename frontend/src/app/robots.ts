import type { MetadataRoute } from "next";
import { AI_CRAWLER_USER_AGENTS } from "@/lib/aiCrawlers";

// Route handlers must be `force-static` (a literal) for `output: "export"`;
// the file is content-free anyway, so the workstation build is unaffected.
export const dynamic = "force-static";

const SITE_URL = process.env.PUBLIC_SITE_URL || "https://catandary.de";

/**
 * robots.txt of catandary.de (the export's file replaces the hand-written
 * one on the webspace — ROOT_ALLOWLIST in scripts/publish_static_site.py).
 *
 * Always: the AI / TDM crawlers from lib/aiCrawlers.ts are disallowed
 * everywhere (owner decision 2026-09-03; the .htaccess adds a 403 on top).
 * PUBLIC_NOINDEX=1 (pre-launch switch, on until 2026-10-01 — owner decides
 * when to flip it): everyone else is kept out too and no sitemap is
 * advertised; layout.tsx sets the matching `noindex, nofollow` meta.
 * Unset: search engines may crawl everything except the never-indexable
 * bits. `_next/` stays allowed on purpose — Google needs the CSS/JS to
 * render the pages.
 */
export default function robots(): MetadataRoute.Robots {
  const aiBlock = { userAgent: [...AI_CRAWLER_USER_AGENTS], disallow: "/" };
  if (process.env.PUBLIC_NOINDEX === "1") {
    return { rules: [aiBlock, { userAgent: "*", disallow: "/" }] };
  }
  return {
    rules: [
      aiBlock,
      { userAgent: "*", allow: "/", disallow: ["/api/", "/trends/expired", "/trends/newsletter/unsubscribed"] },
    ],
    sitemap: `${SITE_URL}/trends/sitemap.xml`,
  };
}
