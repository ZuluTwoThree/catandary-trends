import Database from "better-sqlite3";
import path from "path";

/**
 * Read access to the persisted foresight artifacts (foresight_runs /
 * foresight_clusters, written by pipeline/foresight_snapshot.py).
 * Batch layer computes, frontend reads — no clustering in request paths.
 * All functions degrade gracefully (null / []) while the tables don't exist.
 */

const DB_PATH =
  process.env.DATABASE_PATH ||
  path.join(process.cwd(), "..", "data", "catandary.db");

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
export function getLatestClusterRun(
  scope: string
): { run: ForesightRun; clusters: ForesightCluster[] } | null {
  let db: Database.Database;
  try {
    db = new Database(DB_PATH, { readonly: true });
  } catch {
    return null;
  }
  try {
    db.pragma("journal_mode = WAL");
    const run = db
      .prepare(
        "SELECT * FROM foresight_runs WHERE scope = ? ORDER BY id DESC LIMIT 1"
      )
      .get(scope) as ForesightRun | undefined;
    if (!run) return null;

    const rows = db
      .prepare(
        "SELECT * FROM foresight_clusters WHERE run_id = ? ORDER BY size DESC"
      )
      .all(run.id) as Record<string, unknown>[];

    // Evidence one click away: resolve representative signals to their
    // original source links in one query.
    const repIds = [
      ...new Set(
        rows.flatMap((r) => parseJson<number[]>(r.rep_trend_ids, []))
      ),
    ];
    const repMap = new Map<number, ClusterRep>();
    if (repIds.length > 0) {
      const ph = repIds.map(() => "?").join(",");
      const reps = db
        .prepare(
          `SELECT id, title_en, source_url, source_name FROM trends WHERE id IN (${ph})`
        )
        .all(...repIds) as Array<{
        id: number;
        title_en: string;
        source_url: string | null;
        source_name: string | null;
      }>;
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
    return null; // tables not migrated yet → page renders its empty state
  } finally {
    db.close();
  }
}

/** Scopes that actually have persisted runs (drives the tab row). */
export function getClusterScopes(): string[] {
  let db: Database.Database;
  try {
    db = new Database(DB_PATH, { readonly: true });
  } catch {
    return [];
  }
  try {
    const rows = db
      .prepare("SELECT DISTINCT scope FROM foresight_runs ORDER BY scope")
      .all() as Array<{ scope: string }>;
    return rows.map((r) => r.scope);
  } catch {
    return [];
  } finally {
    db.close();
  }
}
