import { FTS_VECTOR } from "./db";
import { getPool, q, q1 } from "./pg";
import { annLiteral, embedQuery } from "./queryEmbedding";
import {
  annotateMatches,
  collectRecords,
  HISTORY_ID_BASE,
  recordIds,
  type CloudFlows,
  type CloudMeta,
  type CloudNest,
  type SearchMode,
} from "./spaceCloud";

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
        "alt_trustworthiness, n_history, n_history_all, flows " +
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
      nHistory: Number(r.n_history ?? 0),
      nHistoryAll: Number(r.n_history_all ?? 0),
      flows: parseJson<CloudFlows | null>(r.flows, null),
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
  /** Points of the history sample only (id >= HISTORY_ID_BASE). */
  history?: { layer: string; cited: boolean; weight: number | null };
}

/** A point of the history sample: the patent (earliest publication of its family)
 *  or the research work it stands for, with the layer it was drawn in. */
async function getHistoryPoint(id: number): Promise<SpacePoint | null> {
  const rows = await q<SpacePoint & { layer: string; cited: boolean; weight: number | null }>(
    "SELECT h.id + $2::bigint AS id, " +
      "COALESCE(r.title, rc.title, h.ref) AS title, " +
      "CASE h.tier WHEN 'patent' THEN 'Patent (history sample)' ELSE 'Research (history sample)' END AS source_name, " +
      "COALESCE(r.url, rc.doi, 'https://openalex.org/' || h.ref) AS source_url, NULL AS slug, " +
      "'history' AS status, " +
      "COALESCE(to_char(r.published_date, 'YYYY-MM-DD'), to_char(rc.published, 'YYYY-MM-DD')) AS date, " +
      "NULL AS vertical, CASE h.tier WHEN 'patent' THEN 'patent' ELSE 'research' END AS signal_type, " +
      "h.layer, h.cited, h.weight " +
      "FROM history_items h LEFT JOIN raw_entries r ON r.id = h.raw_entry_id " +
      "LEFT JOIN research_corpus rc ON h.tier = 'science' AND rc.id = h.ref WHERE h.id = $1",
    [id - HISTORY_ID_BASE, HISTORY_ID_BASE]
  );
  const r = rows[0];
  if (!r) return null;
  const { layer, cited, weight, ...p } = r;
  return { ...p, id: Number(p.id), history: { layer, cited, weight: weight == null ? null : Number(weight) } };
}

/** What the panel shows for a clicked point. */
export async function getSpacePoint(id: number): Promise<SpacePoint | null> {
  if (id >= HISTORY_ID_BASE) return getHistoryPoint(id);
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
  mode: SearchMode;
  /** Packed 16-byte records of the matches that have a place in the cloud. */
  records: Uint8Array;
  /** Per record: cosine to the query (0 for keyword-only matches) and MATCH_* flags. */
  sim: Float32Array;
  match: Uint8Array;
  matches: number;
  /** Matches outside the cloud's time window (older or undated). */
  outside: number;
  /** Matches per source, before de-duplication; `meaning` = nearest signals returned. */
  bySource: { text: number; research: number; patents: number; meaning: number };
  /** Placed matches by origin: keyword only, vector only, both. */
  kinds: { text: number; meaning: number; both: number };
  /** Similarity of the nearest and of the last returned neighbour, or null. */
  simRange: [number, number] | null;
  /** Sources that failed (e.g. hit the statement timeout) — the result is partial. */
  failed: string[];
}

/** pgvector 0.6: an HNSW scan returns at most ef_search rows (max 1000). */
export const MEANING_MAX = 1000;
export const MEANING_CHOICES = [250, 500, 1000] as const;

/**
 * The n signals nearest to the query vector (cosine on embedding_1024, the
 * HNSW index over every row), restricted to what the cloud draws. A ranking,
 * not a set: something is always "nearest", even for nonsense.
 */
async function nearestSignals(vec: number[], n: number): Promise<Map<number, number>> {
  const client = await getPool().connect();
  try {
    await client.query("BEGIN");
    // ef_search bounds how many rows the scan can return; the status filter
    // drops a few (drafts, rejected), so ask for some slack
    await client.query(`SET LOCAL hnsw.ef_search = ${Math.min(MEANING_MAX, Math.max(400, 2 * n))}`);
    const res = await client.query(
      "SELECT id, 1 - (embedding_1024 <=> $1::vector) AS s FROM trends " +
        "WHERE status IN ('signal','published') ORDER BY embedding_1024 <=> $1::vector LIMIT $2",
      [annLiteral(vec), n]
    );
    await client.query("COMMIT");
    return new Map(res.rows.map((r: { id: number; s: number }) => [Number(r.id), Number(r.s)]));
  } catch (e) {
    await client.query("ROLLBACK").catch(() => undefined);
    throw e;
  } finally {
    client.release();
  }
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
 *
 * mode "meaning" / "both" adds (or uses only) the vector search: the query is
 * embedded on the CPU embedder and its `meaningN` nearest signals join the
 * matches (28.09.; measured 0.15 s embedding + 0.4–1.1 s HNSW for 1,000).
 */
export async function searchSpace(
  runId: number,
  query: string,
  alt = false,
  mode: SearchMode = "text",
  meaningN = MEANING_MAX
): Promise<SpaceSearchResult | null> {
  const placed = await placedSignals(runId, alt);
  if (!placed) return null;
  const ts = "websearch_to_tsquery('english', $1)";
  const useText = mode !== "meaning";
  const useMeaning = mode !== "text";
  const none = Promise.resolve([] as { id: number }[]);
  const meaningP: Promise<Map<number, number>> = useMeaning
    ? embedQuery(query).then((v) => {
        if (!v) throw new Error("embedder unreachable");
        return nearestSignals(v, Math.min(MEANING_MAX, Math.max(1, meaningN)));
      })
    : Promise.resolve(new Map());
  const [text, research, patents, meaning] = await Promise.allSettled([
    useText
      ? q<{ id: number }>(
          `SELECT id FROM trends WHERE status IN ('signal','published') AND ${FTS_VECTOR} @@ ${ts}`,
          [query]
        )
      : none,
    useText
      ? q<{ id: number }>(`SELECT trend_id AS id FROM research_signals WHERE tsv @@ ${ts}`, [query])
      : none,
    useText
      ? q<{ id: number }>(
          "SELECT t.id FROM patent_search ps JOIN raw_entries r ON r.pub_number = ps.pub_number " +
            `JOIN trends t ON t.raw_entry_id = r.id WHERE ps.tsv @@ ${ts}`,
          [query]
        )
      : none,
    meaningP,
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
  const counted = {
    text: count("text", text),
    research: count("research abstracts", research),
    patents: count("patent abstracts", patents),
  };
  const textIds = new Set(ids); // keyword matches only, before the neighbours join
  let near = new Map<number, number>();
  if (meaning.status === "rejected") {
    failed.push(
      String(meaning.reason).includes("embedder") ? "meaning (embedder :8091 unreachable)" : "meaning"
    );
  } else {
    near = meaning.value;
    for (const id of near.keys()) ids.add(id);
  }
  const bySource = { ...counted, meaning: near.size };
  const { records, found, missing } = collectRecords(placed.buf, placed.ids, ids);
  const { sim, match, counts } = annotateMatches(records, textIds, near);
  const sims = [...near.values()];
  const simRange: [number, number] | null = sims.length ? [Math.max(...sims), Math.min(...sims)] : null;
  return {
    q: query,
    mode,
    records,
    sim,
    match,
    matches: found,
    outside: missing,
    bySource,
    kinds: counts,
    simRange,
    failed,
  };
}
