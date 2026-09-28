import { FTS_VECTOR } from "./db";
import { q, q1 } from "./pg";
import { collectRecords, recordIds, type CloudMeta, type CloudNest } from "./spaceCloud";

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
      "SELECT id, created_at::text AS created_at, n_points, n_all, per_month, months, coord_range, " +
        "pca_variance, neighbour_keep, trustworthiness, duration_s, emerging_run_id, nests, codes, " +
        "layout, alt_layout, alt_coord_range, alt_nests, alt_pca_variance, alt_neighbour_keep, " +
        "alt_trustworthiness " +
        "FROM signal_space_runs ORDER BY id DESC LIMIT 1"
    );
    if (!r) return null;
    const codes = parseJson<{ tier?: Record<string, string>; vertical?: Record<string, string> }>(r.codes, {});
    return {
      runId: Number(r.id),
      createdAt: String(r.created_at),
      nPoints: Number(r.n_points ?? 0),
      nAll: Number(r.n_all ?? 0),
      perMonth: Number(r.per_month ?? 0),
      months: parseJson<string[]>(r.months, []),
      coordRange: Number(r.coord_range ?? 1),
      pcaVariance: r.pca_variance == null ? null : Number(r.pca_variance),
      neighbourKeep: Number(r.neighbour_keep ?? 0),
      trustworthiness: Number(r.trustworthiness ?? 0),
      durationS: Number(r.duration_s ?? 0),
      emergingRunId: r.emerging_run_id == null ? null : Number(r.emerging_run_id),
      nests: parseJson<CloudNest[]>(r.nests, []),
      tierCodes: codes.tier ?? {},
      verticalCodes: codes.vertical ?? {},
      // runs before 28.09. had one layout, the one now called "style"
      layout: r.layout ? String(r.layout) : "style",
      alt: r.alt_layout
        ? {
            layout: String(r.alt_layout),
            coordRange: Number(r.alt_coord_range ?? 1),
            nests: parseJson<[number, number, number][]>(r.alt_nests, []),
            pcaVariance: r.alt_pca_variance == null ? null : Number(r.alt_pca_variance),
            neighbourKeep: Number(r.alt_neighbour_keep ?? 0),
            trustworthiness: Number(r.alt_trustworthiness ?? 0),
          }
        : null,
    };
  } catch {
    return null;
  }
}

/** The packed sample points of one run, in its default or its second layout. */
export async function getSpaceBlob(runId: number, alt = false): Promise<Buffer | null> {
  const r = await q1<{ points: Buffer | null }>(
    `SELECT ${alt ? "alt_points" : "points"} AS points FROM signal_space_runs WHERE id = $1`,
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

/**
 * Every signal of a run's window, placed into its cloud (all_points, sorted by
 * trend id) — kept in memory per run: ~24 MB for 1.5M signals, read once.
 */
const placedCache = new Map<string, { buf: Uint8Array; ids: Uint32Array }>();

async function placedSignals(
  runId: number,
  alt = false
): Promise<{ buf: Uint8Array; ids: Uint32Array } | null> {
  const key = `${runId}:${alt ? "alt" : ""}`;
  const hit = placedCache.get(key);
  if (hit) return hit;
  const r = await q1<{ all_points: Buffer | null }>(
    `SELECT ${alt ? "alt_all_points" : "all_points"} AS all_points FROM signal_space_runs WHERE id = $1`,
    [runId]
  );
  if (!r?.all_points) return null;
  const buf = new Uint8Array(r.all_points.buffer, r.all_points.byteOffset, r.all_points.byteLength);
  const entry = { buf, ids: recordIds(buf) };
  // two layouts of the latest run (~24 MB each), plus room for the previous run
  if (placedCache.size >= 4) placedCache.delete(placedCache.keys().next().value as string);
  placedCache.set(key, entry);
  return entry;
}

/** Every placed signal of a run, same 16-byte layout as the sample. */
export async function getAllBlob(runId: number, alt = false): Promise<Uint8Array | null> {
  return (await placedSignals(runId, alt))?.buf ?? null;
}

export interface SpaceSearchResult {
  q: string;
  /** Packed 16-byte records of the matches that have a place in the cloud. */
  records: Uint8Array;
  matches: number;
  /** Matches outside the cloud's time window (older or undated). */
  outside: number;
  /** Matches per source, before de-duplication. */
  bySource: { text: number; research: number; patents: number };
  /** Sources that failed (e.g. hit the statement timeout) — the result is partial. */
  failed: string[];
}

/**
 * All matches for `query` in the whole corpus, placed in the cloud. Three
 * sources, queried in parallel, each allowed to fail on its own:
 *
 *   text      title + summary + tags (idx_trends_fts) — the feed's ?q= search
 *   research  title + abstract of research signals (research_signals.tsv)
 *   patents   title + abstract of patent signals (patent_search.tsv)
 *
 * Same syntax everywhere (websearch_to_tsquery): words must all occur, a quoted
 * phrase must occur as a phrase, -word excludes. Measured 27.09. on the whole
 * corpus: text and research under 1 s, patents 0.2–7 s ("battery").
 */
export async function searchSpace(
  runId: number,
  query: string,
  alt = false
): Promise<SpaceSearchResult | null> {
  const placed = await placedSignals(runId, alt);
  if (!placed) return null;
  const ts = "websearch_to_tsquery('english', $1)";
  const [text, research, patents] = await Promise.allSettled([
    q<{ id: number }>(
      `SELECT id FROM trends WHERE status IN ('signal','published') AND ${FTS_VECTOR} @@ ${ts}`,
      [query]
    ),
    q<{ id: number }>(`SELECT trend_id AS id FROM research_signals WHERE tsv @@ ${ts}`, [query]),
    q<{ id: number }>(
      "SELECT t.id FROM patent_search ps JOIN raw_entries r ON r.pub_number = ps.pub_number " +
        `JOIN trends t ON t.raw_entry_id = r.id WHERE ps.tsv @@ ${ts}`,
      [query]
    ),
  ]);
  const ids = new Set<number>();
  const failed: string[] = [];
  const count = (name: string, res: PromiseSettledResult<{ id: number }[]>): number => {
    if (res.status === "rejected") {
      failed.push(name);
      return 0;
    }
    for (const r of res.value) ids.add(Number(r.id));
    return res.value.length;
  };
  const bySource = {
    text: count("text", text),
    research: count("research abstracts", research),
    patents: count("patent abstracts", patents),
  };
  const { records, found, missing } = collectRecords(placed.buf, placed.ids, ids);
  return { q: query, records, matches: found, outside: missing, bySource, failed };
}
