import path from "path";
import fs from "fs";
import yaml from "js-yaml";
import { q, q1 } from "./pg";
import { windowStartIso } from "./archiveWindow";
import { classifyMomentum, type MegaMomentum } from "./momentum";
import { sourceSql, kindSql, PAPER_FILTER_SQL, type ResearchSourceKey, type ResearchSortKey } from "./researchFacets";
import type { PulseRow, PulseWeekRef } from "./researchPulse";
import type {
  EditionSummary,
  NewsletterEdition,
  MegaTrendRadarEntry,
  TrendRef,
  NewsletterDeepDive,
} from "./newsletterEditions";
import type {
  Trend,
  Vertical,
  PestelDimension,
  TrendSignalType,
} from "./types";

/**
 * Read layer on PostgreSQL + pgvector (migrated from better-sqlite3, 2026-07-03).
 * All functions are async; JSONB columns arrive pre-parsed from pg.
 */

/**
 * In-process TTL cache for expensive aggregate queries (ONB-01/ARCH-02: the
 * landing and methodology pages ran full-table COUNTs over ~1M rows on every
 * request → 7-9s TTFB). Counters may lag reality by up to the TTL — fine for
 * trust numbers that move hourly. Single-server deployment, so process-local
 * state is authoritative enough.
 */
const ttlCache = new Map<string, { at: number; value: unknown }>();

const inflight = new Map<string, Promise<unknown>>();

/** TTL cache that also dedupes CONCURRENT misses: while a value is being
 *  fetched every caller shares the same promise instead of firing its own
 *  query. Besides the thundering-herd saving, this is what makes the static
 *  export deterministic — generateMetadata and the page body of the same
 *  route await the same promise, so their RSC rows always stream in the same
 *  order (two independent queries finished in either order under pool
 *  contention and flipped the payload between builds). */
function cached<T>(key: string, ttlMs: number, fn: () => Promise<T>): Promise<T> {
  const hit = ttlCache.get(key);
  if (hit && Date.now() - hit.at < ttlMs) return Promise.resolve(hit.value as T);
  let p = inflight.get(key) as Promise<T> | undefined;
  if (!p) {
    p = fn()
      .then((value) => {
        ttlCache.set(key, { at: Date.now(), value });
        return value;
      })
      .finally(() => {
        inflight.delete(key);
      });
    inflight.set(key, p);
  }
  return p;
}

function asArray(v: unknown): string[] {
  if (Array.isArray(v)) return v as string[];
  if (typeof v === "string" && v) {
    try {
      const parsed = JSON.parse(v);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }
  return [];
}

function parseTrendRow(row: Record<string, unknown>): Trend {
  return {
    ...row,
    verticals: asArray(row.verticals),
    pestel: asArray(row.pestel),
    tags: asArray(row.tags),
    brands: asArray(row.brands),
    companies: asArray(row.companies),
    regions: asArray(row.regions),
    auto_published: Boolean(row.auto_published),
    source_date: (row.source_date as string) || null,
    source_type: (row.source_type as string) || null,
  } as Trend;
}

/** Explicit column list — never SELECT t.* (would drag the 4096-dim vectors
 *  over the wire on every card query). Timestamps cast to text for stable
 *  ISO-ish strings. */
const TREND_COLS =
  `t.id, t.raw_entry_id, t.title_en, t.slug, t.summary_en, t.body_en,
   t.verticals, t.primary_vertical, t.pestel, t.tags, t.trend_signal_type,
   t.mega_trend, t.macro_trend, t.trend_level, t.brands, t.companies, t.regions,
   t.trend_score, t.confidence, t.source_url, t.source_name, t.status,
   t.auto_published, t.published_at::text as published_at, t.created_at::text as created_at,
   t.sort_date::text as sort_date`;

/** SELECT for trend queries — joins raw_entries for source_date + source_type.
 *  A future-dated feed timestamp is capped at the row's own created_at rather
 *  than NOW(): with NOW() every render of such a row (3.1 % of the public
 *  window) showed the render day as the source date and made the static
 *  export non-deterministic (spike 2026-09-02, cause #4). NULL stays NULL —
 *  the UI falls back to published_at/created_at anyway. */
const TREND_SELECT = `SELECT ${TREND_COLS},
   LEAST(re.published_date, t.created_at)::text as source_date, s.source_type as source_type
   FROM trends t
   LEFT JOIN raw_entries re ON t.raw_entry_id = re.id
   LEFT JOIN sources s ON re.source_id = s.id`;

export async function getTrends(options: {
  status?: string;
  vertical?: Vertical;
  /** Free archive window (issue #70): only rows with sort_date within N days. */
  max_age_days?: number | null;
  limit?: number;
  offset?: number;
} = {}): Promise<Trend[]> {
  const params: unknown[] = [];
  let query = TREND_SELECT + " WHERE 1=1";
  if (options.status) {
    params.push(options.status);
    query += ` AND t.status = $${params.length}`;
  }
  if (options.vertical) {
    params.push(options.vertical);
    query += ` AND t.primary_vertical = $${params.length}`;
  }
  if (options.max_age_days != null) {
    params.push(windowStartIso(options.max_age_days));
    query += ` AND t.sort_date >= $${params.length}::timestamptz`;
  }
  params.push(options.limit ?? 50, options.offset ?? 0);
  query += ` ORDER BY t.sort_date DESC NULLS LAST, t.id DESC LIMIT $${params.length - 1} OFFSET $${params.length}`;
  return (await q(query, params)).map(parseTrendRow);
}

/**
 * Single article by slug. Published-only by default (security review
 * 2026-09-02, E-6): slugs are derivable from titles and turn up in logs and
 * newsletter refs, and the table also holds drafts, rejected articles and
 * ~1.6M `signal` rows that must never render on a public URL. Internal
 * tooling that needs to look at unpublished rows says so explicitly.
 */
export async function getTrendBySlug(
  slug: string,
  options: { includeUnpublished?: boolean } = {}
): Promise<Trend | null> {
  let query = TREND_SELECT + " WHERE t.slug = $1";
  if (!options.includeUnpublished) query += " AND t.status = 'published'";
  const row = await q1(query, [slug]);
  return row ? parseTrendRow(row) : null;
}

export interface PublicSlugRow {
  slug: string;
  sort_date: string | null;
  published_at: string | null;
}

/**
 * Every published slug inside the public window — the static export's page
 * list (`generateStaticParams` of /trends/[slug]) and the sitemap. Newest
 * first with the id tiebreaker, so the list itself is build-stable. Narrow
 * projection on purpose: 14.7k rows of TREND_SELECT would drag bodies over
 * the wire for nothing.
 */
export async function getPublicWindowSlugs(windowDays: number): Promise<PublicSlugRow[]> {
  return q<PublicSlugRow>(
    `SELECT t.slug, t.sort_date::text as sort_date, t.published_at::text as published_at
       FROM trends t
      WHERE t.status = 'published' AND t.sort_date >= $1::timestamptz
      ORDER BY t.sort_date DESC, t.id DESC`,
    [windowStartIso(windowDays)]
  );
}

/**
 * "Related" for an article page: the `limit` published PREDECESSORS in the
 * same vertical — the rows right before it in (sort_date DESC, id DESC)
 * order. A function of the article alone, not of the day it renders: the
 * former "4 newest of the vertical" changed every article page at every new
 * publish (~700 MB of churn per daily export; spike 2026-09-02, cause #5).
 * Bounded below by the archive window when one applies, so the export never
 * links to a slug it did not write (window-edge pages lose a related card
 * on their last day instead of linking into a 410).
 */
export async function getRelatedPredecessors(
  trend: Pick<Trend, "id" | "primary_vertical" | "sort_date">,
  options: { limit?: number; max_age_days?: number | null } = {}
): Promise<Trend[]> {
  if (!trend.sort_date) return [];
  const params: unknown[] = [trend.primary_vertical, trend.id, trend.sort_date];
  let query =
    TREND_SELECT +
    ` WHERE t.status = 'published' AND t.primary_vertical = $1
        AND (t.sort_date, t.id) < ($3::timestamp, $2::int)`;
  if (options.max_age_days != null) {
    params.push(windowStartIso(options.max_age_days));
    query += ` AND t.sort_date >= $${params.length}::timestamptz`;
  }
  params.push(options.limit ?? 3);
  query += ` ORDER BY t.sort_date DESC, t.id DESC LIMIT $${params.length}`;
  return (await q(query, params)).map(parseTrendRow);
}

/**
 * Published count per vertical inside the public window (null = whole
 * archive) — the tabs of the static listing (components/StaticFeed.tsx).
 * One value per window, so it is cached like the other aggregates; every
 * listing page of an export reads the same promise.
 */
export async function getVerticalCountsWindowed(
  windowDays: number | null
): Promise<Record<string, number>> {
  return cached(`vertical-counts-window:${windowDays ?? "all"}`, 600_000, async () => {
    const params: unknown[] = [];
    let where = "t.status = 'published'";
    if (windowDays != null) {
      params.push(windowStartIso(windowDays));
      where += ` AND t.sort_date >= $${params.length}::timestamptz`;
    }
    const rows = await q<{ primary_vertical: string; cnt: number }>(
      `SELECT t.primary_vertical, COUNT(*)::int as cnt FROM trends t
        WHERE ${where} GROUP BY t.primary_vertical ORDER BY cnt DESC`,
      params
    );
    const result: Record<string, number> = {};
    for (const row of rows) if (row.primary_vertical) result[row.primary_vertical] = row.cnt;
    return result;
  });
}

/**
 * Newest `sort_date` among the published rows of the window — the
 * data-derived "as of" stamp of every static listing page (TrendsHero).
 * The same value on all pages of a build, and no page reads the clock.
 */
export async function getPublicWindowNewest(windowDays: number | null): Promise<string | null> {
  return cached(`window-newest:${windowDays ?? "all"}`, 600_000, async () => {
    const params: unknown[] = [];
    let where = "t.status = 'published'";
    if (windowDays != null) {
      params.push(windowStartIso(windowDays));
      where += ` AND t.sort_date >= $${params.length}::timestamptz`;
    }
    const row = await q1<{ d: string | null }>(
      `SELECT MAX(t.sort_date)::text as d FROM trends t WHERE ${where}`,
      params
    );
    return row?.d ?? null;
  });
}

export interface PublicIndexRow {
  slug: string;
  title_en: string;
  summary_en: string | null;
  primary_vertical: string;
  verticals: unknown;
  pestel: unknown;
  mega_trend: string | null;
  sort_date: string | null;
  trend_score: number | null;
  source_name: string | null;
  trend_signal_type: string | null;
  source_type: string | null;
}

/**
 * Rows of the client-side search index of the static site (design Schritt
 * 5 / follow-up D — consumed by app/trends/index.json/route.ts, shaped by
 * lib/staticSearch.ts): every published article in the window, narrow
 * projection, summary pre-cut in SQL (the index trims it to 160 characters
 * at a word boundary). Same window bound and the same `sort_date DESC,
 * id DESC` order as the page list, so the index never names a slug the
 * export did not write. `source_type` comes via the same joins as
 * TREND_SELECT — it is the card's "Trade / Press / Brand" label.
 */
export async function getPublicIndexRows(windowDays: number): Promise<PublicIndexRow[]> {
  return q<PublicIndexRow>(
    `SELECT t.slug, t.title_en, left(t.summary_en, 240) as summary_en,
            t.primary_vertical, t.verticals, t.pestel, t.mega_trend,
            t.sort_date::text as sort_date, t.trend_score, t.source_name,
            t.trend_signal_type, s.source_type as source_type
       FROM trends t
       LEFT JOIN raw_entries re ON t.raw_entry_id = re.id
       LEFT JOIN sources s ON re.source_id = s.id
      WHERE t.status = 'published' AND t.sort_date >= $1::timestamptz
      ORDER BY t.sort_date DESC, t.id DESC`,
    [windowStartIso(windowDays)]
  );
}

export async function getTrendsCount(options: {
  status?: string;
  vertical?: Vertical;
  /** Free archive window (issue #70) — part of the cache key below. */
  max_age_days?: number | null;
} = {}): Promise<number> {
  // status/vertical/window form a tiny keyspace — safe to cache (10 min).
  return cached(
    `trends-count:${options.status ?? "all"}:${options.vertical ?? "all"}:${options.max_age_days ?? "all"}`,
    600_000,
    () => fetchTrendsCount(options)
  );
}

async function fetchTrendsCount(options: {
  status?: string;
  vertical?: Vertical;
  max_age_days?: number | null;
} = {}): Promise<number> {
  const params: unknown[] = [];
  let query = "SELECT COUNT(*)::int as cnt FROM trends t WHERE 1=1";
  if (options.status) {
    params.push(options.status);
    query += ` AND t.status = $${params.length}`;
  }
  if (options.vertical) {
    params.push(options.vertical);
    query += ` AND t.primary_vertical = $${params.length}`;
  }
  if (options.max_age_days != null) {
    params.push(windowStartIso(options.max_age_days));
    query += ` AND t.sort_date >= $${params.length}::timestamptz`;
  }
  const row = await q1<{ cnt: number }>(query, params);
  return row?.cnt ?? 0;
}

export async function getTrendsByMegaTrend(megaTrend: string, options: {
  status?: string;
  /** Free archive window (issue #70). */
  max_age_days?: number | null;
  limit?: number;
} = {}): Promise<Trend[]> {
  const params: unknown[] = [megaTrend];
  let query = TREND_SELECT + " WHERE t.mega_trend = $1";
  if (options.status) {
    params.push(options.status);
    query += ` AND t.status = $${params.length}`;
  }
  if (options.max_age_days != null) {
    params.push(windowStartIso(options.max_age_days));
    query += ` AND t.sort_date >= $${params.length}::timestamptz`;
  }
  params.push(options.limit ?? 50);
  query += ` ORDER BY t.sort_date DESC NULLS LAST, t.id DESC LIMIT $${params.length}`;
  return (await q(query, params)).map(parseTrendRow);
}

export interface MegaTrendInfo {
  mega_trend: string;
  count: number;
  verticals: string[];
  name_en: string;
  description: string;
  /** MEASURED (share of published signals, last 90d vs the 90d before) — see
   *  lib/momentum.ts. null = too few signals for a directional claim. */
  momentum: MegaMomentum | null;
  cluster_strength: "strong" | "moderate" | "fragmented";
  signal_count: number;
  horizon: string;
  /** Earliest source date for any trend in this mega-trend (ISO string). */
  first_seen: string | null;
  /** Number of signals published in the last 30 days. */
  signals_30d: number;
  /** Earned Megatrend badge (measured; see measure_mega_axes.py). */
  megatrend: boolean;
  /** Measurement snapshot backing the badge (reach/tiers/lead/dominance). */
  measured: {
    measured_at: string; reach: number; tiers: number;
    lead_months: number | null; lead_tier?: string | null;
    dom_vertical: string; dom_share: number;
    peak_year?: number | null; peak_market_n?: number;
    last12_market_n?: number; faded_hype?: boolean;
  } | null;
}

function loadMegaTrendYaml(): Record<string, {
  name_en: string; description: string;
  megatrend: boolean; measured: MegaTrendInfo["measured"];
  cluster_strength: string; signal_count: number; horizon: string;
}> {
  const yamlPath = path.join(process.cwd(), "..", "mega_trends.yaml");
  try {
    const raw = fs.readFileSync(yamlPath, "utf-8");
    const data = yaml.load(raw) as { mega_trends: Array<Record<string, unknown>> };
    const map: Record<string, any> = {};
    for (const mt of data.mega_trends || []) {
      map[mt.key as string] = {
        name_en: mt.name_en as string,
        description: mt.description as string,
        megatrend: Boolean(mt.megatrend),
        measured: (mt.measured as Record<string, unknown>) ?? null,
        // momentum deliberately NOT read from yaml: it was a hand-typed claim,
        // and 19 of 26 contradicted the data (2026-08-08). Measured instead
        // in fetchMegaTrends via classifyMomentum().
        cluster_strength: (mt.cluster_strength as string) || "fragmented",
        signal_count: (mt.signal_count as number) || 0,
        horizon: (mt.horizon as string) || "",
      };
    }
    return map;
  } catch {
    return {};
  }
}

export async function getMegaTrends(status?: string): Promise<MegaTrendInfo[]> {
  return cached(`mega-trends:${status ?? "all"}`, 600_000, () =>
    fetchMegaTrends(status)
  );
}

async function fetchMegaTrends(status?: string): Promise<MegaTrendInfo[]> {
  const params: unknown[] = [];
  let query = `SELECT t.mega_trend, COUNT(*)::int as cnt,
     STRING_AGG(DISTINCT t.primary_vertical, ',') as verts,
     MIN(t.sort_date)::text as first_seen,
     -- Tageskante, nicht "jetzt minus N Tage": zwei Builds Minuten auseinander
     -- muessen dieselbe Seite erzeugen (Determinismus-Gate des statischen
     -- Exports). Mit NOW() fielen zwischen zwei Laeufen einzelne Signale aus
     -- dem Fenster — gemessen 2026-09-07: /trends/mega war die einzige Seite,
     -- die sich zwischen zwei identischen Builds unterschied (signals_30d
     -- 2043 vs 2042). Dieselbe Regel wie lib/archiveWindow.ts windowStart().
     SUM(CASE WHEN t.sort_date >= date_trunc('day', NOW()) - INTERVAL '30 days' THEN 1 ELSE 0 END)::int as signals_30d,
     SUM(CASE WHEN t.sort_date >= date_trunc('day', NOW()) - INTERVAL '90 days' THEN 1 ELSE 0 END)::int as recent90,
     SUM(CASE WHEN t.sort_date >= date_trunc('day', NOW()) - INTERVAL '180 days'
              AND t.sort_date <  date_trunc('day', NOW()) - INTERVAL '90 days' THEN 1 ELSE 0 END)::int as prior90
     FROM trends t
     WHERE t.mega_trend IS NOT NULL AND t.mega_trend != ''`;
  if (status) {
    params.push(status);
    query += ` AND t.status = $${params.length}`;
  }
  query += " GROUP BY t.mega_trend ORDER BY cnt DESC";

  const rows = await q<{
    mega_trend: string;
    cnt: number;
    verts: string;
    first_seen: string | null;
    signals_30d: number;
    recent90: number;
    prior90: number;
  }>(query, params);

  const yamlData = loadMegaTrendYaml();
  // normalization base: the whole labeled corpus in the same windows — shares,
  // not raw counts, so corpus growth doesn't read as trend growth
  const totalRecent = rows.reduce((s, r) => s + r.recent90, 0);
  const totalPrior = rows.reduce((s, r) => s + r.prior90, 0);

  return rows.map((r) => {
    const meta = yamlData[r.mega_trend] || {};
    return {
      mega_trend: r.mega_trend,
      count: r.cnt,
      verticals: r.verts ? r.verts.split(",") : [],
      name_en: meta.name_en || r.mega_trend.replace(/_/g, " "),
      description: meta.description || "",
      momentum: classifyMomentum(r.recent90, r.prior90, totalRecent, totalPrior),
      megatrend: Boolean(meta.megatrend),
      measured: meta.measured ?? null,
      cluster_strength: (meta.cluster_strength || "fragmented") as MegaTrendInfo["cluster_strength"],
      signal_count: r.signals_30d || 0,
      horizon: meta.horizon || "",
      first_seen: r.first_seen || null,
      signals_30d: r.signals_30d || 0,
    };
  });
}

export interface ResearchSignal {
  trend_id: number;
  title: string;
  abstract: string | null;
  url: string;
  source: string | null;
  concept: string | null;
  published: string | null;
  mega_trend: string | null;
  vertical: string | null;
  /** article | preprint | review | chapter | artifact | unknown (#73, build_research_index.py). */
  kind: string | null;
}

/** Research Explorer (#72): FTS over the materialized research_signals table
 *  (built by scripts/build_research_index.py — 545k abstracts, GIN-indexed).
 *  Returns one page of results + the total match count. Facets (#73):
 *  source groups, period, concept, sort — parsed in lib/researchFacets.ts.
 *  Artifacts (repository deposits / non-paper works, kind = 'artifact') are
 *  hidden unless `includeArtifacts` — same paper basis as the Research Pulse. */
export async function getResearchSignals(options: {
  q?: string;
  mega?: string;
  concept?: string;
  sources?: ResearchSourceKey[];
  sinceDays?: number | null;
  sort?: ResearchSortKey;
  includeArtifacts?: boolean;
  limit?: number;
  offset?: number;
} = {}): Promise<{ rows: ResearchSignal[]; total: number }> {
  const params: unknown[] = [];
  const where: string[] = [];
  const kindFilter = kindSql(options.includeArtifacts ?? false);
  if (kindFilter) where.push(kindFilter);
  let qIdx = 0;
  if (options.q) {
    params.push(options.q);
    qIdx = params.length;
    where.push(`tsv @@ websearch_to_tsquery('english', $${qIdx})`);
  }
  if (options.mega) {
    params.push(options.mega);
    where.push(`mega_trend = $${params.length}`);
  }
  if (options.concept) {
    params.push(options.concept);
    where.push(`concept = $${params.length}`);
  }
  const src = sourceSql(options.sources ?? []);
  if (src) where.push(src);
  if (options.sinceDays) {
    params.push(options.sinceDays);
    where.push(`published >= CURRENT_DATE - ($${params.length}::int)`);
  }
  const w = where.length ? ` WHERE ${where.join(" AND ")}` : "";
  const totalRow = await q1<{ cnt: number }>(
    `SELECT COUNT(*)::int as cnt FROM research_signals${w}`, params);
  const rank = options.q && options.sort !== "date"
    ? `ts_rank(tsv, websearch_to_tsquery('english', $${qIdx})) DESC, `
    : "";
  params.push(options.limit ?? 25, options.offset ?? 0);
  const rows = await q<ResearchSignal>(
    `SELECT trend_id, title, abstract, url, source, concept, published::text as published,
            mega_trend, vertical, kind
     FROM research_signals${w}
     ORDER BY ${rank}published DESC NULLS LAST, trend_id DESC
     LIMIT $${params.length - 1} OFFSET $${params.length}`, params);
  return { rows, total: totalRow?.cnt ?? 0 };
}

/** Headline counts of the signal layer — papers only (kind <> artifact, #73). */
export async function getResearchStats(): Promise<{ total: number; last30d: number }> {
  return cached("research-stats", 600_000, async () => {
    const row = await q1<{ total: number; last30d: number }>(
      `SELECT COUNT(*)::int as total,
              SUM(CASE WHEN published >= NOW() - INTERVAL '30 days' THEN 1 ELSE 0 END)::int as last30d
       FROM research_signals WHERE ${PAPER_FILTER_SQL}`);
    return { total: row?.total ?? 0, last30d: row?.last30d ?? 0 };
  });
}

// ---------------------------------------------------------------------------
// Research Pulse (#73 Teil 1): weekly per-theme synthesis in `research_pulse`
// (scripts/research_pulse.py; additive migration scripts/migrate_research_pulse.py).
// Versioned: one row per computation, the pages read the newest per
// (theme, year, week). Guarded with to_regclass so a DB without the table
// renders the empty state instead of a 500.
// ---------------------------------------------------------------------------

const PULSE_COLS = `id, theme, year, week, week_start::text AS week_start,
  to_char(computed_at, 'YYYY-MM-DD"T"HH24:MI:SS') AS computed_at,
  stats, clusters, text, model, seconds, note`;

export async function pulseTableReady(): Promise<boolean> {
  try {
    const row = await q1<{ t: string | null }>(
      `SELECT to_regclass('public.research_pulse')::text AS t`);
    return Boolean(row?.t);
  } catch {
    return false;
  }
}

/** Weeks with at least one pulse row, newest first (overview switcher). */
export async function getPulseWeeks(): Promise<(PulseWeekRef & { themes: number; computed_at: string })[]> {
  if (!(await pulseTableReady())) return [];
  return q<PulseWeekRef & { themes: number; computed_at: string }>(
    `SELECT year, week, COUNT(DISTINCT theme)::int AS themes,
            to_char(MAX(computed_at), 'YYYY-MM-DD"T"HH24:MI:SS') AS computed_at
     FROM research_pulse GROUP BY year, week ORDER BY year DESC, week DESC LIMIT 26`);
}

/** Newest pulse per theme for one week. */
export async function getPulseOverview(year: number, week: number): Promise<PulseRow[]> {
  if (!(await pulseTableReady())) return [];
  return q<PulseRow>(
    `SELECT DISTINCT ON (theme) ${PULSE_COLS}
     FROM research_pulse WHERE year = $1 AND week = $2
     ORDER BY theme, computed_at DESC`, [year, week]);
}

export async function getPulseTheme(theme: string, year: number, week: number): Promise<PulseRow | null> {
  if (!(await pulseTableReady())) return null;
  return q1<PulseRow>(
    `SELECT ${PULSE_COLS} FROM research_pulse
     WHERE theme = $1 AND year = $2 AND week = $3
     ORDER BY computed_at DESC LIMIT 1`, [theme, year, week]);
}

/** Weeks this theme has been computed for (detail switcher) + run count. */
export async function getPulseThemeWeeks(theme: string): Promise<(PulseWeekRef & { runs: number })[]> {
  if (!(await pulseTableReady())) return [];
  return q<PulseWeekRef & { runs: number }>(
    `SELECT year, week, COUNT(*)::int AS runs FROM research_pulse
     WHERE theme = $1 GROUP BY year, week ORDER BY year DESC, week DESC LIMIT 26`, [theme]);
}

// ---------------------------------------------------------------------------
// Research-Korpus-Suchschicht (#80): 45,9M OpenAlex-Werke aller Disziplinen
// in `research_corpus` (scripts/ingest_openalex_snapshot.py) — gespeicherter
// tsvector Titel=A/Abstract=B, getrennt von der kuratierten Signal-Schicht.
// ---------------------------------------------------------------------------

export interface ResearchWork {
  id: string;
  doi: string | null;
  title: string;
  abstract: string;
  published: string | null;
  year: number | null;
  type: string | null;
  topic: string | null;
  cited_by_count: number | null;
  fwci: number | null;
  is_retracted: boolean | null;
  journal: string | null;
  /** Open-Access-Volltext-Link (research_work_oa), null wenn Paywall. */
  oa_url: string | null;
  /** Autorenliste, "; "-getrennt (research_authors_flat, max 30 Namen). */
  authors: string | null;
  /** Zitationen seit 2025 — nur in der Rising-Liste gesetzt (flag='rising'). */
  cites_recent?: number | null;
}

const RC_COLS = `rc.id, rc.doi, rc.title, rc.abstract,
       rc.published::text as published, rc.year, rc.type, rc.topic,
       rc.cited_by_count, rc.fwci, rc.is_retracted, wj.journal, oa.oa_url,
       af.authors`;
// Alle drei Joins sind PK-Lookups auf work_id und laufen erst NACH der
// Begrenzung auf die Seitenzeilen (Self-Join-Muster) — Messung 2026-08-16:
// kein Laufzeitunterschied gegenüber dem Stand ohne Autoren-Join.
const RC_JOINS = `LEFT JOIN research_work_journal wj ON wj.work_id = rc.id
     LEFT JOIN research_work_oa oa ON oa.work_id = rc.id
     LEFT JOIN research_authors_flat af ON af.work_id = rc.id`;
const RC_CLAMP = 10000;


/** Operator-Treffermenge (author:/institution:/journal:) — treibt von der
 *  Nebentabelle (Trigram bzw. ILIKE) mit 10k-Deckel. Die Gegenrichtung
 *  (EXISTS je Korpus-Zeile) detoastet bei großen Institutionen die tsv über
 *  Hunderttausende Zeilen: 'Max Planck' x 'quantum' = 21,5s gemessen
 *  (#80, 2026-08-15). Kleine Namen bleiben exakt, Riesen-Namen werden zur
 *  ehrlichen Stichprobe (opClamped). Langfristig sauber: Namen als
 *  C/D-Label-Lexeme in die tsv beim nächsten Voll-Rebuild (in #80 notiert). */
async function researchOperatorHits(options: {
  author?: string; institution?: string; journal?: string;
  funder?: string; country?: string;
}): Promise<{ ids: string[]; opClamped: boolean } | null> {
  const parts: { table: string; col: string; val: string; exact?: boolean }[] = [];
  if (options.author) parts.push({ table: "research_authors_flat", col: "authors", val: options.author });
  if (options.institution) parts.push({ table: "research_authors_flat", col: "institutions", val: options.institution });
  if (options.journal) parts.push({ table: "research_work_journal", col: "journal", val: options.journal });
  if (options.funder) parts.push({ table: "research_work_funder", col: "funder", val: options.funder });
  if (options.country) parts.push({ table: "research_work_inst", col: "country",
                                    val: options.country.toUpperCase(), exact: true });
  if (parts.length === 0) return null;
  let ids: Set<string> | null = null;
  let opClamped = false;
  for (const p of parts) {
    const rows = await q<{ work_id: string }>(
      p.exact
        ? `SELECT work_id FROM ${p.table} WHERE ${p.col} = $1 LIMIT ${RC_CLAMP + 1}`
        : `SELECT work_id FROM ${p.table} WHERE ${p.col} ILIKE $1 LIMIT ${RC_CLAMP + 1}`,
      [p.exact ? p.val : `%${p.val}%`]);
    if (rows.length > RC_CLAMP) opClamped = true;
    const cur = new Set(rows.slice(0, RC_CLAMP).map((r) => r.work_id));
    if (ids === null) {
      ids = cur;
    } else {
      const prev: Set<string> = ids;
      ids = new Set([...prev].filter((x) => cur.has(x)));
    }
  }
  return { ids: [...(ids ?? [])], opClamped };
}

export async function getResearchCorpus(options: {
  q?: string;
  doi?: string;
  arxiv?: string;
  topic?: string;
  author?: string;
  institution?: string;
  journal?: string;
  funder?: string;
  /** Zwei-Buchstaben-Code (Land der Lead-Institution, research_work_inst). */
  country?: string;
  /** Zurückgezogene Werke ausblenden. */
  noRetracted?: boolean;
  /** Klick-Filter aus Panel-Kacheln/Badges (#80): landmark = fwci >= 25,
   *  review = type='review'. Partielle Indizes tragen den Browse-Pfad.
   *  rising (#83) ist kein reiner Filter, sondern die Panel-Definition als
   *  eigene Liste: Werke ab 2023 mit Zitationen seit 2025, nach diesen
   *  sortiert — identisch zur „Rising papers"-Kachel, damit Teaser und
   *  Klickziel dieselbe Menge zeigen. */
  flag?: "landmark" | "review" | "rising";
  yearFrom?: number;
  yearTo?: number;
  limit?: number;
  offset?: number;
} = {}): Promise<{ rows: ResearchWork[]; total: number; clamped: boolean }> {
  const limit = options.limit ?? 25;
  const offset = options.offset ?? 0;

  // Direktpfad DOI / arXiv-ID: die doi-Spalte trägt die volle OpenAlex-URL-
  // Form (https://doi.org/10.…, kleingeschrieben); arXiv-Werke haben den
  // DataCite-DOI 10.48550/arxiv.<id>. Läuft über idx_rc_doi.
  if (options.doi || options.arxiv) {
    const doi = options.doi
      ? `https://doi.org/${options.doi}`
      : `https://doi.org/10.48550/arxiv.${options.arxiv!.replace(/v\d+$/, "")}`;
    const rows = await q<ResearchWork>(
      `SELECT ${RC_COLS} FROM research_corpus rc ${RC_JOINS}
       WHERE rc.doi = $1 LIMIT 5`, [doi]);
    return { rows, total: rows.length, clamped: false };
  }

  const params: unknown[] = [];
  const where: string[] = [];
  let tq = "";
  if (options.q) {
    params.push(options.q);
    tq = `websearch_to_tsquery('english', $${params.length})`;
    where.push(`tsv @@ ${tq}`);
  }
  if (options.topic) {
    params.push(options.topic);
    where.push(`topic = $${params.length}`);
  }
  if (options.yearFrom !== undefined) {
    params.push(options.yearFrom);
    where.push(`year >= $${params.length}`);
  }
  if (options.yearTo !== undefined) {
    params.push(options.yearTo);
    where.push(`year <= $${params.length}`);
  }
  if (options.noRetracted) {
    where.push(`NOT is_retracted`);
  }
  if (options.flag === "landmark") {
    // fwci allein belohnt Ausreisser zitierungsarmer Felder (Theologie-Artikel
    // mit 18 Zitationen = fwci 72; 43% der fwci>=25-Werke hatten <100
    // Zitationen — Owner-Befund 2026-08-15). Landmark = feldnormierte
    // Exzellenz UND absolute Substanz.
    where.push(`fwci >= 25 AND cited_by_count >= 100`);
  } else if (options.flag === "review") {
    where.push(`type = 'review'`);
  } else if (options.flag === "rising") {
    // Identisch zur Aggregat-Klausel: Jahres-Schnitt UND „hat frische
    // Zitationen". Beide Seiten müssen dieselbe Menge kappen, sonst zählt
    // das Panel 10.000 und die Liste 3.961 (Befund 2026-08-17). Kostet
    // gemessen 0,1 s auf 10k Zeilen. Sortiert wird unten im eigenen Zweig.
    where.push(`year >= 2023 AND EXISTS (SELECT 1 FROM research_citation_recent cr
      WHERE cr.work_id = research_corpus.id AND cr.cites_recent > 0)`);
  }
  const op = await researchOperatorHits(options);
  if (op) {
    if (op.ids.length === 0) return { rows: [], total: 0, clamped: false };
    params.push(op.ids);
    where.push(`id = ANY($${params.length})`);
  }
  if (where.length === 0) {
    // Kein Filter: neueste Werke (Datums-Index), Count = Cache-Statistik
    const stats = await getResearchCorpusStats();
    params.push(limit, offset);
    const rows = await q<ResearchWork>(
      `SELECT ${RC_COLS} FROM research_corpus rc ${RC_JOINS}
       ORDER BY rc.published DESC
       LIMIT $${params.length - 1} OFFSET $${params.length}`, params);
    return { rows, total: Math.min(stats.total, RC_CLAMP), clamped: true };
  }
  const w = where.join(" AND ");
  // Rising-Liste (#83): eigener Zweig VOR dem Estimate-Gate — die Sortierung
  // nach Zitations-Zuwachs darf nie in den Datums-Walk kippen, sonst zeigte
  // der Klick auf die „Rising papers"-Kachel etwas anderes als die Kachel.
  // Wie das Panel über die (bis zu 10k) Treffer gerechnet, also derselbe
  // Ausschnitt und damit konsistent zum Teaser.
  if (options.flag === "rising") {
    params.push(limit, offset);
    const rows = await q<ResearchWork & { full_cnt: number }>(
      `WITH m AS MATERIALIZED (
         SELECT id FROM research_corpus WHERE ${w} LIMIT ${RC_CLAMP + 1}),
       r AS MATERIALIZED (
         SELECT m.id, cr.cites_recent FROM m
         JOIN research_citation_recent cr ON cr.work_id = m.id
         WHERE cr.cites_recent > 0)
       SELECT ${RC_COLS}, hit.rk AS cites_recent, hit.full_cnt FROM (
         SELECT r.id AS hit_id, r.cites_recent AS rk,
                (SELECT COUNT(*)::int FROM r) AS full_cnt
         FROM r ORDER BY r.cites_recent DESC
         LIMIT $${params.length - 1} OFFSET $${params.length}) hit
       JOIN research_corpus rc ON rc.id = hit.hit_id
       ${RC_JOINS}
       ORDER BY hit.rk DESC`, params);
    if (rows.length === 0) return { rows: [], total: 0, clamped: false };
    const total = rows[0].full_cnt;
    return { rows, total: Math.min(total, RC_CLAMP),
             clamped: total > RC_CLAMP || (op?.opClamped ?? false) };
  }
  // Zwei-Pfad-Logik wie patent_search (#78), mit einer Verschärfung für den
  // 45M-Korpus: Bei häufigen Begriffen ("battery") muss der GIN-Index erst
  // Millionen Fundstellen sammeln, bevor ein LIMIT greift — der Count-Clamp
  // selbst kostete >20s. Deshalb zuerst der Planer-SCHÄTZWERT (EXPLAIN, ms,
  // ohne Ausführung): große Mengen gehen direkt in den Datums-Pfad (dort sind
  // häufige Begriffe dicht → Index-Walk findet 25 Treffer sofort), nur
  // überschaubare Mengen werden exakt gezählt und nach Relevanz gerankt.
  const planRow = await q1<Record<string, unknown>>(
    `EXPLAIN (FORMAT JSON) SELECT 1 FROM research_corpus WHERE ${w}`,
    [...params]);
  const planJson = planRow?.["QUERY PLAN"] as
    | { Plan?: { "Plan Rows"?: number } }[] | undefined;
  const estimate = planJson?.[0]?.Plan?.["Plan Rows"] ?? 0;
  if (estimate > 100_000) {
    // Riesen-Menge: Datums-Walk (Treffer sind dicht → 25 Zeilen sofort);
    // Trefferzahl bleibt "10.000+". ORDER BY ohne NULLS LAST: idx_rc_published
    // ist DESC (= NULLS FIRST), Werke ohne Datum gibt es nicht (0 von 45,3M).
    // Schmaler ID-Select + Self-Join gegen den Planer-Kipp (22s vs 0,5s).
    params.push(limit, offset);
    const rows = await q<ResearchWork>(
      `SELECT ${RC_COLS} FROM (
         SELECT id AS hit_id, published AS hit_pub
         FROM research_corpus WHERE ${w} ORDER BY published DESC
         LIMIT $${params.length - 1} OFFSET $${params.length}) hit
       JOIN research_corpus rc ON rc.id = hit.hit_id
       ${RC_JOINS}
       ORDER BY hit.hit_pub DESC`, params);
    return { rows, total: RC_CLAMP, clamped: true };
  }
  const opClamped = op?.opClamped ?? false;
  // Überschaubare Menge: Treffer EINMAL materialisieren (inkl. tsv), dann
  // zählen + ranken NUR über die Materialisierung. Direkt auf der Tabelle
  // gerankt entscheidet der Planer bei parametrisierten Jahres-Filtern
  // unvorhersehbar und detoastet tsv weit über die Treffermenge hinaus —
  // gemessen 4,4s statt <1s für 'perovskite 2019-2023' (#80, 2026-08-15).
  const rankExpr = options.q
    ? `ts_rank(${PATENT_RANK_WEIGHTS}, m.tsv, ${tq})`
    : `0::float4`;
  params.push(limit, offset);
  const rows = await q<ResearchWork & { full_cnt: number }>(
    `WITH m AS MATERIALIZED (
       SELECT id, published, tsv FROM research_corpus
       WHERE ${w} LIMIT ${RC_CLAMP + 1})
     SELECT ${RC_COLS}, hit.full_cnt FROM (
       SELECT m.id AS hit_id, m.published AS hit_pub, ${rankExpr} AS rk,
              (SELECT COUNT(*)::int FROM m) AS full_cnt
       FROM m ORDER BY rk DESC, m.published DESC
       LIMIT $${params.length - 1} OFFSET $${params.length}) hit
     JOIN research_corpus rc ON rc.id = hit.hit_id
     ${RC_JOINS}
     ORDER BY hit.rk DESC, hit.hit_pub DESC`, params);
  if (rows.length === 0) {
    // Leere Seite (offset hinter dem Ende oder null Treffer): Count separat
    const countRow = await q1<{ cnt: number }>(
      `SELECT COUNT(*)::int as cnt FROM (
         SELECT 1 FROM research_corpus WHERE ${w} LIMIT ${RC_CLAMP + 1}) x`,
      params.slice(0, -2));
    const total = countRow?.cnt ?? 0;
    return { rows: [], total: Math.min(total, RC_CLAMP),
             clamped: total > RC_CLAMP || opClamped };
  }
  const total = rows[0].full_cnt;
  return {
    rows: rows.map(({ full_cnt: _full_cnt, ...r }) => r as ResearchWork),
    total: Math.min(total, RC_CLAMP),
    clamped: total > RC_CLAMP || opClamped,
  };
}

export interface ResearchAggregates {
  /** Basis der Aggregation (bis RC_CLAMP neueste Treffer). */
  n: number;
  sampled: boolean;
  years: { year: number; n: number }[];
  topics: { topic: string; n: number }[];
  reviews: number;
  retracted: number;
  landmarks: number;
  medianCites: number | null;
  rising: { id: string; doi: string | null; title: string; year: number; cited_by_count: number }[];
  institutions: { institution: string; n: number }[];
  journals: { journal: string; n: number }[];
  countries: { country: string; n: number }[];
  funders: { funder: string; n: number }[];
  /** Anteil der Zitationen aus 2025/26 an allen Zitationen der Treffer. */
  attention: number | null;
}

/** Generische Repositorien — fuer den "Top journals"-Panelblock gefiltert
 *  (primary_location zeigt bei OA-Werken oft aufs Repository, nicht aufs
 *  Journal); die journal:-Suche selbst bleibt ungefiltert. */
const REPO_VENUES = [
  "Zenodo (CERN European Organization for Nuclear Research)",
  "arXiv (Cornell University)", "PubMed", "PubMed Central",
  "DOAJ (DOAJ: Directory of Open Access Journals)", "Figshare",
  "bioRxiv (Cold Spring Harbor Laboratory)",
  "medRxiv (Cold Spring Harbor Laboratory)", "SSRN Electronic Journal",
  "Research Square (Research Square)", "OSF Preprints (OSF)",
  "HAL (Le Centre pour la Communication Scientifique Directe)",
];

/** Treffer-Statistiken für das Result-Intelligence-Panel (#80): aggregiert
 *  über die bis zu 10.000 NEUESTEN Treffer der Filterkombination — bei
 *  geclampten Mengen also eine ehrliche Stichprobe, die Seite sagt das dazu.
 *  Rising = meistzitierte junge Werke (ab 2023) der Treffermenge, normiert
 *  auf Zitationen/Jahr; Landmark = fwci >= 25 (Top 1 % feldnormierter
 *  Impact, Perzentile gemessen 2026-08-14). */
export async function getResearchAggregates(options: {
  q?: string;
  topic?: string;
  author?: string;
  institution?: string;
  journal?: string;
  funder?: string;
  country?: string;
  noRetracted?: boolean;
  flag?: "landmark" | "review" | "rising";
  yearFrom?: number;
  yearTo?: number;
} = {}): Promise<ResearchAggregates | null> {
  const params: unknown[] = [];
  const where: string[] = [];
  if (options.q) {
    params.push(options.q);
    where.push(`tsv @@ websearch_to_tsquery('english', $${params.length})`);
  }
  if (options.topic) {
    params.push(options.topic);
    where.push(`topic = $${params.length}`);
  }
  if (options.yearFrom !== undefined) {
    params.push(options.yearFrom);
    where.push(`year >= $${params.length}`);
  }
  if (options.yearTo !== undefined) {
    params.push(options.yearTo);
    where.push(`year <= $${params.length}`);
  }
  if (options.noRetracted) {
    where.push(`NOT is_retracted`);
  }
  if (options.flag === "landmark") {
    // fwci allein belohnt Ausreisser zitierungsarmer Felder (Theologie-Artikel
    // mit 18 Zitationen = fwci 72; 43% der fwci>=25-Werke hatten <100
    // Zitationen — Owner-Befund 2026-08-15). Landmark = feldnormierte
    // Exzellenz UND absolute Substanz.
    where.push(`fwci >= 25 AND cited_by_count >= 100`);
  } else if (options.flag === "review") {
    where.push(`type = 'review'`);
  } else if (options.flag === "rising") {
    // Das Panel muss GENAU die Liste beschreiben: derselbe Jahres-Schnitt
    // UND dieselbe Bedingung „hat frische Zitationen" wie der Join im
    // Listen-Zweig — sonst zeigte die Statistik ein anderes Set als die
    // Treffer darunter (Befund 2026-08-17: median citations 0).
    where.push(`year >= 2023 AND EXISTS (SELECT 1 FROM research_citation_recent cr
      WHERE cr.work_id = research_corpus.id AND cr.cites_recent > 0)`);
  }
  const op = await researchOperatorHits(options);
  if (op) {
    if (op.ids.length === 0) return null;
    params.push(op.ids);
    where.push(`id = ANY($${params.length})`);
  }
  if (where.length === 0) return null;
  const w = where.join(" AND ");
  // Kein Panel für Riesen-Mengen: "die 10k neuesten Treffer" eines häufigen
  // Begriffs erzwingen einen Datums-Walk mit Hunderttausenden tsv-Rechecks
  // (battery 23s, mit Jahresfilter 120s+ gemessen) — dafür existiert kein
  // billiger exakter Pfad. Unter ~100k Treffern nimmt der Planer den
  // GIN-/Topic-Index OHNE Datums-Sortierung: schnell, und bis 10k sogar die
  // vollständige Menge. Die Seite fordert bei null zum Eingrenzen auf.
  const planRow2 = await q1<Record<string, unknown>>(
    `EXPLAIN (FORMAT JSON) SELECT 1 FROM research_corpus WHERE ${w}`,
    [...params]);
  const plan2 = planRow2?.["QUERY PLAN"] as
    | { Plan?: { "Plan Rows"?: number } }[] | undefined;
  if ((plan2?.[0]?.Plan?.["Plan Rows"] ?? 0) > 100_000) return null;
  // Schmaler Treffer-Select + Self-Join (Planer-Kipp-Schutz wie oben), dann
  // alle Aggregate in EINEM Roundtrip als JSON-Unterabfragen.
  const row = await q1<{
    n: number; reviews: number; retracted: number; landmarks: number;
    median_cites: number | null; years: unknown; topics: unknown; rising: unknown;
    institutions: unknown; journals: unknown; countries: unknown;
    funders: unknown; attention: number | null;
  }>(
    `WITH hit AS (
       SELECT id FROM research_corpus WHERE ${w} LIMIT ${RC_CLAMP}),
     hits AS (
       SELECT rc.id, rc.doi, rc.title, rc.year, rc.topic, rc.type,
              rc.cited_by_count, rc.fwci, rc.is_retracted
       FROM hit JOIN research_corpus rc ON rc.id = hit.id)
     SELECT
       (SELECT COUNT(*)::int FROM hits) AS n,
       (SELECT COUNT(*)::int FROM hits WHERE type = 'review') AS reviews,
       (SELECT COUNT(*)::int FROM hits WHERE is_retracted) AS retracted,
       (SELECT COUNT(*)::int FROM hits WHERE fwci >= 25 AND cited_by_count >= 100) AS landmarks,
       (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY cited_by_count)
          FROM hits) AS median_cites,
       (SELECT json_agg(t) FROM (
          SELECT year, COUNT(*)::int AS n FROM hits
          WHERE year IS NOT NULL GROUP BY year ORDER BY year) t) AS years,
       (SELECT json_agg(t) FROM (
          SELECT topic, COUNT(*)::int AS n FROM hits
          WHERE topic IS NOT NULL GROUP BY topic
          ORDER BY COUNT(*) DESC LIMIT 6) t) AS topics,
       (SELECT json_agg(t) FROM (
          SELECT h.id, h.doi, h.title, h.year, h.cited_by_count FROM hits h
          JOIN research_citation_recent cr ON cr.work_id = h.id
          WHERE h.year >= 2023
          ORDER BY cr.cites_recent DESC LIMIT 5) t) AS rising,
       (SELECT json_agg(t) FROM (
          SELECT wi.institution, COUNT(*)::int AS n FROM hits h
          JOIN research_work_inst wi ON wi.work_id = h.id
          WHERE wi.institution IS NOT NULL
          GROUP BY 1 ORDER BY COUNT(*) DESC LIMIT 5) t) AS institutions,
       (SELECT json_agg(t) FROM (
          SELECT wj.journal, COUNT(*)::int AS n FROM hits h
          JOIN research_work_journal wj ON wj.work_id = h.id
          WHERE wj.journal <> ALL($${params.length + 1})
          GROUP BY 1 ORDER BY COUNT(*) DESC LIMIT 5) t) AS journals,
       (SELECT json_agg(t) FROM (
          SELECT wi.country, COUNT(*)::int AS n FROM hits h
          JOIN research_work_inst wi ON wi.work_id = h.id
          WHERE wi.country IS NOT NULL
          GROUP BY 1 ORDER BY COUNT(*) DESC LIMIT 5) t) AS countries,
       (SELECT json_agg(t) FROM (
          SELECT f.funder, COUNT(DISTINCT h.id)::int AS n FROM hits h
          JOIN research_work_funder f ON f.work_id = h.id
          GROUP BY 1 ORDER BY COUNT(DISTINCT h.id) DESC LIMIT 5) t) AS funders,
       (SELECT SUM(cr.cites_recent)::float / NULLIF(SUM(cr.cites_total), 0)
          FROM hits h JOIN research_citation_recent cr ON cr.work_id = h.id
        ) AS attention`,
    [...params, REPO_VENUES]);
  if (!row || !row.n) return null;
  return {
    n: row.n,
    sampled: row.n >= RC_CLAMP,
    years: (row.years as ResearchAggregates["years"]) ?? [],
    topics: (row.topics as ResearchAggregates["topics"]) ?? [],
    reviews: row.reviews,
    retracted: row.retracted,
    landmarks: row.landmarks,
    medianCites: row.median_cites === null ? null : Number(row.median_cites),
    rising: (row.rising as ResearchAggregates["rising"]) ?? [],
    institutions: (row.institutions as ResearchAggregates["institutions"]) ?? [],
    journals: (row.journals as ResearchAggregates["journals"]) ?? [],
    countries: (row.countries as ResearchAggregates["countries"]) ?? [],
    funders: (row.funders as ResearchAggregates["funders"]) ?? [],
    attention: row.attention === null ? null : Number(row.attention),
  };
}

/** Research→Patent-Lead-Time einer CPC-Achse (Median-Alter der 2023
 *  zitierten Forschung, tip_npl_share) — für die Patent-Brücke im Panel. */
export async function getNplLagYears(cpc: string): Promise<number | null> {
  return cached(`npl-lag-${cpc}`, 3_600_000, async () => {
    const row = await q1<{ median_lag_years: number | null }>(
      `SELECT median_lag_years FROM tip_npl_share
       WHERE cpc_subclass = $1 AND publn_year = 2023`, [cpc]);
    return row?.median_lag_years ?? null;
  });
}

/** Wachstum je Topic: Ø Werke/Jahr 2023–2025 vs. 2019–2021 (aus dem
 *  Sync-gepflegten Aggregat research_topic_years — nur ZITIERTE Werke,
 *  damit der Korpus-Zitations-Floor keine Scheinwachstums erzeugt). */
export async function getTopicTrends(topics: string[]): Promise<Map<string, number>> {
  if (topics.length === 0) return new Map();
  const rows = await q<{ topic: string; recent: number; base: number }>(
    `SELECT topic,
            AVG(n) FILTER (WHERE year BETWEEN 2023 AND 2025) AS recent,
            AVG(n) FILTER (WHERE year BETWEEN 2019 AND 2021) AS base
     FROM research_topic_years WHERE topic = ANY($1)
     GROUP BY topic`, [topics]);
  const m = new Map<string, number>();
  for (const r of rows) {
    if (r.base && Number(r.base) >= 20) {
      m.set(r.topic, Number(r.recent ?? 0) / Number(r.base) - 1);
    }
  }
  return m;
}

/** Emerging research fields: wachstumsstärkste Topics (Basis-Floor gegen
 *  Quasi-Null-Basen, Muster emergingGroups). Gecacht 1h. */
export async function getEmergingTopics(): Promise<
  { topic: string; growth: number; recent: number }[]
> {
  return cached("emerging-topics", 3_600_000, async () => {
    const rows = await q<{ topic: string; growth: number; recent: number }>(
      `SELECT topic,
              (AVG(n) FILTER (WHERE year BETWEEN 2023 AND 2025)
               / NULLIF(AVG(n) FILTER (WHERE year BETWEEN 2019 AND 2021), 0) - 1) AS growth,
              COALESCE(AVG(n) FILTER (WHERE year BETWEEN 2023 AND 2025), 0)::int AS recent
       FROM research_topic_years
       GROUP BY topic
       HAVING AVG(n) FILTER (WHERE year BETWEEN 2019 AND 2021) >= 200
       ORDER BY 2 DESC NULLS LAST LIMIT 10`);
    return rows.map((r) => ({ ...r, growth: Number(r.growth) }));
  });
}

export async function getResearchCorpusStats(): Promise<{ total: number; topics: number }> {
  return cached("research-corpus-stats", 3_600_000, async () => {
    // Beide Zahlen aus Meta-/Statistik-Tabellen — COUNT(*) bzw.
    // COUNT(DISTINCT) über die 45M-Tabelle kosteten beim Kaltstart ~30-40s
    // und liefen nach jedem Server-Neustart erneut. Gepflegt vom
    // Snapshot-Ingest/Sync (#80).
    const row = await q1<{ total: number; topics: number }>(
      `SELECT (SELECT total::int FROM research_corpus_meta) as total,
              (SELECT COUNT(*)::int FROM research_corpus_topics) as topics`);
    return { total: row?.total ?? 0, topics: row?.topics ?? 0 };
  });
}

/** Topic-Facette für die Datalist — aus der materialisierten Statistik-
 *  Tabelle research_corpus_topics (Aufbau im Snapshot-Ingest/Sync, 4,5k
 *  Zeilen), nie aus der 45M-Tabelle selbst. */
export async function getResearchTopics(): Promise<string[]> {
  return cached("research-corpus-topics", 3_600_000, async () => {
    const rows = await q<{ topic: string }>(
      `SELECT topic FROM research_corpus_topics ORDER BY n DESC LIMIT 500`);
    return rows.map((r) => r.topic);
  });
}


/* ---------- Paper-Detailseite + Live-Features (#83) ---------- */

export interface ResearchWorkDetail extends ResearchWork {
  institutions: string | null;
}

/** Ein Werk per OpenAlex-ID (PK-Lookup) inkl. Institutions-String. */
export async function getResearchWorkById(
  id: string,
): Promise<ResearchWorkDetail | null> {
  const row = await q1<ResearchWorkDetail>(
    `SELECT ${RC_COLS}, af.institutions
     FROM research_corpus rc ${RC_JOINS}
     WHERE rc.id = $1`,
    [id]);
  return row ?? null;
}

export interface CorpusRef {
  id: string;
  title: string;
  year: number | null;
  cited_by_count: number | null;
  doi: string | null;
}

/** OpenAlex-IDs (references/related/citing) gegen den lokalen Korpus
 *  auflösen — PK-Lookup, Reihenfolge: meistzitiert zuerst. */
export async function resolveCorpusIds(ids: string[]): Promise<CorpusRef[]> {
  if (!ids.length) return [];
  const rows = await q<CorpusRef>(
    `SELECT id, title, year, cited_by_count, doi FROM research_corpus
     WHERE id = ANY($1) ORDER BY cited_by_count DESC NULLS LAST`,
    [ids.slice(0, 2000)]);
  return rows;
}

/** Lokales Typeahead (#83): Distinct-Aggregate (36k Funder / 82k
 *  Institutionen / ~100k Journals) — ILIKE-Scan reicht, keine API. */
export async function suggestLocal(
  kind: "journal" | "funder" | "institution", qText: string,
): Promise<{ v: string; n: number }[]> {
  const table = kind === "journal" ? "research_journals"
    : kind === "funder" ? "research_funders" : "research_institutions";
  const col = kind === "journal" ? "journal"
    : kind === "funder" ? "funder" : "institution";
  return q<{ v: string; n: number }>(
    `SELECT ${col} AS v, n FROM ${table}
     WHERE ${col} ILIKE $1 ORDER BY n DESC LIMIT 8`,
    [`%${qText}%`]);
}

export interface PatentSignal {
  pub_number: string;
  title: string;
  abstract: string | null;
  url: string;
  published: string | null;
  assignee: string | null;
  family_id: number | null;
  family_size: number | null;
  cpcs: string[];
}

/** Patent Explorer (#74/#78): Volltextsuche über die materialisierte Tabelle
 *  `patent_search` (scripts/build_patent_search_index.py) — gespeicherter
 *  tsvector mit Titel=A/Abstract=B statt eines Ausdrucks-Index auf
 *  raw_entries. Nur so ist der Phrasen-Recheck billig (er liest eine Spalte,
 *  statt den Text pro Kandidatenzeile neu zu zerlegen) und Titeltreffer
 *  ranken vor Abstract-Treffern.
 *  Trefferzahlen sind bei 10k gedeckelt (ein vollständiges COUNT über
 *  Millionen dauert länger als die Suche selbst); Aufrufer zeigen "10,000+". */
const PATENT_COUNT_CLAMP = 10000;
/** Gewichte für ts_rank: {D, C, B, A} — Titel (A) zählt 4x so viel wie der
 *  Abstract (B). */
const PATENT_RANK_WEIGHTS = "'{0.1, 0.2, 0.4, 1.0}'::float4[]";

// Anreicherungs-Spalten pro Trefferzeile (Assignee, Familie, CPC-Chips) —
// identisch für beide Query-Pfade unten.
const PATENT_ROW_COLS = `
       r.pub_number, r.title, NULLIF(r.excerpt, '') as abstract, r.url,
       LEAST(r.published_date, NOW())::date::text as published,
       asg.name as assignee,
       pf.family_id,
       (SELECT COUNT(*)::int FROM patent_family pf2
        WHERE pf2.family_id = pf.family_id) as family_size,
       COALESCE(cp.subs, '{}') as cpcs`;
const PATENT_ROW_JOINS = `
     LEFT JOIN LATERAL (
       SELECT a.name FROM patent_assignee_raw a
       WHERE a.pub_number = r.pub_number ORDER BY a.seq LIMIT 1) asg ON TRUE
     LEFT JOIN patent_family pf ON pf.pub_number = r.pub_number
     LEFT JOIN LATERAL (
       SELECT array_agg(DISTINCT pc.subclass) as subs FROM (
         SELECT subclass FROM patent_cpc
         WHERE pub_number = r.pub_number LIMIT 6) pc) cp ON TRUE`;

export async function getPatentSignals(options: {
  q?: string;
  cpc?: string;
  country?: string;
  /** Exakte Publikationsnummern (US-2023120329-A1) — Router-Pfad #78.
   *  Mehrere, weil dieselbe Veröffentlichung amtlich und im DOCDB-Format
   *  unterschiedlich geschrieben wird (führende Null der Seriennummer). */
  pubExact?: string[];
  /** Nummern-Präfixe ohne Kind-Code (US-11734097-) */
  pubPrefix?: string[];
  /** Anmelder-Teilstring (Trigramm-Suche über patent_assignee_raw.name) */
  company?: string;
  yearFrom?: number;
  yearTo?: number;
  limit?: number;
  offset?: number;
} = {}): Promise<{ rows: PatentSignal[]; total: number; clamped: boolean }> {
  const limit = options.limit ?? 25;
  const offset = options.offset ?? 0;
  const params: unknown[] = [];
  let countSql: string;
  let rowSql: string;

  // Nummern-Pfad: exakter Treffer bzw. alle Kind-Codes einer Nummer. Läuft
  // über idx_raw_pubnum_pattern (text_pattern_ops — die DB-Collation
  // de_DE.UTF-8 macht den normalen btree für Präfixe unbrauchbar).
  if (options.pubExact?.length || options.pubPrefix?.length) {
    // Explizite OR-Kette statt = ANY(...) / LIKE ANY(...): nur so bekommt
    // jede Variante ihren eigenen Index-Range-Scan (Bitmap-OR).
    const exact = options.pubExact ?? [];
    const prefixes = options.pubPrefix ?? [];
    const terms = [
      ...exact.map((v) => { params.push(v); return `r.pub_number = $${params.length}`; }),
      ...prefixes.map((p) => { params.push(`${p}%`); return `r.pub_number LIKE $${params.length}`; }),
    ];
    const where = `(${terms.join(" OR ")})`;
    countSql = `SELECT COUNT(*)::int as cnt FROM raw_entries r WHERE ${where}`;
    params.push(limit, offset);
    rowSql = `SELECT ${PATENT_ROW_COLS}
     FROM raw_entries r
     ${PATENT_ROW_JOINS}
     WHERE ${where}
     ORDER BY r.published_date DESC
     LIMIT $${params.length - 1} OFFSET $${params.length}`;
    const countRow = await q1<{ cnt: number }>(countSql, params.slice(0, -2));
    const rows = await q<PatentSignal>(rowSql, params);
    return {
      rows: rows.map((r) => ({ ...r, cpcs: (r.cpcs as unknown as string[]) ?? [] })),
      total: countRow?.cnt ?? 0,
      clamped: false,
    };
  }

  // Firmen-Pfad (#78 Stufe 2). EXISTS statt einer eigenen DISTINCT-Liste:
  // mit dem GIN-Trigramm auf patent_assignee_raw.name schätzt der Planer die
  // Selektivität richtig und treibt selbst von der Anmelder-Seite — gemessen
  // 0,01–0,13s für seltene wie für große Anmelder. Eine handgebaute
  // DISTINCT-Unterabfrage war deutlich langsamer (Toyota 8,4s), weil sie alle
  // Treffer dedupliziert, bevor das LIMIT greifen kann.
  if (options.company) {
    params.push(`%${options.company}%`);
    const nameParam = `$${params.length}`;
    const companyExists = `EXISTS (SELECT 1 FROM patent_assignee_raw a
        WHERE a.pub_number = r.pub_number AND a.name ILIKE ${nameParam})`;
    const extra: string[] = [];
    if (options.q) {
      params.push(options.q);
      // Textfilter im Firmen-Pfad ebenfalls über patent_search (#78 Stufe 3)
      extra.push(`EXISTS (SELECT 1 FROM patent_search ps WHERE ps.id = r.id
                  AND ps.tsv @@ websearch_to_tsquery('english', $${params.length}))`);
    }
    if (options.cpc) {
      params.push(options.cpc);
      extra.push(`EXISTS (SELECT 1 FROM patent_cpc pc
                  WHERE pc.pub_number = r.pub_number AND pc.subclass = $${params.length})`);
    }
    if (options.country) {
      params.push(options.country + "-%");
      extra.push(`r.pub_number LIKE $${params.length}`);
    }
    if (options.yearFrom !== undefined) {
      params.push(`${options.yearFrom}-01-01`);
      extra.push(`r.published_date >= $${params.length}::date`);
    }
    if (options.yearTo !== undefined) {
      params.push(`${options.yearTo}-12-31`);
      extra.push(`r.published_date <= $${params.length}::date`);
    }
    const w = ["r.pub_number IS NOT NULL", companyExists, ...extra].join(" AND ");
    const countRow = await q1<{ cnt: number }>(
      `SELECT COUNT(*)::int as cnt FROM (
         SELECT 1 FROM raw_entries r WHERE ${w}
         LIMIT ${PATENT_COUNT_CLAMP + 1}) x`, [...params]);
    const total = countRow?.cnt ?? 0;
    params.push(limit, offset);
    const rows = await q<PatentSignal>(
      `SELECT ${PATENT_ROW_COLS}
       FROM raw_entries r
       ${PATENT_ROW_JOINS}
       WHERE ${w}
       ORDER BY r.published_date DESC
       LIMIT $${params.length - 1} OFFSET $${params.length}`, params);
    return {
      rows: rows.map((r) => ({ ...r, cpcs: (r.cpcs as unknown as string[]) ?? [] })),
      total: Math.min(total, PATENT_COUNT_CLAMP),
      clamped: total > PATENT_COUNT_CLAMP,
    };
  }

  const yearClause = (col: string) => {
    const parts: string[] = [];
    if (options.yearFrom !== undefined) {
      params.push(`${options.yearFrom}-01-01`);
      parts.push(`${col} >= $${params.length}::date`);
    }
    if (options.yearTo !== undefined) {
      params.push(`${options.yearTo}-12-31`);
      parts.push(`${col} <= $${params.length}::date`);
    }
    return parts;
  };

  if (options.cpc && !options.q) {
    // Browse-Pfad Technologie-Facette: patent_cpc (128M Zeilen) ist dafür
    // unbrauchbar (>240s gemessen) — die materialisierte Tabelle
    // patent_explorer_cpc (scripts/build_patent_explorer_index.py, kuratierte
    // Subclasses) liefert die Datums-Sortierung direkt aus ihrem Index.
    params.push(options.cpc);
    let w = `pcc.subclass = $1`;
    if (options.country) {
      params.push(options.country + "-%");
      w += ` AND pcc.pub_number LIKE $${params.length}`;
    }
    for (const c of yearClause("pcc.published")) w += ` AND ${c}`;
    countSql = `SELECT COUNT(*)::int as cnt FROM (
       SELECT 1 FROM patent_explorer_cpc pcc WHERE ${w}
       LIMIT ${PATENT_COUNT_CLAMP + 1}) x`;
    params.push(limit, offset);
    rowSql = `SELECT ${PATENT_ROW_COLS}
     FROM patent_explorer_cpc pcc
     JOIN raw_entries r ON r.pub_number = pcc.pub_number
     ${PATENT_ROW_JOINS}
     WHERE ${w}
     ORDER BY pcc.published DESC
     LIMIT $${params.length - 1} OFFSET $${params.length}`;
  } else if (options.q) {
    // Volltext-Pfad über patent_search: Filter, Sortierung und Ranking laufen
    // komplett in der schlanken Suchtabelle, raw_entries wird erst für die
    // 25 Anzeigezeilen angefasst.
    params.push(options.q);
    const tq = `websearch_to_tsquery('english', $${params.length})`;
    const where: string[] = [`ps.tsv @@ ${tq}`];
    if (options.cpc) {
      params.push(options.cpc);
      where.push(`EXISTS (SELECT 1 FROM patent_explorer_cpc pcc
                  WHERE pcc.pub_number = ps.pub_number
                    AND pcc.subclass = $${params.length})`);
    }
    if (options.country) {
      params.push(options.country + "-%");
      where.push(`ps.pub_number LIKE $${params.length}`);
    }
    where.push(...yearClause("ps.published"));
    const w = where.join(" AND ");
    countSql = `SELECT COUNT(*)::int as cnt FROM (
       SELECT 1 FROM patent_search ps WHERE ${w} LIMIT ${PATENT_COUNT_CLAMP + 1}) x`;
    const countRow = await q1<{ cnt: number }>(countSql, [...params]);
    const total = countRow?.cnt ?? 0;
    const clamped = total > PATENT_COUNT_CLAMP;
    // Relevanz-Reihung nur bei überschaubarer Treffermenge: bei Zehntausenden
    // Treffern müsste jede Zeile bewertet und sortiert werden, und die
    // Reihung trennt dort ohnehin kaum — dann ist "neueste zuerst" sowohl
    // schneller (Datums-Index) als auch nützlicher.
    // Die Reihung muss die Treffer-Unterabfrage überleben: der Rang wird als
    // Spalte mitgenommen und außen erneut angewandt — ein äußeres
    // "ORDER BY published" allein würde die Relevanz-Sortierung zerstören.
    const rankCol = clamped
      ? `0::float4 AS rk`
      : `ts_rank(${PATENT_RANK_WEIGHTS}, ps.tsv, ${tq}) AS rk`;
    const order = clamped
      ? `ps.published DESC`
      : `ts_rank(${PATENT_RANK_WEIGHTS}, ps.tsv, ${tq}) DESC, ps.published DESC`;
    params.push(limit, offset);
    rowSql = `SELECT ${PATENT_ROW_COLS}
     FROM (SELECT ps.id, ps.pub_number, ps.published, ${rankCol}
           FROM patent_search ps
           WHERE ${w} ORDER BY ${order}
           LIMIT $${params.length - 1} OFFSET $${params.length}) hit
     JOIN raw_entries r ON r.id = hit.id
     ${PATENT_ROW_JOINS}
     ORDER BY hit.rk DESC, hit.published DESC`;
    const rows = await q<PatentSignal>(rowSql, params);
    return {
      rows: rows.map((r) => ({ ...r, cpcs: (r.cpcs as unknown as string[]) ?? [] })),
      total: Math.min(total, PATENT_COUNT_CLAMP),
      clamped,
    };
  } else {
    const where: string[] = ["r.pub_number IS NOT NULL"];
    if (options.cpc) {
      params.push(options.cpc);
      where.push(`EXISTS (SELECT 1 FROM patent_cpc pc
                  WHERE pc.pub_number = r.pub_number AND pc.subclass = $${params.length})`);
    }
    if (options.country) {
      params.push(options.country + "-%");
      where.push(`r.pub_number LIKE $${params.length}`);
    }
    where.push(...yearClause("r.published_date"));
    const w = where.join(" AND ");
    countSql = `SELECT COUNT(*)::int as cnt FROM (
       SELECT 1 FROM raw_entries r WHERE ${w} LIMIT ${PATENT_COUNT_CLAMP + 1}) x`;
    params.push(limit, offset);
    // ORDER BY ohne NULLS LAST: idx_raw_patent_pubdate ist DESC (= NULLS
    // FIRST) — nur so trägt der Index die Sortierung. Patente ohne
    // published_date gibt es nicht (0 von 19,6M, gemessen 2026-08-09).
    rowSql = `SELECT ${PATENT_ROW_COLS}
     FROM raw_entries r
     ${PATENT_ROW_JOINS}
     WHERE ${w}
     ORDER BY r.published_date DESC
     LIMIT $${params.length - 1} OFFSET $${params.length}`;
  }

  const countRow = await q1<{ cnt: number }>(countSql, params.slice(0, -2));
  const total = countRow?.cnt ?? 0;
  const rows = await q<PatentSignal>(rowSql, params);
  return {
    rows: rows.map((r) => ({ ...r, cpcs: (r.cpcs as unknown as string[]) ?? [] })),
    total: Math.min(total, PATENT_COUNT_CLAMP),
    clamped: total > PATENT_COUNT_CLAMP,
  };
}

/** "Meintest du Firma …?" — prüft den Suchtext gegen die harmonisierten
 *  PATSTAT-Anmeldernamen (tip_leading_applicants, 1.300 Zeilen, gecacht).
 *  Bewusst gegen diese kleine Liste statt gegen die 22,5M Rohnamen: sie
 *  enthält genau die Akteure, nach denen Nutzer suchen, ist in Millisekunden
 *  durchsucht und liefert die aufgeräumte Schreibweise. */
export async function suggestCompany(text: string): Promise<string | null> {
  const t = text.trim();
  if (t.length < 3) return null;
  const names = await cached("psn-names", 3_600_000, async () =>
    q<{ psn_name: string; families: number }>(
      `SELECT psn_name, SUM(families)::int as families FROM tip_leading_applicants
       GROUP BY 1 ORDER BY 2 DESC`));
  const needle = t.toLowerCase();
  // Nur wenn der Name mit dem Suchtext BEGINNT — sonst schlüge "battery"
  // jede "… BATTERY CO" vor und der Hinweis würde bei Fachbegriffen zum
  // Rauschen. Liste ist nach Familienzahl sortiert, der erste Treffer ist
  // also der größte Anmelder dieses Namens.
  const hit = names.find((n) => n.psn_name.toLowerCase().startsWith(needle));
  return hit ? hit.psn_name : null;
}

export async function getPatentStats(): Promise<{ total: number; assignees: number }> {
  return cached("patent-stats", 3_600_000, async () => {
    const row = await q1<{ total: number; assignees: number }>(
      `SELECT (SELECT COUNT(*)::int FROM raw_entries WHERE pub_number IS NOT NULL) as total,
              (SELECT COUNT(DISTINCT pub_number)::int FROM patent_assignee_raw) as assignees`);
    return { total: row?.total ?? 0, assignees: row?.assignees ?? 0 };
  });
}

/** Technologie-Intelligenz aus den PATSTAT-TIP-Referenztabellen (#14):
 *  Top-Anmelder (harmonisierte PSN-Namen) + Sektor-Zeilen für die
 *  Uni→Industrie-Transfer-Kurve. Anmeldejahre nur bis 2023 — jüngere
 *  Anmeldungen sind wegen der 18-Monats-Publikationsfrist systematisch
 *  untererfasst und würden einen fallenden Trend vortäuschen. */
export interface PatentTechApplicant {
  rank: number;
  name: string;
  sector: string | null;
  ctry: string | null;
  families: number;
}

export async function getPatentTechIntel(cpc: string): Promise<{
  applicants: PatentTechApplicant[];
  sectorRows: { filing_year: number; psn_sector: string; families: number }[];
  npl: { publn_year: number; citations: number; npl_citations: number; median_lag_years: number | null }[];
  survival: { filing_year: number; cohort_size: number; age_years: number; cessations: number }[];
  countries: { filing_year: number; ctry: string; families: number }[];
  intl: { filing_year: number; families: number; multi_office_families: number; pct_families: number }[];
  collabs: { rank: number; university: string; company: string; families: number }[];
  groups: { cpc_group: string; filing_year: number; families: number }[];
  nace: { nace2_descr: string | null; weighted_applications: number }[];
  oppositions: { event_year: number; event_code: string; applications: number }[];
} | null> {
  return cached(`patent-tech-${cpc}`, 3_600_000, async () => {
    const applicants = await q<PatentTechApplicant>(
      `SELECT rank, psn_name as name, psn_sector as sector, ctry, families
       FROM tip_leading_applicants WHERE cpc_subclass = $1
       ORDER BY rank LIMIT 10`, [cpc]);
    if (applicants.length === 0) return null;
    // Runde-2-Referenztabellen (#75) — alles winzige Aggregate, ein Roundtrip je Block
    const [sectorRows, npl, survival, countries, intl, collabs, groups, nace, oppositions] =
      await Promise.all([
        q<{ filing_year: number; psn_sector: string; families: number }>(
          `SELECT filing_year, psn_sector, families FROM tip_sector_shares
           WHERE cpc_subclass = $1 AND filing_year BETWEEN 2010 AND 2023
           ORDER BY filing_year`, [cpc]),
        q<{ publn_year: number; citations: number; npl_citations: number; median_lag_years: number | null }>(
          `SELECT publn_year, citations, npl_citations, median_lag_years
           FROM tip_npl_share
           WHERE cpc_subclass = $1 AND publn_year BETWEEN 2010 AND 2023
           ORDER BY publn_year`, [cpc]),
        q<{ filing_year: number; cohort_size: number; age_years: number; cessations: number }>(
          `SELECT filing_year, cohort_size, age_years, cessations FROM tip_survival
           WHERE cpc_subclass = $1`, [cpc]),
        q<{ filing_year: number; ctry: string; families: number }>(
          `SELECT filing_year, ctry, families FROM tip_country_race
           WHERE cpc_subclass = $1`, [cpc]),
        q<{ filing_year: number; families: number; multi_office_families: number; pct_families: number }>(
          `SELECT filing_year, families, multi_office_families, pct_families
           FROM tip_internationalization WHERE cpc_subclass = $1
           ORDER BY filing_year`, [cpc]),
        q<{ rank: number; university: string; company: string; families: number }>(
          `SELECT rank, university, company, families FROM tip_collaborations
           WHERE cpc_subclass = $1 ORDER BY rank LIMIT 3`, [cpc]),
        q<{ cpc_group: string; filing_year: number; families: number }>(
          `SELECT cpc_group, filing_year, families FROM tip_cpc_groups
           WHERE cpc_subclass = $1`, [cpc]),
        q<{ nace2_descr: string | null; weighted_applications: number }>(
          `SELECT nace2_descr, weighted_applications FROM tip_nace2_bridge
           WHERE cpc_subclass = $1 ORDER BY weighted_applications DESC LIMIT 3`, [cpc]),
        q<{ event_year: number; event_code: string; applications: number }>(
          `SELECT event_year, event_code, applications FROM tip_ep_oppositions
           WHERE cpc_subclass = $1 AND event_code IN ('26','26N')`, [cpc]),
      ]);
    return { applicants, sectorRows, npl, survival, countries, intl, collabs, groups, nace, oppositions };
  });
}


export async function getTopTrendsByEngagement(limit: number = 10): Promise<Trend[]> {
  const rows = await q(
    `SELECT ${TREND_COLS},
        LEAST(re.published_date, t.created_at)::text as source_date, s.source_type as source_type,
        COALESCE(m.page_views, 0) as views
     FROM trends t
     LEFT JOIN raw_entries re ON t.raw_entry_id = re.id
     LEFT JOIN sources s ON re.source_id = s.id
     LEFT JOIN trend_metrics m ON t.id = m.trend_id
     WHERE t.status = 'published'
     ORDER BY views DESC, t.trend_score DESC
     LIMIT $1`,
    [limit]
  );
  return rows.map(parseTrendRow);
}

// ---------------------------------------------------------------------------
// Composite filter query (Phase 2 — filter & sort)
// ---------------------------------------------------------------------------

export type TrendsSortBy =
  | "date_desc"
  | "date_asc"
  | "score_desc"
  | "engagement_desc"
  | "source_date_desc";

export type TrendsDateRange = "1d" | "7d" | "30d" | "all";

export type TrendsViewMode = "grid" | "list";

export interface TrendsFilterOptions {
  status?: "published" | "all";
  verticals?: Vertical[];
  pestel?: PestelDimension[];
  signal_types?: TrendSignalType[];
  mega_trend?: string;
  exclude_sources?: string[];
  min_trend_score?: number; // 0–100 (percentage UX), converted to 0–1 internally
  date_range?: TrendsDateRange;
  /** Free archive window (issue #70): hard cap on sort_date age in days,
   *  ANDed with any user-chosen date_range. null/undefined = unlimited. */
  max_age_days?: number | null;
  search?: string;
  sort_by?: TrendsSortBy;
  limit?: number;
  offset?: number;
}

/** The tsvector expression MUST textually match the idx_trends_fts GIN index
 *  expression, or Postgres won't use the index. */
const FTS_VECTOR =
  "to_tsvector('english', coalesce(title_en,'') || ' ' || coalesce(summary_en,'') || ' ' || coalesce(tags::text,''))";

function buildFilterClauses(options: TrendsFilterOptions): {
  where: string;
  params: unknown[];
  extraJoins: string;
} {
  const where: string[] = ["1=1"];
  const params: unknown[] = [];
  let extraJoins = "";
  const p = (v: unknown): string => {
    params.push(v);
    return `$${params.length}`;
  };

  // Status default = published
  const status = options.status ?? "published";
  if (status !== "all") {
    where.push(`t.status = ${p(status)}`);
  }

  if (options.verticals && options.verticals.length > 0) {
    where.push(`t.primary_vertical = ANY(${p(options.verticals)}::text[])`);
  }

  if (options.pestel && options.pestel.length > 0) {
    // jsonb "any of these keys/elements" operator
    where.push(`t.pestel ?| ${p(options.pestel)}::text[]`);
  }

  if (options.signal_types && options.signal_types.length > 0) {
    where.push(`t.trend_signal_type = ANY(${p(options.signal_types)}::text[])`);
  }

  if (options.mega_trend) {
    where.push(`t.mega_trend = ${p(options.mega_trend)}`);
  }

  if (options.exclude_sources && options.exclude_sources.length > 0) {
    where.push(`COALESCE(t.source_name, '') != ALL(${p(options.exclude_sources)}::text[])`);
  }

  if (options.min_trend_score !== undefined && options.min_trend_score > 0) {
    // UI passes 0–100, DB stores 0–1
    where.push(`COALESCE(t.trend_score, 0) >= ${p(options.min_trend_score / 100)}`);
  }

  if (options.date_range && options.date_range !== "all") {
    const interval =
      options.date_range === "1d" ? "1 day"
      : options.date_range === "7d" ? "7 days"
      : "30 days";
    where.push(`t.sort_date >= NOW() - ${p(interval)}::interval`);
  }

  if (options.max_age_days != null) {
    where.push(`t.sort_date >= ${p(windowStartIso(options.max_age_days))}::timestamptz`);
  }

  const search = options.search?.trim();
  if (search && search.length > 0) {
    where.push(`${FTS_VECTOR} @@ websearch_to_tsquery('english', ${p(search)})`);
  }

  if (options.sort_by === "engagement_desc") {
    extraJoins += " LEFT JOIN trend_metrics m ON m.trend_id = t.id";
  }

  return { where: where.join(" AND "), params, extraJoins };
}

const CAPPED_DATE = "t.sort_date";

/** Every branch ends in `t.id` so ties are stable: feed timestamps sit on
 *  full hours (744 tie groups / 3,114 rows in the 30-day window), and
 *  Postgres returns tied rows in arbitrary order — page boundaries and the
 *  static export flipped between builds without it (spike 2026-09-02, #6). */
function buildOrderBy(sort: TrendsSortBy | undefined): string {
  switch (sort) {
    case "date_asc":
      return `ORDER BY ${CAPPED_DATE} ASC, t.id ASC`;
    case "score_desc":
      return `ORDER BY t.trend_score DESC NULLS LAST, ${CAPPED_DATE} DESC NULLS LAST, t.id DESC`;
    case "engagement_desc":
      return `ORDER BY COALESCE(m.page_views, 0) DESC, ${CAPPED_DATE} DESC, t.id DESC`;
    case "source_date_desc":
      return `ORDER BY ${CAPPED_DATE} DESC NULLS LAST, t.created_at DESC, t.id DESC`;
    case "date_desc":
    default:
      return `ORDER BY ${CAPPED_DATE} DESC NULLS LAST, t.id DESC`;
  }
}

export async function getTrendsFiltered(options: TrendsFilterOptions = {}): Promise<Trend[]> {
  const { where, params, extraJoins } = buildFilterClauses(options);
  params.push(options.limit ?? 12, options.offset ?? 0);
  const query =
    TREND_SELECT +
    extraJoins +
    ` WHERE ${where} ` +
    buildOrderBy(options.sort_by) +
    ` LIMIT $${params.length - 1} OFFSET $${params.length}`;
  return (await q(query, params)).map(parseTrendRow);
}

export async function getTrendsFilteredCount(
  options: TrendsFilterOptions = {}
): Promise<number> {
  const { where, params, extraJoins } = buildFilterClauses(options);
  const query =
    `SELECT COUNT(*)::int as cnt FROM trends t` + extraJoins + ` WHERE ${where}`;
  const row = await q1<{ cnt: number }>(query, params);
  return row?.cnt ?? 0;
}

export interface MethodologyStats {
  analyzed: number;
  published: number;
  sources: number;
  megaTrends: number;
  tierCounts: Record<string, number>;
  dateSpan: { first: string | null; last: string | null };
}

/**
 * Corpus stats for the landing / methodology trust pages. Cached 1h — these
 * are full-table aggregations over ~1M rows that used to run per request and
 * made both pages take 7-9s (ONB-01/ARCH-02).
 */
export async function getMethodologyStats(): Promise<MethodologyStats> {
  // Static export: the build computes the numbers once (scripts/methodology_stats.py)
  // and points METHODOLOGY_STATS_FILE at the JSON — the live aggregates below ran
  // into the 20 s statement_timeout under six export workers (2026-09-05) and
  // would make the export non-deterministic anyway.
  const snapshot = readMethodologyStatsSnapshot();
  if (snapshot) return snapshot;
  return cached("methodology-stats", 3_600_000, fetchMethodologyStats);
}

export interface BriefingStats {
  sources: number | null;
  analyzed: number | null;
  published: number | null;
  patents: number | null;
  /** planner estimate (pg_class.reltuples) — an exact COUNT over 45 M rows times out */
  researchWorks: number | null;
}

/**
 * Cheap, never-failing corpus numbers for the customer briefing
 * (/trends/foresight/pitch). getMethodologyStats() runs a MIN/MAX over all
 * raw_entries and a three-way join over 1.7 M trends — both exceed the 20 s
 * statement timeout on a cold cache and took the deck down with a 500
 * (2026-09-13). Here every number is its own query, each failure becomes
 * null (rendered as "—"), and the 45 M-row research corpus is read from the
 * planner estimate instead of counted. Cached 1 h.
 */
export async function getBriefingStats(): Promise<BriefingStats> {
  return cached("briefing-stats", 3_600_000, async () => {
    const one = async (sql: string): Promise<number | null> => {
      try {
        const r = await q1<{ c: number | string }>(sql);
        return r?.c == null ? null : Number(r.c);
      } catch {
        return null;
      }
    };
    const [sources, analyzed, published, patents, researchWorks] = await Promise.all([
      one("SELECT COUNT(*)::int c FROM sources WHERE active = true"),
      one("SELECT COUNT(*)::int c FROM trends"),
      one("SELECT COUNT(*)::int c FROM trends WHERE status = 'published'"),
      one("SELECT COUNT(*)::int c FROM raw_entries WHERE pub_number IS NOT NULL"),
      one("SELECT reltuples::bigint c FROM pg_class WHERE relname = 'research_corpus'"),
    ]);
    return { sources, analyzed, published, patents, researchWorks };
  });
}

export function readMethodologyStatsSnapshot(
  file: string | undefined = process.env.METHODOLOGY_STATS_FILE
): MethodologyStats | null {
  if (!file) return null;
  try {
    const raw = JSON.parse(fs.readFileSync(file, "utf-8")) as Partial<MethodologyStats>;
    if (typeof raw.analyzed !== "number" || typeof raw.published !== "number") return null;
    return {
      analyzed: raw.analyzed,
      published: raw.published,
      sources: raw.sources ?? 0,
      megaTrends: raw.megaTrends ?? 0,
      tierCounts: raw.tierCounts ?? {},
      dateSpan: raw.dateSpan ?? { first: null, last: null },
    };
  } catch {
    return null;
  }
}

async function fetchMethodologyStats(): Promise<MethodologyStats> {
  const analyzed = (await q1<{ c: number }>("SELECT COUNT(*)::int c FROM trends"))?.c ?? 0;
  const published =
    (await q1<{ c: number }>("SELECT COUNT(*)::int c FROM trends WHERE status = 'published'"))?.c ?? 0;
  const sources =
    (await q1<{ c: number }>("SELECT COUNT(*)::int c FROM sources WHERE active = true"))?.c ?? 0;
  const megaTrends =
    (await q1<{ c: number }>(
      "SELECT COUNT(DISTINCT mega_trend)::int c FROM trends WHERE mega_trend IS NOT NULL AND mega_trend != ''"
    ))?.c ?? 0;
  // Lead-time tiers via source_type + patent flag (mirrors lead_time_discoverer).
  const tierRows = await q<{ tier: string; c: number }>(
    `SELECT
       CASE
         WHEN re.pub_number IS NOT NULL THEN 'patent'
         WHEN s.source_type = 'research' THEN 'science'
         WHEN s.source_type = 'api' AND (s.name LIKE '%NSF%' OR s.name LIKE '%NIH%'
              OR s.name LIKE '%OpenAIRE%' OR s.name LIKE '%UKRI%' OR s.name LIKE '%RePORTER%'
              OR s.name LIKE '%Gateway to Research%') THEN 'funding'
         WHEN s.source_type = 'api' AND (s.name LIKE '%arXiv%' OR s.name LIKE '%rxiv%'
              OR s.name LIKE '%Preprint%') THEN 'science'
         ELSE 'market'
       END AS tier,
       COUNT(*)::int AS c
     FROM trends t
     JOIN raw_entries re ON t.raw_entry_id = re.id
     JOIN sources s ON re.source_id = s.id
     GROUP BY tier`
  );
  const tierCounts: Record<string, number> = {};
  for (const r of tierRows) tierCounts[r.tier] = r.c;
  const span = await q1<{ f: string | null; l: string | null }>(
    `SELECT MIN(to_char(published_date, 'YYYY-MM')) f, MAX(to_char(published_date, 'YYYY-MM')) l
     FROM raw_entries WHERE published_date IS NOT NULL AND published_date <= NOW()`
  );
  return {
    analyzed,
    published,
    sources,
    megaTrends,
    tierCounts,
    dateSpan: { first: span?.f ?? null, last: span?.l ?? null },
  };
}

export async function getTopSourcesByCount(
  limit: number = 20,
  status: string = "published"
): Promise<Array<{ source_name: string; count: number }>> {
  return cached(`top-sources:${limit}:${status}`, 3_600_000, () =>
    fetchTopSourcesByCount(limit, status)
  );
}

async function fetchTopSourcesByCount(
  limit: number,
  status: string
): Promise<Array<{ source_name: string; count: number }>> {
  const statusClause = status === "all" ? "" : " AND status = $2";
  const params: unknown[] = status === "all" ? [limit] : [limit, status];
  const rows = await q<{ source_name: string; cnt: number }>(
    `SELECT source_name, COUNT(*)::int as cnt
     FROM trends
     WHERE source_name IS NOT NULL AND source_name != ''${statusClause}
     GROUP BY source_name
     ORDER BY cnt DESC
     LIMIT $1`,
    params
  );
  return rows.map((r) => ({ source_name: r.source_name, count: r.cnt }));
}

/**
 * Vertical counts scoped to the *current filter set minus the vertical filter*.
 * Powers the multi-select vertical chips so toggling never collapses the UI
 * to zero for other verticals.
 */
export async function getVerticalCountsScoped(
  options: TrendsFilterOptions = {}
): Promise<Record<string, number>> {
  const scoped: TrendsFilterOptions = { ...options, verticals: undefined };
  const { where, params, extraJoins } = buildFilterClauses(scoped);
  const rows = await q<{ primary_vertical: string; cnt: number }>(
    `SELECT t.primary_vertical, COUNT(*)::int as cnt
     FROM trends t` +
      extraJoins +
      ` WHERE ${where}
     GROUP BY t.primary_vertical
     ORDER BY cnt DESC`,
    params
  );
  const result: Record<string, number> = {};
  for (const row of rows) {
    if (row.primary_vertical) result[row.primary_vertical] = row.cnt;
  }
  return result;
}

export async function getVerticalCounts(status?: string): Promise<Record<string, number>> {
  return cached(`vertical-counts:${status ?? "all"}`, 600_000, () =>
    fetchVerticalCounts(status)
  );
}

async function fetchVerticalCounts(status?: string): Promise<Record<string, number>> {
  const params: unknown[] = [];
  let query = "SELECT primary_vertical, COUNT(*)::int as cnt FROM trends t WHERE 1=1";
  if (status) {
    params.push(status);
    query += ` AND t.status = $${params.length}`;
  }
  query += " GROUP BY t.primary_vertical ORDER BY cnt DESC";
  const rows = await q<{ primary_vertical: string; cnt: number }>(query, params);
  const result: Record<string, number> = {};
  for (const row of rows) {
    if (row.primary_vertical) result[row.primary_vertical] = row.cnt;
  }
  return result;
}

/**
 * Source-link-rot lookup (#48). dead_links is populated by
 * `scripts/check_source_links.py --mark`, but that table only exists once
 * `scripts/migrate_dead_links.py` has been run by hand against this DB — an
 * additive migration in this repo is NEVER wired into automatic init, so a
 * freshly deployed or not-yet-migrated DB legitimately lacks the table.
 *
 * to_regclass() is a cheap, non-throwing existence check (no exception on a
 * missing relation, unlike SELECTing from it directly), and its result is
 * cached for the process lifetime of the TTL so a still-missing table isn't
 * re-checked on every article view. Everything is additionally wrapped in
 * try/catch: any surprise here (permissions, a dropped connection) must
 * degrade to "no badge", never crash the article page.
 */
async function deadLinksTableExists(): Promise<boolean> {
  return cached("dead-links-table-exists", 600_000, async () => {
    try {
      const row = await q1<{ reg: string | null }>(
        "SELECT to_regclass('public.dead_links')::text as reg"
      );
      return row?.reg != null;
    } catch (e) {
      console.error("dead_links existence check failed:", e);
      return false;
    }
  });
}

/** Only a check_count >= 2 (confirmed, per the 2-strike rule in
 *  check_source_links.py) is surfaced — a single blip never shows a badge. */
export async function isSourceLinkDead(sourceUrl: string): Promise<boolean> {
  if (!sourceUrl) return false;
  try {
    if (!(await deadLinksTableExists())) return false;
    const row = await q1<{ url: string }>(
      "SELECT url FROM dead_links WHERE url = $1 AND check_count >= 2",
      [sourceUrl]
    );
    return row != null;
  } catch (e) {
    console.error("dead_links lookup failed:", e);
    return false;
  }
}

/* ---------- Newsletter editions (static export, Schritt E) ---------- */

/**
 * Newest-first index of the weekly briefings for the public archive
 * (/trends/newsletter, generateStaticParams of /trends/newsletter/[edition],
 * sitemap). `limit` = PUBLIC_NEWSLETTER_EDITIONS (lib/archiveWindow.ts).
 * A missing table (fresh DB) yields [] instead of a failed build.
 */
export async function getNewsletterEditionIndex(limit: number): Promise<EditionSummary[]> {
  const exists = await q1<{ ok: string | null }>(
    "SELECT to_regclass('newsletter_editions')::text AS ok"
  );
  if (!exists?.ok) return [];
  return q<EditionSummary>(
    `SELECT id, year, week, total_signals, created_at::text AS created_at
       FROM newsletter_editions
      ORDER BY year DESC, week DESC
      LIMIT $1`,
    [limit]
  );
}

/** One edition with its TEXT JSON columns parsed; null when absent. */
export async function getNewsletterEdition(year: number, week: number): Promise<NewsletterEdition | null> {
  const row = await q1<Record<string, unknown>>(
    `SELECT id, year, week, editorial, vertical_summaries, mega_trend_radar, trend_refs,
            total_signals, created_at::text AS created_at, deep_dive
       FROM newsletter_editions
      WHERE year = $1 AND week = $2
      LIMIT 1`,
    [year, week]
  );
  if (!row) return null;
  const parse = <T,>(v: unknown, fallback: T): T => {
    if (typeof v !== "string") return (v as T) ?? fallback;
    try {
      return JSON.parse(v) as T;
    } catch {
      return fallback;
    }
  };
  return {
    id: Number(row.id),
    year: Number(row.year),
    week: Number(row.week),
    editorial: typeof row.editorial === "string" ? row.editorial : "",
    vertical_summaries: parse<Record<string, string>>(row.vertical_summaries, {}),
    mega_trend_radar: parse<MegaTrendRadarEntry[]>(row.mega_trend_radar, []),
    trend_refs: parse<Record<string, TrendRef[]>>(row.trend_refs, {}),
    total_signals: Number(row.total_signals ?? 0),
    created_at: String(row.created_at ?? ""),
    // JSONB arrives parsed from pg; a SQLite-style TEXT value is parsed here.
    deep_dive: parse<NewsletterDeepDive | null>(row.deep_dive, null),
  };
}

export interface TrendLinkTarget {
  slug: string;
  source_url: string | null;
  /** Same predicate as getPublicWindowSlugs: published AND inside the window. */
  in_window: boolean;
}

/**
 * Window membership + primary source for the article slugs an edition
 * links (lib/newsletterEditions.ts collectEditionSlugs). One round trip per
 * edition; slugs unknown to the table are simply absent (→ plain text).
 */
export async function getTrendLinkTargets(slugs: string[], windowDays: number): Promise<TrendLinkTarget[]> {
  if (slugs.length === 0) return [];
  return q<TrendLinkTarget>(
    `SELECT t.slug, t.source_url,
            (t.status = 'published' AND t.sort_date >= $2::timestamptz) AS in_window
       FROM trends t
      WHERE t.slug = ANY($1::text[])
      ORDER BY t.slug`,
    [slugs, windowStartIso(windowDays)]
  );
}
