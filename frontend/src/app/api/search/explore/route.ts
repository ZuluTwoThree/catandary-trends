/**
 * Foresight Cockpit — Explore API (landing page data)
 *
 * Returns trending tags, mega-trend momentum, and vertical activity
 * from the last 14 days. No search query needed.
 *
 * GET /api/search/explore
 */
import { NextResponse } from "next/server";
import Database from "better-sqlite3";
import path from "path";

const DB_PATH =
  process.env.DATABASE_PATH ||
  path.join(process.cwd(), "..", "data", "catandary.db");

const LOOKBACK_DAYS = 14;

export async function GET() {
  const t0 = Date.now();
  const db = new Database(DB_PATH, { readonly: true });
  db.pragma("journal_mode = WAL");

  const cutoff = new Date(Date.now() - LOOKBACK_DAYS * 86400000)
    .toISOString()
    .slice(0, 10);

  // Signal-type tags to exclude
  const SIGNAL_TYPE_TAGS = new Set([
    "product_launch", "research", "market_shift", "consumer_behavior",
    "regulation", "funding", "partnership", "patent",
  ]);

  // -----------------------------------------------------------------------
  // 1. Trending tags (TF-IDF: recent vs corpus)
  // -----------------------------------------------------------------------
  const recentTags = db
    .prepare(
      `SELECT tags FROM trends
       WHERE status = 'published' AND published_at >= ?`
    )
    .all(cutoff) as Array<{ tags: string }>;

  const totalDocs = (
    db.prepare("SELECT COUNT(*) as c FROM trends WHERE status = 'published'").get() as { c: number }
  ).c;

  const tagTf: Record<string, number> = {};
  for (const row of recentTags) {
    try {
      const tags = JSON.parse(row.tags || "[]") as string[];
      for (const rawTag of tags) {
        const tag = rawTag.replace(/_/g, " ").toLowerCase().trim();
        if (!tag || SIGNAL_TYPE_TAGS.has(rawTag)) continue;
        tagTf[tag] = (tagTf[tag] || 0) + 1;
      }
    } catch { /* skip */ }
  }

  const topTfTags = Object.entries(tagTf)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 40);

  const trendingTags: Array<{ tag: string; count: number; tfidf: number }> = [];
  for (const [tag, tf] of topTfTags) {
    if (tf < 2) continue;
    const dfRow = db
      .prepare(
        `SELECT COUNT(*) as c FROM trends
         WHERE status = 'published' AND tags LIKE ?`
      )
      .get(`%"${tag}"%`) as { c: number };

    // Also check underscore variant for DF lookup
    const tagUnderscore = tag.replace(/ /g, "_");
    const dfRow2 = tag !== tagUnderscore
      ? (db
          .prepare(
            `SELECT COUNT(*) as c FROM trends
             WHERE status = 'published' AND tags LIKE ?`
          )
          .get(`%"${tagUnderscore}"%`) as { c: number })
      : { c: 0 };

    const df = (dfRow.c + dfRow2.c) || 1;
    const idf = Math.log(totalDocs / df);
    const tfidf = Math.round(tf * idf * 100) / 100;
    trendingTags.push({ tag, count: tf, tfidf });
  }
  trendingTags.sort((a, b) => b.tfidf - a.tfidf);

  // -----------------------------------------------------------------------
  // 2. Mega-trend momentum (recent count vs average)
  // -----------------------------------------------------------------------
  const megaMomentum = db
    .prepare(
      `SELECT
         mega_trend,
         SUM(CASE WHEN published_at >= ? THEN 1 ELSE 0 END) as recent,
         COUNT(*) as total
       FROM trends
       WHERE status = 'published' AND mega_trend IS NOT NULL
       GROUP BY mega_trend
       HAVING recent > 0
       ORDER BY recent DESC
       LIMIT 10`
    )
    .all(cutoff) as Array<{ mega_trend: string; recent: number; total: number }>;

  // -----------------------------------------------------------------------
  // 3. Vertical activity (recent signal counts)
  // -----------------------------------------------------------------------
  const verticalActivity = db
    .prepare(
      `SELECT primary_vertical, COUNT(*) as count
       FROM trends
       WHERE status = 'published' AND published_at >= ?
       GROUP BY primary_vertical
       ORDER BY count DESC`
    )
    .all(cutoff) as Array<{ primary_vertical: string; count: number }>;

  // -----------------------------------------------------------------------
  // 4. Total recent signals
  // -----------------------------------------------------------------------
  const recentTotal = (
    db
      .prepare(
        `SELECT COUNT(*) as c FROM trends
         WHERE status = 'published' AND published_at >= ?`
      )
      .get(cutoff) as { c: number }
  ).c;

  db.close();

  return NextResponse.json({
    lookback_days: LOOKBACK_DAYS,
    recent_total: recentTotal,
    took_ms: Date.now() - t0,
    trending_tags: trendingTags.slice(0, 20),
    mega_momentum: megaMomentum,
    vertical_activity: verticalActivity,
  });
}
