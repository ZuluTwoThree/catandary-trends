import type { Trend } from "@/lib/types";
import { getVerticalInfo } from "@/lib/types";
import { serializeJsonLd } from "@/lib/jsonld";
import { ARTICLE_DISCLOSURE_EN } from "@/lib/aiDisclosure";

/**
 * Machine-readable half of the AI label (#99). There is NO standard for this:
 * `<meta name="ai-generated">` is somebody's proposal, schema.org has no
 * AI-provenance property, and C2PA signs media files, not HTML. So this uses
 * what schema.org does define and states the fact rather than inventing a flag:
 *
 *   author   stays the Organization — Catandary publishes this and answers for
 *            it; a machine cannot be the responsible author.
 *   creator  the SoftwareApplication that actually produced the words, with
 *            the visible disclosure sentence as its description, so the two
 *            can never say different things.
 *   isBasedOn  the one source the text was written from (Article/CreativeWork
 *            property) — the same URL the page links.
 *
 * The other half is `<meta name="generator">` on the page (aiDisclosure.ts)
 * and, above all, the visible label. If a real standard appears, it is added
 * here; nothing below has to be removed for that.
 */
export function TrendArticleJsonLd({ trend }: { trend: Trend }) {
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "Article",
    headline: trend.title_en,
    description: trend.summary_en,
    datePublished: trend.published_at || trend.created_at,
    dateModified: trend.published_at || trend.created_at,
    author: {
      "@type": "Organization",
      name: "Catandary",
      url: "https://catandary.de",
    },
    creator: {
      "@type": "SoftwareApplication",
      name: "Catandary Trends pipeline",
      applicationCategory: "Text generation",
      description: ARTICLE_DISCLOSURE_EN,
    },
    ...(trend.source_url ? { isBasedOn: trend.source_url } : {}),
    publisher: {
      "@type": "Organization",
      name: "Catandary Trends",
      url: "https://catandary.de/trends",
    },
    mainEntityOfPage: {
      "@type": "WebPage",
      "@id": `https://catandary.de/trends/${trend.slug}`,
    },
    keywords: trend.tags.join(", "),
    articleSection: getVerticalInfo(trend.primary_vertical).label,
  };

  return (
    <script
      type="application/ld+json"
      // serializeJsonLd escapes < > & so DB-sourced strings cannot close the script tag (F-2).
      dangerouslySetInnerHTML={{ __html: serializeJsonLd(jsonLd) }}
    />
  );
}

export function TrendsListJsonLd() {
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: "Catandary Trends",
    url: "https://catandary.de/trends",
    description:
      "Cross-Industry Trend Intelligence — curated trend signals from eight industry verticals.",
    publisher: {
      "@type": "Organization",
      name: "Catandary",
      url: "https://catandary.de",
    },
  };

  return (
    <script
      type="application/ld+json"
      // serializeJsonLd escapes < > & so DB-sourced strings cannot close the script tag (F-2).
      dangerouslySetInnerHTML={{ __html: serializeJsonLd(jsonLd) }}
    />
  );
}
