import path from "path";
import fs from "fs";
import yaml from "js-yaml";
import { q, q1 } from "./pg";
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

/** SELECT for trend queries — joins raw_entries for source_date + source_type,
 *  capping future dates to now. */
const TREND_SELECT = `SELECT ${TREND_COLS},
   LEAST(re.published_date, NOW())::text as source_date, s.source_type as source_type
   FROM trends t
   LEFT JOIN raw_entries re ON t.raw_entry_id = re.id
   LEFT JOIN sources s ON re.source_id = s.id`;

export async function getTrends(options: {
  status?: string;
  vertical?: Vertical;
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
  params.push(options.limit ?? 50, options.offset ?? 0);
  query += ` ORDER BY t.sort_date DESC NULLS LAST LIMIT $${params.length - 1} OFFSET $${params.length}`;
  return (await q(query, params)).map(parseTrendRow);
}

export async function getTrendBySlug(slug: string): Promise<Trend | null> {
  const row = await q1(TREND_SELECT + " WHERE t.slug = $1", [slug]);
  return row ? parseTrendRow(row) : null;
}

export async function getTrendsCount(options: {
  status?: string;
  vertical?: Vertical;
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
  const row = await q1<{ cnt: number }>(query, params);
  return row?.cnt ?? 0;
}

export async function getTrendsByMegaTrend(megaTrend: string, options: {
  status?: string;
  limit?: number;
} = {}): Promise<Trend[]> {
  const params: unknown[] = [megaTrend];
  let query = TREND_SELECT + " WHERE t.mega_trend = $1";
  if (options.status) {
    params.push(options.status);
    query += ` AND t.status = $${params.length}`;
  }
  params.push(options.limit ?? 50);
  query += ` ORDER BY t.sort_date DESC NULLS LAST LIMIT $${params.length}`;
  return (await q(query, params)).map(parseTrendRow);
}

export interface MegaTrendInfo {
  mega_trend: string;
  count: number;
  verticals: string[];
  name_en: string;
  description: string;
  momentum: "rising" | "stable" | "declining" | "emerging";
  cluster_strength: "strong" | "moderate" | "fragmented";
  signal_count: number;
  horizon: string;
  /** Earliest source date for any trend in this mega-trend (ISO string). */
  first_seen: string | null;
  /** Number of signals published in the last 30 days. */
  signals_30d: number;
}

function loadMegaTrendYaml(): Record<string, {
  name_en: string; description: string;
  momentum: string; cluster_strength: string; signal_count: number; horizon: string;
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
        momentum: (mt.momentum as string) || "stable",
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
  const params: unknown[] = [];
  let query = `SELECT t.mega_trend, COUNT(*)::int as cnt,
     STRING_AGG(DISTINCT t.primary_vertical, ',') as verts,
     MIN(t.sort_date)::text as first_seen,
     SUM(CASE WHEN t.sort_date >= NOW() - INTERVAL '30 days' THEN 1 ELSE 0 END)::int as signals_30d
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
  }>(query, params);

  const yamlData = loadMegaTrendYaml();

  return rows.map((r) => {
    const meta = yamlData[r.mega_trend] || {};
    return {
      mega_trend: r.mega_trend,
      count: r.cnt,
      verticals: r.verts ? r.verts.split(",") : [],
      name_en: meta.name_en || r.mega_trend.replace(/_/g, " "),
      description: meta.description || "",
      momentum: (meta.momentum || "stable") as MegaTrendInfo["momentum"],
      cluster_strength: (meta.cluster_strength || "fragmented") as MegaTrendInfo["cluster_strength"],
      signal_count: r.signals_30d || 0,
      horizon: meta.horizon || "",
      first_seen: r.first_seen || null,
      signals_30d: r.signals_30d || 0,
    };
  });
}

export async function getCrossVerticalTrends(options: {
  status?: string;
  limit?: number;
} = {}): Promise<Trend[]> {
  const params: unknown[] = [];
  let query = TREND_SELECT + " WHERE jsonb_array_length(t.verticals) > 1";
  if (options.status) {
    params.push(options.status);
    query += ` AND t.status = $${params.length}`;
  }
  params.push(options.limit ?? 20);
  query += ` ORDER BY t.sort_date DESC NULLS LAST, t.trend_score DESC LIMIT $${params.length}`;
  return (await q(query, params)).map(parseTrendRow);
}

export async function getTopTrendsByEngagement(limit: number = 10): Promise<Trend[]> {
  const rows = await q(
    `SELECT ${TREND_COLS},
        LEAST(re.published_date, NOW())::text as source_date, s.source_type as source_type,
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

function buildOrderBy(sort: TrendsSortBy | undefined): string {
  switch (sort) {
    case "date_asc":
      return `ORDER BY ${CAPPED_DATE} ASC`;
    case "score_desc":
      return `ORDER BY t.trend_score DESC NULLS LAST, ${CAPPED_DATE} DESC`;
    case "engagement_desc":
      return `ORDER BY COALESCE(m.page_views, 0) DESC, ${CAPPED_DATE} DESC`;
    case "source_date_desc":
      return `ORDER BY ${CAPPED_DATE} DESC, t.created_at DESC`;
    case "date_desc":
    default:
      return `ORDER BY ${CAPPED_DATE} DESC`;
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

/** Corpus stats for the methodology / trust page. */
export async function getMethodologyStats(): Promise<{
  analyzed: number;
  published: number;
  sources: number;
  megaTrends: number;
  tierCounts: Record<string, number>;
  dateSpan: { first: string | null; last: string | null };
}> {
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
