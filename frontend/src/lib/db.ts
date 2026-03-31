import Database from "better-sqlite3";
import path from "path";
import type { Trend, Vertical } from "./types";

const DB_PATH = process.env.DATABASE_PATH
  || path.join(process.cwd(), "..", "data", "catandary.db");

function getDb(): Database.Database {
  const db = new Database(DB_PATH, { readonly: true });
  db.pragma("journal_mode = WAL");
  return db;
}

function parseTrendRow(row: Record<string, unknown>): Trend {
  return {
    ...row,
    verticals: JSON.parse((row.verticals as string) || "[]"),
    pestel: JSON.parse((row.pestel as string) || "[]"),
    tags: JSON.parse((row.tags as string) || "[]"),
    brands: JSON.parse((row.brands as string) || "[]"),
    companies: JSON.parse((row.companies as string) || "[]"),
    regions: JSON.parse((row.regions as string) || "[]"),
    auto_published: Boolean(row.auto_published),
  } as Trend;
}

export function getTrends(options: {
  status?: string;
  vertical?: Vertical;
  limit?: number;
  offset?: number;
} = {}): Trend[] {
  const db = getDb();
  try {
    let query = "SELECT * FROM trends WHERE 1=1";
    const params: unknown[] = [];

    if (options.status) {
      query += " AND status = ?";
      params.push(options.status);
    }
    if (options.vertical) {
      query += " AND primary_vertical = ?";
      params.push(options.vertical);
    }

    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?";
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
      .prepare("SELECT * FROM trends WHERE slug = ?")
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
    let query = "SELECT COUNT(*) as cnt FROM trends WHERE 1=1";
    const params: unknown[] = [];

    if (options.status) {
      query += " AND status = ?";
      params.push(options.status);
    }
    if (options.vertical) {
      query += " AND primary_vertical = ?";
      params.push(options.vertical);
    }

    const row = db.prepare(query).get(...params) as { cnt: number };
    return row.cnt;
  } finally {
    db.close();
  }
}

export function getVerticalCounts(status?: string): Record<string, number> {
  const db = getDb();
  try {
    let query = "SELECT primary_vertical, COUNT(*) as cnt FROM trends WHERE 1=1";
    const params: unknown[] = [];

    if (status) {
      query += " AND status = ?";
      params.push(status);
    }

    query += " GROUP BY primary_vertical ORDER BY cnt DESC";

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
