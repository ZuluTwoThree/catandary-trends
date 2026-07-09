import { q, q1 } from "./pg";

/**
 * Read access to the persisted foresight artifacts (foresight_runs /
 * foresight_clusters, written by pipeline/foresight_snapshot.py).
 * Batch layer computes, frontend reads — no clustering in request paths.
 * All functions degrade gracefully (null / []) if the tables are missing.
 */

export interface ClusterRep {
  id: number;
  title: string;
  source_url: string | null;
  source_name: string | null;
}

export interface ForesightCluster {
  id: number;
  cluster_idx: number;
  label: string;
  size: number;
  cohesion: number;
  mega_trend: string | null;
  mega_purity: number;
  verticals: string[];
  top_tags: string[];
  n_sources: number;
  momentum: "rising" | "stable" | "declining" | "unknown";
  sov_delta_pp: number;
  tier: string | null;
  reps: ClusterRep[];
  monthly_series: { m: string; n: number; share: number }[];
}

export interface ForesightRun {
  id: number;
  scope: string;
  tier: string | null;
  k: number;
  signals: number;
  first_month: string | null;
  last_month: string | null;
  created_at: string;
}

function parseJson<T>(raw: unknown, fallback: T): T {
  if (typeof raw !== "string" || !raw) return fallback;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

/** Latest persisted run for a scope ('global' | 'vertical:FOOD' | …). */
export async function getLatestClusterRun(
  scope: string
): Promise<{ run: ForesightRun; clusters: ForesightCluster[] } | null> {
  try {
    const run = await q1<ForesightRun>(
      "SELECT id, scope, tier, k, signals, first_month, last_month, created_at::text as created_at " +
        "FROM foresight_runs WHERE scope = $1 ORDER BY id DESC LIMIT 1",
      [scope]
    );
    if (!run) return null;

    const rows = await q("SELECT * FROM foresight_clusters WHERE run_id = $1 ORDER BY size DESC", [
      run.id,
    ]);

    // Evidence one click away: resolve representative signals to their
    // original source links in one query.
    const repIds = [
      ...new Set(rows.flatMap((r) => parseJson<number[]>(r.rep_trend_ids, []))),
    ];
    const repMap = new Map<number, ClusterRep>();
    if (repIds.length > 0) {
      const reps = await q<{
        id: number;
        title_en: string;
        source_url: string | null;
        source_name: string | null;
      }>(
        "SELECT id, title_en, source_url, source_name FROM trends WHERE id = ANY($1::int[])",
        [repIds]
      );
      for (const r of reps) {
        repMap.set(r.id, {
          id: r.id,
          title: r.title_en,
          source_url: r.source_url,
          source_name: r.source_name,
        });
      }
    }

    const clusters: ForesightCluster[] = rows.map((r) => ({
      id: r.id as number,
      cluster_idx: r.cluster_idx as number,
      label: (r.label as string) || `Cluster ${r.cluster_idx}`,
      size: r.size as number,
      cohesion: r.cohesion as number,
      mega_trend: (r.mega_trend as string) || null,
      mega_purity: (r.mega_purity as number) ?? 0,
      verticals: parseJson<string[]>(r.verticals, []),
      top_tags: parseJson<string[]>(r.top_tags, []),
      n_sources: (r.n_sources as number) ?? 0,
      momentum: (r.momentum as ForesightCluster["momentum"]) || "unknown",
      sov_delta_pp: (r.sov_delta_pp as number) ?? 0,
      tier: (r.tier as string) || null,
      reps: parseJson<number[]>(r.rep_trend_ids, [])
        .map((id) => repMap.get(id))
        .filter((x): x is ClusterRep => Boolean(x)),
      monthly_series: parseJson<{ m: string; n: number; share: number }[]>(
        r.monthly_series,
        []
      ),
    }));
    return { run, clusters };
  } catch {
    return null; // tables not present yet → page renders its empty state
  }
}

/* ----------------------------- Lead-time layer ---------------------------- */
/**
 * Cross-tier lead-time (#9/#2): the four lead-time tiers (research → patents →
 * funding → market) projected onto the shared CPC axis, read from the batch-
 * built cpc_tier_series / cpc_tier_totals / cpc_leadtime_summary. SoV (share of
 * a tier's yearly volume) is the honest unit — it normalizes out each tier's
 * different corpus depth, so the curves are comparable. A headline lead-time is
 * surfaced ONLY where the corpus can prove it (reliable = genuine in-window
 * emergence in both compared tiers); otherwise we show the curves, no number.
 */

export type TierName = "science" | "patent" | "funding" | "market";

export interface LeadTech {
  cpc: string;
  title: string;
  curated_name: string | null;
  lead_science_vs_market: number | null;
  science_takeoff: number | null;
  market_takeoff: number | null;
  reliable: boolean;
  science_n: number;
  market_n: number;
}

/** Cleaned display name for a CPC — curated Explorer name, else tidied caption. */
export function cpcDisplayName(title: string, curated: string | null): string {
  if (curated) return curated;
  let t = title.split(/[;(]/)[0].replace(/,?\s*NOT OTHERWISE PROVIDED FOR/gi, "");
  t = t.replace(/\s+/g, " ").trim().toLowerCase();
  t = t.charAt(0).toUpperCase() + t.slice(1);
  // restore bracketed acronyms: "[uav]" → "[UAV]"
  return t.replace(/\[([^\]]+)\]/g, (_, a: string) => `[${a.toUpperCase()}]`);
}

/** Reliable emerging technologies with a credible research→market lead. */
export async function getLeadTimeTechnologies(limit = 12): Promise<LeadTech[]> {
  try {
    const rows = await q<LeadTech>(
      `SELECT s.cpc, d.title, i.name AS curated_name,
              s.lead_science_vs_market, s.science_takeoff, s.market_takeoff,
              (s.reliable = 1) AS reliable, s.science_n, s.market_n
       FROM cpc_leadtime_summary s
       JOIN cpc_definitions d ON d.symbol = s.cpc
       LEFT JOIN cpc_insights i ON i.symbol = s.cpc
       WHERE s.reliable = 1 AND s.lead_science_vs_market > 0
       -- curated Explorer axes first (recognizable names), then by market
       -- prominence — so the default view opens on a technology people know
       ORDER BY (i.name IS NULL), s.market_n DESC
       LIMIT $1`,
      [limit]
    );
    return rows;
  } catch {
    return [];
  }
}

export interface TierPoint { year: number; sov: number; n: number }

/** Per-tier yearly SoV curve for one CPC (SoV = share of that tier's year). */
export async function getTierCurves(
  cpc: string
): Promise<{ tiers: Record<TierName, TierPoint[]>; lead: LeadTech | null }> {
  const empty = { science: [], patent: [], funding: [], market: [] } as Record<
    TierName,
    TierPoint[]
  >;
  try {
    const rows = await q<{ tier: TierName; year: number; sov: number; n: number }>(
      `SELECT s.tier, s.year, (s.n::float / NULLIF(t.total, 0)) AS sov, s.n
       FROM cpc_tier_series s
       JOIN cpc_tier_totals t ON t.tier = s.tier AND t.year = s.year
       WHERE s.cpc = $1 AND s.year >= 1995
       ORDER BY s.year`,
      [cpc.toUpperCase()]
    );
    const tiers = { science: [], patent: [], funding: [], market: [] } as Record<
      TierName,
      TierPoint[]
    >;
    for (const r of rows) {
      if (r.tier in tiers && r.sov != null)
        tiers[r.tier].push({ year: r.year, sov: r.sov, n: r.n });
    }
    const lead = await q1<LeadTech>(
      `SELECT s.cpc, d.title, i.name AS curated_name, s.lead_science_vs_market,
              s.science_takeoff, s.market_takeoff, (s.reliable = 1) AS reliable,
              s.science_n, s.market_n
       FROM cpc_leadtime_summary s JOIN cpc_definitions d ON d.symbol = s.cpc
       LEFT JOIN cpc_insights i ON i.symbol = s.cpc WHERE s.cpc = $1`,
      [cpc.toUpperCase()]
    );
    return { tiers: rows.length ? tiers : empty, lead };
  } catch {
    return { tiers: empty, lead: null };
  }
}

/** Scopes that actually have persisted runs (drives the tab row). */
export async function getClusterScopes(): Promise<string[]> {
  try {
    const rows = await q<{ scope: string }>(
      "SELECT DISTINCT scope FROM foresight_runs ORDER BY scope"
    );
    return rows.map((r) => r.scope);
  } catch {
    return [];
  }
}
