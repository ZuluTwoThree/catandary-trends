export type Locale = "de" | "en";

export const translations = {
  de: {
    // Header
    trends: "Trends",
    newsletter: "Newsletter",

    // Hero
    heroTitle: "Cross-Industry Trend Intelligence",
    heroSubtitle:
      "Kuratierte Trend-Signale aus 10 Industrie-Vertikalen. Analysiert, klassifiziert und eingeordnet.",

    // Filter
    filterAll: "Alle",

    // Empty state
    emptyTitle: "Noch keine Trends",
    emptyIn: "in",
    emptySubtitle:
      "Die Pipeline läuft — bald erscheinen hier kuratierte Trend-Signale.",

    // CTA
    ctaTitle: "Tiefere Analysen gefragt?",
    ctaText:
      "Catandary Foresight bietet vollständige Mega/Macro/Micro-Prognosen, Cross-Industry-Cluster und strategische Handlungsempfehlungen.",
    ctaButton: "Catandary Foresight entdecken",

    // Pagination
    paginationPrev: "Zurück",
    paginationNext: "Weiter",

    // Article
    source: "Quelle",
    originalSource: "Originalquelle",
    signalType: "Signal-Typ",
    megaTrend: "Mega-Trend",
    brands: "Marken",
    regions: "Regionen",
    relatedTrends: "Weitere Trends in",
    foresightCta:
      "Vollständige Mega/Macro/Micro-Einordnung und strategische Prognosen",
    crossIndustry: "Cross-Industry",

    // Newsletter
    newsletterTitle: "Trends Newsletter",
    newsletterSubtitle:
      "Jeden Montag die wichtigsten Trend-Signale aus 10 Branchen. Kuratiert, analysiert, eingeordnet.",
    newsletterPlaceholder: "deine@email.de",
    newsletterButton: "Abonnieren",
    newsletterLoading: "...",
    newsletterSpam: "Kein Spam. Jederzeit abmeldbar.",
    newsletterFeature1Title: "Top-Trends der Woche",
    newsletterFeature1Text:
      "Die wichtigsten Signale aus allen Vertikalen, jeden Montag.",
    newsletterFeature2Title: "Cross-Industry Insights",
    newsletterFeature2Text:
      "Trends die mehrere Branchen betreffen — dein Frühwarnsystem.",
    newsletterFeature3Title: "PESTEL-Analyse",
    newsletterFeature3Text:
      "Politische, wirtschaftliche und technologische Einordnung.",
    newsletterFeature4Title: "Foresight-Previews",
    newsletterFeature4Text:
      "Exklusive Vorschauen auf Catandary Foresight Analysen.",

    // Footer
    footerRights: "All rights reserved.",
    footerPowered: "Powered by",

    // Signal types
    product_launch: "Produkteinführung",
    research: "Forschung",
    market_shift: "Marktverschiebung",
    consumer_behavior: "Verbraucherverhalten",
    regulation: "Regulierung",
    funding: "Finanzierung",
    partnership: "Partnerschaft",
    patent: "Patent",
  },
  en: {
    trends: "Trends",
    newsletter: "Newsletter",

    heroTitle: "Cross-Industry Trend Intelligence",
    heroSubtitle:
      "Curated trend signals from 10 industry verticals. Analyzed, classified, and contextualized.",

    filterAll: "All",

    emptyTitle: "No trends yet",
    emptyIn: "in",
    emptySubtitle:
      "The pipeline is running — curated trend signals will appear here soon.",

    ctaTitle: "Looking for deeper analysis?",
    ctaText:
      "Catandary Foresight offers complete Mega/Macro/Micro forecasts, cross-industry clusters, and strategic recommendations.",
    ctaButton: "Discover Catandary Foresight",

    paginationPrev: "Previous",
    paginationNext: "Next",

    source: "Source",
    originalSource: "Original source",
    signalType: "Signal type",
    megaTrend: "Mega trend",
    brands: "Brands",
    regions: "Regions",
    relatedTrends: "More trends in",
    foresightCta:
      "Complete Mega/Macro/Micro classification and strategic forecasts",
    crossIndustry: "Cross-Industry",

    newsletterTitle: "Trends Newsletter",
    newsletterSubtitle:
      "The most important trend signals from 10 industries, every Monday. Curated, analyzed, contextualized.",
    newsletterPlaceholder: "your@email.com",
    newsletterButton: "Subscribe",
    newsletterLoading: "...",
    newsletterSpam: "No spam. Unsubscribe anytime.",
    newsletterFeature1Title: "Weekly Top Trends",
    newsletterFeature1Text:
      "The most important signals from all verticals, every Monday.",
    newsletterFeature2Title: "Cross-Industry Insights",
    newsletterFeature2Text:
      "Trends affecting multiple industries — your early warning system.",
    newsletterFeature3Title: "PESTEL Analysis",
    newsletterFeature3Text:
      "Political, economic, and technological classification.",
    newsletterFeature4Title: "Foresight Previews",
    newsletterFeature4Text:
      "Exclusive previews of Catandary Foresight analyses.",

    footerRights: "All rights reserved.",
    footerPowered: "Powered by",

    product_launch: "Product Launch",
    research: "Research",
    market_shift: "Market Shift",
    consumer_behavior: "Consumer Behavior",
    regulation: "Regulation",
    funding: "Funding",
    partnership: "Partnership",
    patent: "Patent",
  },
} as const;

export type TranslationKey = keyof (typeof translations)["de"];
