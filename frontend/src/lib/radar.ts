import Database from "better-sqlite3";
import path from "path";
import type { Trend } from "./types";

const DB_PATH = process.env.DATABASE_PATH
  || path.join(process.cwd(), "..", "data", "catandary.db");

function getDb(): Database.Database {
  const db = new Database(DB_PATH, { readonly: true });
  db.pragma("journal_mode = WAL");
  return db;
}

export interface RadarCustomer {
  id: number;
  name: string;
  contact_name: string | null;
  email: string;
  tier: "trial" | "solo" | "pro" | "agency";
  parent_id: number | null;
  token: string;
  verticals: string[];
  keywords: string[];
  language: "de" | "en";
  brand_name: string | null;
  brand_color: string | null;
  brand_logo_url: string | null;
  status: "active" | "paused" | "cancelled";
  trial_ends_at: string | null;
}

export interface BriefingSummary {
  id: number;
  week_label: string;
  subject: string | null;
  trend_count: number;
  watchlist_hit_count: number;
  sent_at: string | null;
  created_at: string;
}

function tableExists(db: Database.Database, name: string): boolean {
  return !!db
    .prepare("SELECT name FROM sqlite_master WHERE type='table' AND name=?")
    .get(name);
}

export function getCustomerByToken(token: string): RadarCustomer | null {
  const db = getDb();
  try {
    if (!tableExists(db, "radar_customers")) return null;
    const row = db
      .prepare("SELECT * FROM radar_customers WHERE token = ?")
      .get(token) as Record<string, unknown> | undefined;
    if (!row) return null;
    return {
      ...row,
      verticals: JSON.parse((row.verticals as string) || "[]"),
      keywords: JSON.parse((row.keywords as string) || "[]"),
    } as RadarCustomer;
  } finally {
    db.close();
  }
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

const TREND_SELECT =
  "SELECT t.*, MIN(re.published_date, datetime('now')) as source_date, s.source_type as source_type " +
  "FROM trends t LEFT JOIN raw_entries re ON t.raw_entry_id = re.id " +
  "LEFT JOIN sources s ON re.source_id = s.id";

/** Anchor the signal window on the newest published trend so the portal
 *  stays meaningful even when the pipeline pauses for a few days. */
function getAnchorDate(db: Database.Database): string {
  const row = db
    .prepare(
      "SELECT MAX(COALESCE(published_at, created_at)) as latest FROM trends WHERE status = 'published'"
    )
    .get() as { latest: string | null };
  return row.latest || new Date().toISOString();
}

export function getRadarFeed(
  customer: RadarCustomer,
  options: { windowDays?: number; limit?: number } = {}
): { topTrends: Trend[]; watchlistHits: Record<string, Trend[]>; windowStart: string } {
  const db = getDb();
  try {
    const windowDays = options.windowDays ?? 30;
    const limit = options.limit ?? 24;
    const anchor = getAnchorDate(db);
    const windowStart = new Date(
      new Date(anchor.replace(" ", "T")).getTime() - windowDays * 86400_000
    ).toISOString().slice(0, 10);

    // Watchlist first — FTS5 per keyword, top 3 each
    const watchlistHits: Record<string, Trend[]> = {};
    const seenIds = new Set<number>();
    if (customer.keywords.length && tableExists(db, "trends_fts")) {
      const stmt = db.prepare(
        `SELECT t.*, MIN(re.published_date, datetime('now')) as source_date, s.source_type as source_type
         FROM trends_fts f
         JOIN trends t ON t.id = f.rowid
         LEFT JOIN raw_entries re ON t.raw_entry_id = re.id
         LEFT JOIN sources s ON re.source_id = s.id
         WHERE trends_fts MATCH ? AND t.status = 'published'
           AND COALESCE(t.published_at, t.created_at) >= ?
         ORDER BY t.trend_score DESC LIMIT 3`
      );
      for (const kw of customer.keywords) {
        const ftsQuery = kw
          .split(/\s+/)
          .map((tok) => `"${tok.replace(/"/g, "")}"`)
          .join(" ");
        try {
          const rows = stmt.all(ftsQuery, windowStart) as Record<string, unknown>[];
          if (rows.length) {
            watchlistHits[kw] = rows.map(parseTrendRow);
            rows.forEach((r) => seenIds.add(r.id as number));
          }
        } catch {
          // malformed keyword for FTS — skip silently
        }
      }
    }

    // Top trends for the customer's verticals, excluding watchlist hits
    const placeholders = customer.verticals.map(() => "?").join(",");
    const jsonClauses = customer.verticals.map(() => "t.verticals LIKE ?").join(" OR ");
    const params: unknown[] = [
      ...customer.verticals,
      ...customer.verticals.map((v) => `%"${v}"%`),
      windowStart,
    ];
    let excludeSql = "";
    if (seenIds.size) {
      excludeSql = ` AND t.id NOT IN (${[...seenIds].map(() => "?").join(",")})`;
      params.push(...seenIds);
    }
    params.push(limit);
    const rows = db
      .prepare(
        `${TREND_SELECT}
         WHERE t.status = 'published'
           AND (t.primary_vertical IN (${placeholders}) OR ${jsonClauses})
           AND COALESCE(t.published_at, t.created_at) >= ?
           ${excludeSql}
         ORDER BY t.trend_score DESC, COALESCE(t.published_at, t.created_at) DESC
         LIMIT ?`
      )
      .all(...params) as Record<string, unknown>[];

    return { topTrends: rows.map(parseTrendRow), watchlistHits, windowStart };
  } finally {
    db.close();
  }
}

export function getBriefingsForCustomer(customerId: number): BriefingSummary[] {
  const db = getDb();
  try {
    if (!tableExists(db, "radar_briefings")) return [];
    const rows = db
      .prepare(
        `SELECT id, week_label, subject, trend_ids, watchlist_hits, sent_at, created_at
         FROM radar_briefings WHERE customer_id = ? ORDER BY week_label DESC LIMIT 26`
      )
      .all(customerId) as Record<string, unknown>[];
    return rows.map((r) => {
      const hits = JSON.parse((r.watchlist_hits as string) || "{}") as Record<string, number[]>;
      return {
        id: r.id as number,
        week_label: r.week_label as string,
        subject: (r.subject as string) || null,
        trend_count: (JSON.parse((r.trend_ids as string) || "[]") as number[]).length,
        watchlist_hit_count: Object.values(hits).reduce((acc, ids) => acc + ids.length, 0),
        sent_at: (r.sent_at as string) || null,
        created_at: r.created_at as string,
      };
    });
  } finally {
    db.close();
  }
}

export function getBriefingHtml(customerId: number, briefingId: number): string | null {
  const db = getDb();
  try {
    if (!tableExists(db, "radar_briefings")) return null;
    const row = db
      .prepare("SELECT html FROM radar_briefings WHERE id = ? AND customer_id = ?")
      .get(briefingId, customerId) as { html: string } | undefined;
    return row?.html ?? null;
  } finally {
    db.close();
  }
}
