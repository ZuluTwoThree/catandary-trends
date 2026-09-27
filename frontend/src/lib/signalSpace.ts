import { q, q1 } from "./pg";
import type { CloudMeta, CloudNest } from "./spaceCloud";

/**
 * Read access to the signal cloud (signal_space_runs, written by
 * pipeline/signal_space.py). The page gets the metadata server-side; the
 * 1.7 MB point blob is fetched by the browser from
 * /api/foresight/space/points only when the Cloud view is opened.
 */

function parseJson<T>(raw: unknown, fallback: T): T {
  if (raw && typeof raw === "object") return raw as T;
  if (typeof raw !== "string" || !raw) return fallback;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

/** Latest run without its blob, or null when there is none (or no table yet). */
export async function getLatestSpaceRun(): Promise<CloudMeta | null> {
  try {
    const r = await q1<Record<string, unknown>>(
      "SELECT id, created_at::text AS created_at, n_points, per_month, months, coord_range, " +
        "pca_variance, neighbour_keep, trustworthiness, duration_s, emerging_run_id, nests, codes " +
        "FROM signal_space_runs ORDER BY id DESC LIMIT 1"
    );
    if (!r) return null;
    const codes = parseJson<{ tier?: Record<string, string>; vertical?: Record<string, string> }>(r.codes, {});
    return {
      runId: Number(r.id),
      createdAt: String(r.created_at),
      nPoints: Number(r.n_points ?? 0),
      perMonth: Number(r.per_month ?? 0),
      months: parseJson<string[]>(r.months, []),
      coordRange: Number(r.coord_range ?? 1),
      pcaVariance: Number(r.pca_variance ?? 0),
      neighbourKeep: Number(r.neighbour_keep ?? 0),
      trustworthiness: Number(r.trustworthiness ?? 0),
      durationS: Number(r.duration_s ?? 0),
      emergingRunId: r.emerging_run_id == null ? null : Number(r.emerging_run_id),
      nests: parseJson<CloudNest[]>(r.nests, []),
      tierCodes: codes.tier ?? {},
      verticalCodes: codes.vertical ?? {},
    };
  } catch {
    return null;
  }
}

/** The packed points of one run. */
export async function getSpaceBlob(runId: number): Promise<Buffer | null> {
  const r = await q1<{ points: Buffer | null }>(
    "SELECT points FROM signal_space_runs WHERE id = $1",
    [runId]
  );
  return r?.points ?? null;
}

export interface SpacePoint {
  id: number;
  title: string;
  source_name: string | null;
  source_url: string | null;
  slug: string | null;
  status: string | null;
  date: string | null;
  vertical: string | null;
  signal_type: string | null;
}

/** What the panel shows for a clicked point. */
export async function getSpacePoint(id: number): Promise<SpacePoint | null> {
  const rows = await q<SpacePoint>(
    "SELECT t.id, t.title_en AS title, t.source_name, t.source_url, t.slug, t.status, " +
      "to_char(COALESCE(r.published_date, t.sort_date), 'YYYY-MM-DD') AS date, " +
      "t.primary_vertical AS vertical, t.trend_signal_type AS signal_type " +
      "FROM trends t JOIN raw_entries r ON r.id = t.raw_entry_id WHERE t.id = $1",
    [id]
  );
  return rows[0] ?? null;
}
