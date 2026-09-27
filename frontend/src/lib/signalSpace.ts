import { FTS_VECTOR } from "./db";
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

// ------------------------------------------------------------------- search

/** trend ids of a run in blob order, kept per run (a run never changes). */
const idCache = new Map<number, number[]>();

async function runTrendIds(runId: number): Promise<number[] | null> {
  const hit = idCache.get(runId);
  if (hit) return hit;
  const blob = await getSpaceBlob(runId);
  if (!blob) return null;
  const n = Math.floor(blob.length / 16);
  const ids = new Array<number>(n);
  for (let i = 0; i < n; i++) ids[i] = blob.readUInt32LE(i * 16 + 12);
  if (idCache.size >= 2) idCache.delete(idCache.keys().next().value as number);
  idCache.set(runId, ids);
  return ids;
}

export interface SpaceSearchResult {
  q: string;
  /** Point indices (positions in the blob), ascending. */
  indices: number[];
}

/**
 * Which points of a run match `query`. Same full-text search as the feed's
 * ?q= (title + summary + tags, `websearch_to_tsquery`, so "solar panel" needs
 * both words, a quoted phrase needs the phrase, -word excludes), restricted to
 * the run's own signals. Measured 27.09. on the 108k cloud: 0.12-0.57 s.
 */
export async function searchSpace(runId: number, query: string): Promise<SpaceSearchResult | null> {
  const ids = await runTrendIds(runId);
  if (!ids) return null;
  const rows = await q<{ id: number }>(
    `SELECT id FROM trends WHERE id = ANY($1::int[]) AND ${FTS_VECTOR} @@ websearch_to_tsquery('english', $2)`,
    [ids, query]
  );
  const pos = new Map<number, number>();
  ids.forEach((id, i) => pos.set(id, i));
  const indices = rows
    .map((r) => pos.get(Number(r.id)))
    .filter((i): i is number => i !== undefined)
    .sort((a, b) => a - b);
  return { q: query, indices };
}
