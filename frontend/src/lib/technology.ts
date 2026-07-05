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
}

export interface TechPayload {
  lead_time: Record<TierName, TierLead>;
  lead_years_science_vs_market: number | null;
  lead_years_patent_vs_market: number | null;
  patent_dynamics: {
    hub?: { pub: string; cites: number; title: string };
    cycle_time_years?: number;
    cycle_cov?: number;
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
