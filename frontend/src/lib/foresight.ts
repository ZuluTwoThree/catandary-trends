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
