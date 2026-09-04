/**
 * Research Explorer facets on the curated signal layer (#73 Teil 2, the
 * cheap refinements): source group, period and sort order as URL params,
 * plus the concept facet behind the clickable concept badges.
 *
 *   ?src=arxiv,openalex   source groups (comma list, whitelisted)
 *   ?range=30d            period over research_signals.published
 *   ?sort=relevance|date  relevance needs a text query (FTS rank)
 *   ?concept=Microbiome   exact concept (the badge text)
 *   ?layer=signals        keep a text query on the signal layer instead of
 *                         routing it to the 45M corpus
 *
 * Pure: parsing and the SQL fragments are unit-tested; db.ts only assembles.
 */

export type ResearchSourceKey = "arxiv" | "biorxiv" | "medrxiv" | "openalex" | "journals";

export const RESEARCH_SOURCES: { key: ResearchSourceKey; label: string; title: string }[] = [
  { key: "arxiv", label: "arXiv", title: "arXiv preprints (open access)" },
  { key: "biorxiv", label: "bioRxiv", title: "bioRxiv preprints (open access)" },
  { key: "medrxiv", label: "medRxiv", title: "medRxiv preprints (open access)" },
  { key: "openalex", label: "OpenAlex", title: "Journal works from the OpenAlex sweeps (citation-gated + weekly fresh)" },
  { key: "journals", label: "Journals & press", title: "Journal and science-press RSS feeds (Nature, PNAS, Lancet, Phys.org …)" },
];

export type ResearchRangeKey = "7d" | "30d" | "90d" | "1y" | "all";

export const RESEARCH_RANGES: { key: ResearchRangeKey; label: string; days: number | null }[] = [
  { key: "7d", label: "7 days", days: 7 },
  { key: "30d", label: "30 days", days: 30 },
  { key: "90d", label: "90 days", days: 90 },
  { key: "1y", label: "1 year", days: 365 },
  { key: "all", label: "All time", days: null },
];

export type ResearchSortKey = "date" | "relevance";

export interface ResearchFacets {
  sources: ResearchSourceKey[];
  range: ResearchRangeKey;
  sort: ResearchSortKey;
  concept: string | undefined;
  /** Text query stays on the signal layer (`?layer=signals`). */
  signalLayer: boolean;
}

const SOURCE_KEYS = new Set<string>(RESEARCH_SOURCES.map((s) => s.key));
const RANGE_KEYS = new Set<string>(RESEARCH_RANGES.map((r) => r.key));

export function parseSourceParam(raw: string | undefined | null): ResearchSourceKey[] {
  if (!raw) return [];
  const out: ResearchSourceKey[] = [];
  for (const part of raw.split(",")) {
    const k = part.trim().toLowerCase();
    if (SOURCE_KEYS.has(k) && !out.includes(k as ResearchSourceKey)) out.push(k as ResearchSourceKey);
  }
  return out;
}

export function parseRangeParam(raw: string | undefined | null): ResearchRangeKey {
  const k = (raw ?? "").trim().toLowerCase();
  return RANGE_KEYS.has(k) ? (k as ResearchRangeKey) : "all";
}

/** Relevance only makes sense with a text query; otherwise date. */
export function parseSortParam(raw: string | undefined | null, hasQuery: boolean): ResearchSortKey {
  const k = (raw ?? "").trim().toLowerCase();
  if (k === "relevance") return hasQuery ? "relevance" : "date";
  if (k === "date") return "date";
  return hasQuery ? "relevance" : "date";
}

export function parseResearchFacets(sp: {
  src?: string; range?: string; sort?: string; concept?: string; layer?: string;
}, hasQuery: boolean): ResearchFacets {
  const concept = (sp.concept ?? "").trim().slice(0, 120);
  return {
    sources: parseSourceParam(sp.src),
    range: parseRangeParam(sp.range),
    sort: parseSortParam(sp.sort, hasQuery),
    concept: concept || undefined,
    signalLayer: sp.layer === "signals",
  };
}

export function rangeDays(range: ResearchRangeKey): number | null {
  return RESEARCH_RANGES.find((r) => r.key === range)?.days ?? null;
}

/** SQL predicate over research_signals.source for the chosen groups (OR-ed),
 *  or null when nothing is selected. Constant strings only — no params. */
export function sourceSql(sources: ResearchSourceKey[]): string | null {
  if (sources.length === 0) return null;
  const parts = sources.map((s) => {
    switch (s) {
      case "arxiv": return "source = 'arXiv Preprints'";
      case "biorxiv": return "source = 'biorxiv Preprints'";
      case "medrxiv": return "source = 'medrxiv Preprints'";
      case "openalex": return "source LIKE 'OpenAlex%'";
      case "journals":
        return "(source NOT LIKE 'OpenAlex%' AND source NOT IN ('arXiv Preprints','biorxiv Preprints','medrxiv Preprints'))";
    }
  });
  return `(${parts.join(" OR ")})`;
}

/** Toggle one source in the comma list (for the facet links). */
export function toggleSource(current: ResearchSourceKey[], key: ResearchSourceKey): ResearchSourceKey[] {
  return current.includes(key) ? current.filter((k) => k !== key) : [...current, key];
}

/** Count of facets that narrow the signal layer (for the "clear" affordance). */
export function activeFacetCount(f: ResearchFacets): number {
  return (f.sources.length > 0 ? 1 : 0) + (f.range !== "all" ? 1 : 0) + (f.concept ? 1 : 0);
}
