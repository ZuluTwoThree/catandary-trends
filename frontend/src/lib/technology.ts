import { q, q1 } from "./pg";

/**
 * Technology-axis insights (issue #3/#28): precomputed per-CPC-subclass
 * snapshots built by scripts/build_cpc_insights.py. Each payload carries the
 * four-tier lead-time chain (science → patent → funding → market), patent
 * citation dynamics, and CPC convergence partners. Read-only here — finished
 * default views, no on-demand computation.
 */

export type TierName = "science" | "patent" | "funding" | "market";

export interface TierLead {
  n: number;
  first: number | null;
  takeoff: number | null;
  median: number | null;
  /** year (as string) -> signal count */
  series: Record<string, number>;
  /** year -> share of the tier's total that year (basis points); acquisition-
   *  density-normalized, so it shows real composition, not the RSS-onset cliff */
  share_series: Record<string, number>;
}

export interface TopPatent {
  pub: string;
  cites: number;
  title: string;
  year?: string | null;
}

export interface TechPayload {
  lead_time: Record<TierName, TierLead>;
  lead_years_science_vs_market: number | null;
  lead_years_patent_vs_market: number | null;
  patent_dynamics: {
    hub?: TopPatent;
    /** top-cited patents in the domain, browsable (forward citations) */
    top_patents?: TopPatent[];
    cycle_time_years?: number;
    cycle_cov?: number;
    /** blueprint §2.1.1 index: immediate importance × 1/cycle-time */
    tir_index?: number;
    /** predicted Technology Improvement Rate, %/yr — index calibrated on
     *  published Benson–Magee domain rates */
    tir_pct?: number;
    immediate_importance?: number;
  };
  convergence: { cpc: string; title: string; total: number; recent_share: number }[];
}

export interface TechInsight {
  symbol: string;
  name: string;
  vertical: string;
  payload: TechPayload;
  updated_at: string;
}

export async function getTechnologies(): Promise<TechInsight[]> {
  return q<TechInsight>(
    `SELECT symbol, name, vertical, payload, updated_at::text
     FROM cpc_insights
     ORDER BY (payload->'patent_dynamics'->>'cycle_time_years')::float ASC NULLS LAST, name`
  );
}

export async function getTechnology(symbol: string): Promise<TechInsight | null> {
  return q1<TechInsight>(
    `SELECT symbol, name, vertical, payload, updated_at::text
     FROM cpc_insights WHERE symbol = $1`,
    [symbol.toUpperCase()]
  );
}

/** Espacenet link for a dashed publication number (e.g. CN-105918786-A). */
export function espacenetUrl(pub: string): string {
  return `https://worldwide.espacenet.com/patent/search?q=pn%3D%22${pub.replace(/-/g, "")}%22`;
}

/**
 * Technology context of a single trend (#28): its persisted nearest CPC
 * subclasses from signal_cpc (embedding projection, confident matches only),
 * enriched with the curated insight payload where the class is one of the
 * Technology Explorer axes.
 */

/** Same projection gate as the pipeline (assign_cpc.CONFIDENT_DIST). */
const CPC_CONFIDENT_DIST = 0.55;

export interface TrendTechMatch {
  symbol: string;
  /** raw CPC caption (ALL-CAPS legalese) — use prettyCpcTitle() for display */
  title: string;
  dist: number;
  /** curated display name when this class is a Technology Explorer axis */
  curated_name: string | null;
  tir_pct: number | null;
  lead_years: number | null;
  /** corpus signals confidently mapped to the same class */
  siblings: number;
}

export async function getTrendTechContext(trendId: number): Promise<TrendTechMatch[]> {
  // The block is a Foresight teaser, so every row must carry Foresight value:
  // we project the trend's own embedding onto the CURATED technology axes only
  // (the ~two dozen Technology Explorer classes that have lead-time + improve-
  // ment-rate data and a page to click through to). A raw nearest-neighbour can
  // land on a generic "Mixing" or "Crushing" class — semantically close but
  // insight-free — so we deliberately don't surface those here. signal_cpc (raw
  // top-3) stays the substrate for cross-tier fusion; this is the display path.
  try {
    return await q<TrendTechMatch>(
      // lead_years now comes from the honest cpc_leadtime_summary and is shown
      // ONLY where reliable=1 (both tiers genuinely emerged in-window). The old
      // cpc_insights payload lead could report a 13y "lead" for an established
      // field like dairy — a corpus-depth artifact — which we no longer surface.
      `SELECT d.symbol, d.title, (t.embedding_1024 <=> d.embedding_1024)::float AS dist,
              i.name AS curated_name,
              (i.payload->'patent_dynamics'->>'tir_pct')::float AS tir_pct,
              CASE WHEN ls.reliable = 1 THEN ls.lead_science_vs_market END AS lead_years,
              (SELECT COUNT(*) FROM signal_cpc x
                WHERE x.cpc = d.symbol AND x.dist < $2)::int AS siblings
       FROM trends t
       JOIN cpc_definitions d ON d.embedding_1024 IS NOT NULL
       JOIN cpc_insights i ON i.symbol = d.symbol
       LEFT JOIN cpc_leadtime_summary ls ON ls.cpc = d.symbol
       WHERE t.id = $1 AND t.embedding_1024 IS NOT NULL
         AND (t.embedding_1024 <=> d.embedding_1024) < $2
       ORDER BY t.embedding_1024 <=> d.embedding_1024
       LIMIT 3`,
      [trendId, CPC_CONFIDENT_DIST]
    );
  } catch {
    // table/column absent (pre-migration deploys) → article renders without it
    return [];
  }
}
