import type { Trend } from "@/lib/types";
import { getVerticalInfo } from "@/lib/types";

export function TrendArticleJsonLd({ trend }: { trend: Trend }) {
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "Article",
    headline: trend.title_de || trend.title_en,
    description: trend.summary_de || trend.summary_en,
    datePublished: trend.published_at || trend.created_at,
    dateModified: trend.published_at || trend.created_at,
    author: {
      "@type": "Organization",
      name: "Catandary",
      url: "https://catandary.de",
    },
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
      dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
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
      "Cross-Industry Trend Intelligence — kuratierte Trend-Signale aus acht Industrie-Vertikalen.",
    publisher: {
      "@type": "Organization",
      name: "Catandary",
      url: "https://catandary.de",
    },
  };

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
    />
  );
}
