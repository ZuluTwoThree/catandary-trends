import { cached } from "./db";
import { q, q1 } from "./pg";

/**
 * Read access to the emerging-nest artifacts (emerging_runs / emerging_nests,
 * written by pipeline/emerging_snapshot.py).
 *
 * Second layer next to the clusters, not a replacement (Owner 2026-09-15): the
 * cluster layer partitions everything into ~28 subject areas, this one keeps
 * only small dense pockets of the recent slice and dates each against the whole
 * archive. The number that matters here is not share of attention but age.
 */

export interface NestRep {
  id: number;
  title: string;
  source_url: string | null;
  source_name: string | null;
  slug: string | null;
  status: string | null;
  date: string | null;
}

export type TierName = "science" | "patent" | "funding" | "market";

export interface TierFact {
  first_month: string | null;
  age_months: number | null;
  hits: number;
  hits_recent: number;
  share_of_nest: number;
}

export interface EmergingNest {
  id: number;
  /** Deterministic label from the pocket's own tags or titles. */
  label: string;
  /** Model-written name, or null when it did not survive the grounding check.
   *  Both are shown: the name reads, the label is what was measured. */
  llm_label: string | null;
  llm_label_note: string | null;
  size: number;
  cohesion: number;
  n_sources: number;
  top_source: string | null;
  top_source_share: number;
  /** Share of members that ever passed the classification stages. 0 means the
   *  pocket is pure bulk-ingested signal that no stage of the pipeline read. */
  tagged_share: number;
  /** Share of the pocket carried by sources that were already being read two
   *  years ago. Near zero means its age is a fact about our subscriptions. */
  established_share: number;
  verticals: string[];
  top_tags: string[];
  /** Nest terms that were rare in the corpus two to three years ago. */
  new_terms: string[];
  /** First month with at least three lookalikes anywhere in the archive. */
  first_month: string | null;
  age_months: number | null;
  hits_total: number;
  hits_recent: number;
  /** Recent share of the nest's lookalikes over the corpus's recent share.
   *  1.0 = spread like the archive, 4.5 = every trace of it is from now. */
  novelty_lift: number | null;
  /** Recent monthly rate over the preceding months, both corpus-normalised.
   *  null = the nest had no lookalikes at all in the earlier window. */
  accel: number | null;
  history_months: string[];
  history_hits: number[];
  /** The same pocket dated separately on research, patents, funding and the
   *  market. Owner 2026-09-15: a science trend is not a market trend even when
   *  the topic is identical. */
  tiers: Partial<Record<TierName, TierFact>>;
  tier_order: TierName[];
  science_to_market_months: number | null;
  /** Distinct companies and brands named in the market-tier lookalikes.
   *  Only 13 % of trade-press rows carry an extracted actor, so this is a
   *  floor, never a census. */
  actors_early: number;
  actors_late: number;
  /** Domain runs of the discovery service: sub-group (1 = largest) and its name. */
  group_id: number | null;
  group_label: string | null;
  /** Dated by the research and patent calendar (pipeline/calendar_dating.py, 01.10.):
   *  how often the pocket's vocabulary appears per year in OpenAlex (from 2010) and the
   *  patent corpus (from 1990). Null for runs before that, and for non-domain runs. */
  calendar: CalendarDating | null;
  reps: NestRep[];
}

export interface CalendarSeries {
  first: number | null;
  /** first year = the corpus' first year in breadth, so the topic may be older */
  edge: boolean;
  takeoff: number | null;
  growth: number | null;
  total: number;
  years: number[];
  counts: number[];
  per_million: number[];
}

export interface CalendarDating {
  anchor: string[];
  phrases: string[];
  science?: CalendarSeries;
  patent?: CalendarSeries;
}

export interface EmergingRun {
  id: number;
  scope: string;
  since: string | null;
  window_days: number | null;
  signals: number;
  cells: number;
  nests: number;
  scanned: number;
  first_month: string | null;
  last_month: string | null;
  created_at: string;
  /** How a run was made — set by the live discovery service (mode "live"). */
  params: RunParams | null;
}

export interface RunParams {
  mode?: string;
  term?: string;
  also?: string[];
  window_months?: number;
  members_window?: number;
  members_archive?: number;
  in_pockets?: number;
  cohesion_quantile?: number;
}

function parseJson<T>(raw: unknown, fallback: T): T {
  if (Array.isArray(raw)) return raw as unknown as T;
  if (raw && typeof raw === "object") return raw as T;   // jsonb comes back parsed
  if (typeof raw !== "string" || !raw) return fallback;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

const RUN_COLUMNS =
  "SELECT id, scope, since, window_days, signals, cells, nests, scanned, " +
  "first_month, last_month, created_at::text AS created_at, params";

const NEST_COLUMNS =
  "SELECT id, label, llm_label, llm_label_note, size, cohesion, n_sources, " +
  "top_source, top_source_share, " +
  "tagged_share, established_share, verticals, top_tags, new_terms, " +
  "first_month, age_months, " +
  "hits_total, hits_recent, novelty_lift, accel, history_months, history_hits, " +
  "tiers, tier_order, science_to_market_months, actors_early, actors_late, " +
  "group_id, group_label, calendar, rep_trend_ids";

/** Latest persisted emerging run for a scope, newest pockets first. */
export async function getLatestEmergingRun(
  scope: string
): Promise<{ run: EmergingRun; nests: EmergingNest[] } | null> {
  try {
    const raw = await q1<EmergingRun>(
      RUN_COLUMNS + " FROM emerging_runs WHERE scope = $1 ORDER BY id DESC LIMIT 1",
      [scope]
    );
    if (!raw) return null;
    const run: EmergingRun = { ...raw, params: parseJson<RunParams | null>(raw.params, null) };
    const rows = await q(
      NEST_COLUMNS +
        " FROM emerging_nests WHERE run_id = $1 " +
        // lift saturates once every trace of a nest is recent, so size breaks
        // the tie rather than leaving the order to the planner
        "ORDER BY novelty_lift DESC NULLS LAST, size DESC",
      [run.id]
    );

    const repIds = [
      ...new Set(rows.flatMap((r) => parseJson<number[]>(r.rep_trend_ids, []))),
    ];
    const repMap = new Map<number, NestRep>();
    if (repIds.length > 0) {
      const reps = await q<{
        id: number;
        title_en: string;
        source_url: string | null;
        source_name: string | null;
        slug: string | null;
        status: string | null;
        date: string | null;
      }>(
        "SELECT t.id, t.title_en, t.source_url, t.source_name, t.slug, t.status, " +
          "to_char(COALESCE(r.published_date, t.sort_date), 'YYYY-MM-DD') AS date " +
          "FROM trends t JOIN raw_entries r ON r.id = t.raw_entry_id " +
          "WHERE t.id = ANY($1::int[])",
        [repIds]
      );
      for (const r of reps) {
        repMap.set(r.id, {
          id: r.id,
          title: r.title_en,
          source_url: r.source_url,
          source_name: r.source_name,
          slug: r.slug,
          status: r.status,
          date: r.date,
        });
      }
    }

    const nests: EmergingNest[] = rows.map((r) => ({
      id: r.id as number,
      label: (r.label as string) || "Nest",
      llm_label: (r.llm_label as string) || null,
      llm_label_note: (r.llm_label_note as string) || null,
      size: r.size as number,
      cohesion: (r.cohesion as number) ?? 0,
      n_sources: (r.n_sources as number) ?? 0,
      top_source: (r.top_source as string) || null,
      top_source_share: (r.top_source_share as number) ?? 0,
      tagged_share: (r.tagged_share as number) ?? 0,
      established_share: (r.established_share as number) ?? 0,
      verticals: parseJson<string[]>(r.verticals, []),
      top_tags: parseJson<string[]>(r.top_tags, []),
      new_terms: parseJson<string[]>(r.new_terms, []),
      first_month: (r.first_month as string) || null,
      age_months: r.age_months == null ? null : (r.age_months as number),
      hits_total: (r.hits_total as number) ?? 0,
      hits_recent: (r.hits_recent as number) ?? 0,
      novelty_lift: r.novelty_lift == null ? null : (r.novelty_lift as number),
      accel: r.accel == null ? null : (r.accel as number),
      history_months: parseJson<string[]>(r.history_months, []),
      history_hits: parseJson<number[]>(r.history_hits, []),
      tiers: parseJson<Partial<Record<TierName, TierFact>>>(r.tiers, {}),
      tier_order: parseJson<TierName[]>(r.tier_order, []),
      science_to_market_months:
        r.science_to_market_months == null ? null : (r.science_to_market_months as number),
      actors_early: (r.actors_early as number) ?? 0,
      actors_late: (r.actors_late as number) ?? 0,
      group_id: r.group_id == null ? null : (r.group_id as number),
      group_label: (r.group_label as string) || null,
      calendar: parseJson<CalendarDating | null>(r.calendar, null),
      reps: parseJson<number[]>(r.rep_trend_ids, [])
        .map((id) => repMap.get(id))
        .filter((x): x is NestRep => Boolean(x)),
    }));
    return { run, nests };
  } catch {
    return null; // tables not present yet → the page renders its empty state
  }
}

/**
 * Display names of the freely defined domains (pipeline/domains.py, domains.yaml):
 * key -> name, from the trained probes. Empty when none is trained yet.
 */
export async function getDomainNames(): Promise<Record<string, string>> {
  try {
    const rows = await q<{ key: string; name: string | null }>(
      "SELECT key, name FROM domain_probes ORDER BY key"
    );
    return Object.fromEntries(rows.map((r) => [r.key, r.name || r.key]));
  } catch {
    return {};
  }
}

/** Scopes that have a persisted emerging run (drives the tab row). */
export async function getEmergingScopes(): Promise<string[]> {
  try {
    const rows = await q<{ scope: string }>(
      "SELECT DISTINCT scope FROM emerging_runs ORDER BY scope"
    );
    return rows.map((r) => r.scope);
  } catch {
    return [];
  }
}

// ----------------------------------------------------------- signal-space view

export interface EmergingSpace {
  run: EmergingRun;
  nests: EmergingNest[];
  /** One 1024-dim centroid per nest, in the same order. Server-side only —
   *  225 KB of vectors have no business in a browser payload. */
  centroids: number[][];
  /** The month axis of the run (identical for every nest of a run). */
  months: string[];
  /** Corpus signals per month AS THE RUN SAW THEM (see getCorpusMonthly). */
  totals: number[];
  /** Sum of `totals` — compared against run.scanned on the page, so the
   *  normalisation states its own residual instead of implying exactness. */
  corpusRows: number;
}

/**
 * Corpus volume per month, reconstructed for the state the snapshot ran against.
 *
 * Same filter as pipeline/foresight.iter_signals (status, embedded, no future
 * dates) plus the run's vertical scope — tier scopes are deliberately NOT
 * filtered, because emerging_snapshot dates each pocket against the whole
 * corpus regardless of the scope it was found in.
 *
 * `asOf` is what makes this usable at all: bounded by trends.created_at, the
 * totals describe the corpus of the run. Against today's corpus every pocket
 * would appear to fade, since the newest months have grown by tens of thousands
 * of rows since the snapshot while the pockets' counts are frozen in it.
 */
export async function getCorpusMonthly(
  asOf: string,
  vertical: string | null
): Promise<Map<string, number>> {
  const key = `corpus-monthly:${asOf}:${vertical ?? "all"}`;
  return cached(key, 3_600_000, async () => {
    const params: unknown[] = [asOf];
    let scope = "";
    if (vertical) {
      params.push(vertical);
      scope = " AND t.primary_vertical = $2";
    }
    const rows = await q<{ m: string; n: string }>(
      "SELECT to_char(r.published_date, 'YYYY-MM') AS m, count(*) AS n " +
        "FROM trends t JOIN raw_entries r ON t.raw_entry_id = r.id " +
        "WHERE t.status IN ('signal','published') AND t.embedding_1024 IS NOT NULL " +
        "  AND r.published_date IS NOT NULL AND r.published_date <= CURRENT_TIMESTAMP " +
        "  AND t.created_at <= $1" +
        scope +
        " GROUP BY 1",
      params
    );
    return new Map(rows.map((r) => [r.m, Number(r.n)]));
  });
}

/** Centroids of a run, keyed by nest id. float32 little-endian, as written by
 *  numpy's tobytes() in pipeline/emerging_snapshot.py. */
async function getCentroids(runId: number): Promise<Map<number, number[]>> {
  const rows = await q<{ id: number; centroid: Buffer | null }>(
    "SELECT id, centroid FROM emerging_nests WHERE run_id = $1",
    [runId]
  );
  const out = new Map<number, number[]>();
  for (const r of rows) {
    if (!r.centroid || r.centroid.length < 4) continue;
    const n = Math.floor(r.centroid.length / 4);
    const view = new Float32Array(n);
    for (let i = 0; i < n; i++) view[i] = r.centroid.readFloatLE(i * 4);
    out.set(r.id, Array.from(view));
  }
  return out;
}

/** Everything the signal-space view needs for one scope, or null when the scope
 *  has no run (or the tables are not there yet). */
export async function getEmergingSpace(scope: string): Promise<EmergingSpace | null> {
  const data = await getLatestEmergingRun(scope);
  if (!data || data.nests.length === 0) return null;
  const { run } = data;
  const months = data.nests[0].history_months;
  if (months.length === 0) return null;
  const vertical = scope.startsWith("vertical:") ? scope.slice("vertical:".length) : null;
  let centroidMap: Map<number, number[]>;
  let corpus: Map<string, number>;
  try {
    [centroidMap, corpus] = await Promise.all([
      getCentroids(run.id),
      getCorpusMonthly(run.created_at, vertical),
    ]);
  } catch {
    return null;
  }
  // Only pockets whose centroid is actually stored can be placed on the map.
  const nests = data.nests.filter((n) => centroidMap.has(n.id));
  const centroids = nests.map((n) => centroidMap.get(n.id)!);
  const totals = months.map((m) => corpus.get(m) ?? 0);
  return {
    run,
    nests,
    centroids,
    months,
    totals,
    corpusRows: totals.reduce((s, v) => s + v, 0),
  };
}
