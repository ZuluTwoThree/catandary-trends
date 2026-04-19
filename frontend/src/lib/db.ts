import Database from "better-sqlite3";
import path from "path";
import fs from "fs";
import yaml from "js-yaml";
import type {
  Trend,
  Vertical,
  PestelDimension,
  TrendSignalType,
} from "./types";

const DB_PATH = process.env.DATABASE_PATH
  || path.join(process.cwd(), "..", "data", "catandary.db");

function getDb(): Database.Database {
  const db = new Database(DB_PATH, { readonly: true });
  db.pragma("journal_mode = WAL");
  return db;
}

function parseTrendRow(row: Record<string, unknown>): Trend {
  const { embedding, ...rest } = row;
  return {
    ...rest,
    verticals: JSON.parse((row.verticals as string) || "[]"),
    pestel: JSON.parse((row.pestel as string) || "[]"),
    tags: JSON.parse((row.tags as string) || "[]"),
    brands: JSON.parse((row.brands as string) || "[]"),
    companies: JSON.parse((row.companies as string) || "[]"),
    regions: JSON.parse((row.regions as string) || "[]"),
    auto_published: Boolean(row.auto_published),
    source_date: (row.source_date as string) || null,
    source_type: (row.source_type as string) || null,
  } as Trend;
}

/** SELECT columns for trend queries — joins raw_entries for source_date + source_type, capping future dates to now */
const TREND_SELECT = "SELECT t.*, MIN(re.published_date, datetime('now')) as source_date, s.source_type as source_type FROM trends t LEFT JOIN raw_entries re ON t.raw_entry_id = re.id LEFT JOIN sources s ON re.source_id = s.id";

export function getTrends(options: {
  status?: string;
  vertical?: Vertical;
  limit?: number;
  offset?: number;
} = {}): Trend[] {
  const db = getDb();
  try {
    let query = TREND_SELECT + " WHERE 1=1";
    const params: unknown[] = [];

    if (options.status) {
      query += " AND t.status = ?";
      params.push(options.status);
    }
    if (options.vertical) {
      query += " AND t.primary_vertical = ?";
      params.push(options.vertical);
    }

    query += " ORDER BY MIN(COALESCE(re.published_date, t.created_at), t.created_at) DESC LIMIT ? OFFSET ?";
    params.push(options.limit ?? 50);
    params.push(options.offset ?? 0);

    const rows = db.prepare(query).all(...params) as Record<string, unknown>[];
    return rows.map(parseTrendRow);
  } finally {
    db.close();
  }
}

export function getTrendBySlug(slug: string): Trend | null {
  const db = getDb();
  try {
    const row = db
      .prepare(TREND_SELECT + " WHERE t.slug = ?")
      .get(slug) as Record<string, unknown> | undefined;
    return row ? parseTrendRow(row) : null;
  } finally {
    db.close();
  }
}

export function getTrendsCount(options: {
  status?: string;
  vertical?: Vertical;
} = {}): number {
  const db = getDb();
  try {
    let query = "SELECT COUNT(*) as cnt FROM trends t WHERE 1=1";
    const params: unknown[] = [];

    if (options.status) {
      query += " AND t.status = ?";
      params.push(options.status);
    }
    if (options.vertical) {
      query += " AND t.primary_vertical = ?";
      params.push(options.vertical);
    }

    const row = db.prepare(query).get(...params) as { cnt: number };
    return row.cnt;
  } finally {
    db.close();
  }
}

export function getTrendsByMegaTrend(megaTrend: string, options: {
  status?: string;
  limit?: number;
} = {}): Trend[] {
  const db = getDb();
  try {
    let query = TREND_SELECT + " WHERE t.mega_trend = ?";
    const params: unknown[] = [megaTrend];

    if (options.status) {
      query += " AND t.status = ?";
      params.push(options.status);
    }

    query += " ORDER BY MIN(COALESCE(re.published_date, t.created_at), t.created_at) DESC LIMIT ?";
    params.push(options.limit ?? 50);

    const rows = db.prepare(query).all(...params) as Record<string, unknown>[];
    return rows.map(parseTrendRow);
  } finally {
    db.close();
  }
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

export function getMegaTrends(status?: string): MegaTrendInfo[] {
  const db = getDb();
  try {
    let query = `SELECT t.mega_trend, COUNT(*) as cnt,
       GROUP_CONCAT(DISTINCT t.primary_vertical) as verts,
       MIN(re.published_date) as first_seen,
       SUM(CASE WHEN re.published_date >= datetime('now', '-30 days') THEN 1 ELSE 0 END) as signals_30d
       FROM trends t
       LEFT JOIN raw_entries re ON t.raw_entry_id = re.id
       WHERE t.mega_trend IS NOT NULL AND t.mega_trend != ''`;
    const params: unknown[] = [];

    if (status) {
      query += " AND t.status = ?";
      params.push(status);
    }

    query += " GROUP BY t.mega_trend ORDER BY cnt DESC";

    const rows = db.prepare(query).all(...params) as {
      mega_trend: string;
      cnt: number;
      verts: string;
      first_seen: string | null;
      signals_30d: number;
    }[];

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
  } finally {
    db.close();
  }
}

export function getCrossVerticalTrends(options: {
  status?: string;
  limit?: number;
} = {}): Trend[] {
  const db = getDb();
  try {
    let query = TREND_SELECT + " WHERE json_array_length(t.verticals) > 1";
    const params: unknown[] = [];

    if (options.status) {
      query += " AND t.status = ?";
      params.push(options.status);
    }

    query += " ORDER BY t.trend_score DESC, COALESCE(re.published_date, t.created_at) DESC LIMIT ?";
    params.push(options.limit ?? 20);

    const rows = db.prepare(query).all(...params) as Record<string, unknown>[];
    return rows.map(parseTrendRow);
  } finally {
    db.close();
  }
}

export function getTopTrendsByEngagement(limit: number = 10): Trend[] {
  const db = getDb();
  try {
    const rows = db
      .prepare(
        `SELECT t.*, MIN(re.published_date, datetime('now')) as source_date, s.source_type as source_type, COALESCE(m.page_views, 0) as views
         FROM trends t
         LEFT JOIN raw_entries re ON t.raw_entry_id = re.id
         LEFT JOIN sources s ON re.source_id = s.id
         LEFT JOIN trend_metrics m ON t.id = m.trend_id
         WHERE t.status = 'published'
         ORDER BY views DESC, t.trend_score DESC
         LIMIT ?`
      )
      .all(limit) as Record<string, unknown>[];
    return rows.map(parseTrendRow);
  } finally {
    db.close();
  }
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

function buildFilterClauses(options: TrendsFilterOptions): {
  where: string;
  params: unknown[];
  extraJoins: string;
  needsFts: boolean;
  needsMetrics: boolean;
} {
  const where: string[] = ["1=1"];
  const params: unknown[] = [];
  let extraJoins = "";
  let needsFts = false;
  let needsMetrics = false;

  // Status default = published
  const status = options.status ?? "published";
  if (status !== "all") {
    where.push("t.status = ?");
    params.push(status);
  }

  if (options.verticals && options.verticals.length > 0) {
    const ph = options.verticals.map(() => "?").join(",");
    where.push(`t.primary_vertical IN (${ph})`);
    params.push(...options.verticals);
  }

  if (options.pestel && options.pestel.length > 0) {
    const ph = options.pestel.map(() => "?").join(",");
    where.push(
      `EXISTS (SELECT 1 FROM json_each(t.pestel) WHERE json_each.value IN (${ph}))`
    );
    params.push(...options.pestel);
  }

  if (options.signal_types && options.signal_types.length > 0) {
    const ph = options.signal_types.map(() => "?").join(",");
    where.push(`t.trend_signal_type IN (${ph})`);
    params.push(...options.signal_types);
  }

  if (options.mega_trend) {
    where.push("t.mega_trend = ?");
    params.push(options.mega_trend);
  }

  if (options.exclude_sources && options.exclude_sources.length > 0) {
    const ph = options.exclude_sources.map(() => "?").join(",");
    where.push(`COALESCE(t.source_name, '') NOT IN (${ph})`);
    params.push(...options.exclude_sources);
  }

  if (options.min_trend_score !== undefined && options.min_trend_score > 0) {
    // UI passes 0–100, DB stores 0–1
    where.push("COALESCE(t.trend_score, 0) >= ?");
    params.push(options.min_trend_score / 100);
  }

  if (options.date_range && options.date_range !== "all") {
    const modifier =
      options.date_range === "1d"
        ? "-1 day"
        : options.date_range === "7d"
          ? "-7 days"
          : "-30 days";
    where.push(
      "datetime(COALESCE(re.published_date, t.created_at)) >= datetime('now', ?)"
    );
    params.push(modifier);
  }

  const search = options.search?.trim();
  if (search && search.length > 0) {
    needsFts = true;
    // Sanitise: escape double-quotes and wrap each whitespace-separated token
    // in quotes to use FTS5 prefix-friendly phrase matching.
    const tokens = search
      .split(/\s+/)
      .filter(Boolean)
      .map((t) => `"${t.replace(/"/g, '""')}"*`)
      .join(" AND ");
    extraJoins += " JOIN trends_fts fts ON fts.rowid = t.id";
    where.push("trends_fts MATCH ?");
    params.push(tokens);
  }

  if (options.sort_by === "engagement_desc") {
    needsMetrics = true;
    extraJoins += " LEFT JOIN trend_metrics m ON m.trend_id = t.id";
  }

  return {
    where: where.join(" AND "),
    params,
    extraJoins,
    needsFts,
    needsMetrics,
  };
}

/** Capped date expression — caps future source dates to created_at so they
 *  sort by ingestion time, not by a bogus future RSS date. */
const CAPPED_DATE = "MIN(COALESCE(re.published_date, t.created_at), t.created_at)";

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

export function getTrendsFiltered(options: TrendsFilterOptions = {}): Trend[] {
  const db = getDb();
  try {
    const { where, params, extraJoins } = buildFilterClauses(options);

    const query =
      TREND_SELECT +
      extraJoins +
      ` WHERE ${where} ` +
      buildOrderBy(options.sort_by) +
      " LIMIT ? OFFSET ?";

    const rows = db
      .prepare(query)
      .all(...params, options.limit ?? 12, options.offset ?? 0) as Record<
      string,
      unknown
    >[];
    return rows.map(parseTrendRow);
  } finally {
    db.close();
  }
}

export function getTrendsFilteredCount(
  options: TrendsFilterOptions = {}
): number {
  const db = getDb();
  try {
    const { where, params, extraJoins } = buildFilterClauses(options);

    // Always include the raw_entries join because filters reference re.published_date.
    const query =
      `SELECT COUNT(*) as cnt FROM trends t LEFT JOIN raw_entries re ON t.raw_entry_id = re.id` +
      extraJoins +
      ` WHERE ${where}`;

    const row = db.prepare(query).get(...params) as { cnt: number };
    return row.cnt;
  } finally {
    db.close();
  }
}

export function getTopSourcesByCount(
  limit: number = 20,
  status: string = "published"
): Array<{ source_name: string; count: number }> {
  const db = getDb();
  try {
    const rows = db
      .prepare(
        `SELECT source_name, COUNT(*) as cnt
         FROM trends
         WHERE source_name IS NOT NULL AND source_name != ''
           AND (? = 'all' OR status = ?)
         GROUP BY source_name
         ORDER BY cnt DESC
         LIMIT ?`
      )
      .all(status, status, limit) as Array<{ source_name: string; cnt: number }>;
    return rows.map((r) => ({ source_name: r.source_name, count: r.cnt }));
  } finally {
    db.close();
  }
}

/**
 * Vertical counts scoped to the *current filter set minus the vertical filter*.
 * Powers the multi-select vertical chips so toggling never collapses the UI
 * to zero for other verticals.
 */
export function getVerticalCountsScoped(
  options: TrendsFilterOptions = {}
): Record<string, number> {
  const db = getDb();
  try {
    // Strip verticals from the filter to get the "all other filters" scope
    const scoped: TrendsFilterOptions = { ...options, verticals: undefined };
    const { where, params, extraJoins } = buildFilterClauses(scoped);

    const query =
      `SELECT t.primary_vertical, COUNT(*) as cnt
       FROM trends t LEFT JOIN raw_entries re ON t.raw_entry_id = re.id` +
      extraJoins +
      ` WHERE ${where}
       GROUP BY t.primary_vertical
       ORDER BY cnt DESC`;

    const rows = db.prepare(query).all(...params) as {
      primary_vertical: string;
      cnt: number;
    }[];

    const result: Record<string, number> = {};
    for (const row of rows) {
      if (row.primary_vertical) {
        result[row.primary_vertical] = row.cnt;
      }
    }
    return result;
  } finally {
    db.close();
  }
}

export function getVerticalCounts(status?: string): Record<string, number> {
  const db = getDb();
  try {
    let query = "SELECT primary_vertical, COUNT(*) as cnt FROM trends t WHERE 1=1";
    const params: unknown[] = [];

    if (status) {
      query += " AND t.status = ?";
      params.push(status);
    }

    query += " GROUP BY t.primary_vertical ORDER BY cnt DESC";

    const rows = db.prepare(query).all(...params) as {
      primary_vertical: string;
      cnt: number;
    }[];

    const result: Record<string, number> = {};
    for (const row of rows) {
      if (row.primary_vertical) {
        result[row.primary_vertical] = row.cnt;
      }
    }
    return result;
  } finally {
    db.close();
  }
}
