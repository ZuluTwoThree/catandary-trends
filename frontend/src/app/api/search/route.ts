/**
 * Foresight Cockpit — Hybrid Search API
 *
 * Combines FTS5 lexical search + qwen3-embedding semantic search via
 * Reciprocal Rank Fusion (RRF). Returns results + analytics for the
 * Foresight Cockpit dashboard.
 *
 * GET /api/search?q=...&vertical=FOOD&limit=20
 *
 * Response shape:
 *   { query, vertical, results[], analytics: { timeline, lead_time, pestel, mega_trends, co_occurrence, verticals }, meta }
 */
import { NextResponse } from "next/server";
import Database from "better-sqlite3";
import path from "path";

const DB_PATH =
  process.env.DATABASE_PATH ||
  path.join(process.cwd(), "..", "data", "catandary.db");

const OLLAMA_URL =
  process.env.OLLAMA_CLIENT_HOST || "http://127.0.0.1:11434";
const EMBED_MODEL = "qwen3-embedding";
const EMBED_DIM = 4096;

const RRF_K = 60; // RRF smoothing constant
const ANALYTICS_MIN_N = 30; // minimum hits for analytics overlays

// ---------------------------------------------------------------------------
// Embedding cache (module-scoped, loaded once per process)
// ---------------------------------------------------------------------------
type TrendVec = {
  id: number;
  primary_vertical: string;
  embedding: Float32Array;
  norm: number;
};
let vecCache: TrendVec[] | null = null;

function loadEmbeddings(): TrendVec[] {
  if (vecCache) return vecCache;
  const db = new Database(DB_PATH, { readonly: true });
  db.pragma("journal_mode = WAL");
  const rows = db
    .prepare(
      `SELECT id, primary_vertical, embedding
       FROM trends
       WHERE status = 'published' AND embedding IS NOT NULL`
    )
    .all() as Array<{
    id: number;
    primary_vertical: string;
    embedding: Buffer;
  }>;
  db.close();

  const out: TrendVec[] = [];
  for (const r of rows) {
    if (r.embedding.length !== EMBED_DIM * 4) continue;
    const vec = new Float32Array(
      r.embedding.buffer,
      r.embedding.byteOffset,
      EMBED_DIM
    ).slice();
    let sum = 0;
    for (let i = 0; i < EMBED_DIM; i++) sum += vec[i] * vec[i];
    out.push({
      id: r.id,
      primary_vertical: r.primary_vertical,
      embedding: vec,
      norm: Math.sqrt(sum) || 1,
    });
  }
  vecCache = out;
  return out;
}

// ---------------------------------------------------------------------------
// Ollama embedding
// ---------------------------------------------------------------------------
async function embedQuery(q: string): Promise<Float32Array | null> {
  try {
    const resp = await fetch(`${OLLAMA_URL}/api/embed`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model: EMBED_MODEL, input: q }),
    });
    if (!resp.ok) return null;
    const data = (await resp.json()) as { embeddings?: number[][] };
    const vec = data.embeddings?.[0];
    if (!vec || vec.length !== EMBED_DIM) return null;
    return Float32Array.from(vec);
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Cosine similarity
// ---------------------------------------------------------------------------
function cosine(q: Float32Array, qNorm: number, t: TrendVec): number {
  let dot = 0;
  const v = t.embedding;
  for (let i = 0; i < EMBED_DIM; i++) dot += q[i] * v[i];
  return dot / (qNorm * t.norm);
}

// ---------------------------------------------------------------------------
// FTS5 search
// ---------------------------------------------------------------------------
function escapeFts5(query: string): string {
  const words = query
    .replace(/['"]/g, "")
    .split(/\s+/)
    .filter(Boolean);
  if (words.length === 0) return "";
  // Single word: simple match. Multi-word: AND (all words must appear)
  return words.map((w) => `"${w}"`).join(" AND ");
}

/** Top-K FTS5 results for RRF display */
function fts5Search(
  db: Database.Database,
  query: string,
  vertical: string | null,
  maxResults: number
): Array<{ id: number; rank: number }> {
  const escaped = escapeFts5(query);
  if (!escaped) return [];

  const sql = vertical
    ? `SELECT f.rowid as id, rank
       FROM trends_fts f
       JOIN trends t ON t.id = f.rowid
       WHERE trends_fts MATCH ?
         AND t.status = 'published'
         AND t.primary_vertical = ?
       ORDER BY rank
       LIMIT ?`
    : `SELECT f.rowid as id, rank
       FROM trends_fts f
       JOIN trends t ON t.id = f.rowid
       WHERE trends_fts MATCH ?
         AND t.status = 'published'
       ORDER BY rank
       LIMIT ?`;

  const params = vertical
    ? [escaped, vertical, maxResults * 3]
    : [escaped, maxResults * 3];

  try {
    return db.prepare(sql).all(...params) as Array<{
      id: number;
      rank: number;
    }>;
  } catch {
    return [];
  }
}

/** ALL FTS5 matching IDs (no limit) for analytics */
function fts5AllIds(
  db: Database.Database,
  query: string,
  vertical: string | null,
): number[] {
  const escaped = escapeFts5(query);
  if (!escaped) return [];

  const sql = vertical
    ? `SELECT f.rowid as id FROM trends_fts f
       JOIN trends t ON t.id = f.rowid
       WHERE trends_fts MATCH ? AND t.status = 'published' AND t.primary_vertical = ?`
    : `SELECT f.rowid as id FROM trends_fts f
       JOIN trends t ON t.id = f.rowid
       WHERE trends_fts MATCH ? AND t.status = 'published'`;

  const params = vertical ? [escaped, vertical] : [escaped];

  try {
    return (db.prepare(sql).all(...params) as Array<{ id: number }>).map((r) => r.id);
  } catch {
    return [];
  }
}

// ---------------------------------------------------------------------------
// Reciprocal Rank Fusion
// ---------------------------------------------------------------------------
function rrfMerge(
  ftsResults: Array<{ id: number }>,
  embResults: Array<{ id: number; score: number }>,
  limit: number
): Array<{ id: number; rrf_score: number; fts_rank: number | null; emb_score: number | null }> {
  const scores = new Map<
    number,
    { rrf: number; fts_rank: number | null; emb_score: number | null }
  >();

  // FTS5 contribution
  ftsResults.forEach((r, i) => {
    const rank = i + 1;
    const existing = scores.get(r.id) || {
      rrf: 0,
      fts_rank: null,
      emb_score: null,
    };
    existing.rrf += 1 / (RRF_K + rank);
    existing.fts_rank = rank;
    scores.set(r.id, existing);
  });

  // Embedding contribution
  embResults.forEach((r, i) => {
    const rank = i + 1;
    const existing = scores.get(r.id) || {
      rrf: 0,
      fts_rank: null,
      emb_score: null,
    };
    existing.rrf += 1 / (RRF_K + rank);
    existing.emb_score = r.score;
    scores.set(r.id, existing);
  });

  return [...scores.entries()]
    .map(([id, s]) => ({
      id,
      rrf_score: Math.round(s.rrf * 10000) / 10000,
      fts_rank: s.fts_rank,
      emb_score: s.emb_score ? Math.round(s.emb_score * 1000) / 1000 : null,
    }))
    .sort((a, b) => b.rrf_score - a.rrf_score)
    .slice(0, limit);
}

// ---------------------------------------------------------------------------
// Analytics computation (runs on the full match set, not just top-K)
// ---------------------------------------------------------------------------
interface AnalyticsInput {
  ids: number[];
  db: Database.Database;
}

function computeAnalytics(input: AnalyticsInput) {
  const { ids, db } = input;
  const n = ids.length;
  const hasEnough = n >= ANALYTICS_MIN_N;

  if (!hasEnough) {
    return {
      total_matches: n,
      has_enough_data: false,
      timeline: [],
      lead_time: {},
      pestel: {},
      mega_trends: [],
      co_occurrence: [],
      verticals: {},
    };
  }

  const placeholders = ids.map(() => "?").join(",");

  // Timeline: monthly histogram
  const timeline = db
    .prepare(
      `SELECT strftime('%Y-%m', COALESCE(r.published_date, t.created_at)) as month,
              COUNT(*) as count
       FROM trends t
       LEFT JOIN raw_entries r ON t.raw_entry_id = r.id
       WHERE t.id IN (${placeholders})
       GROUP BY month
       ORDER BY month`
    )
    .all(...ids) as Array<{ month: string; count: number }>;

  // Lead-time tier breakdown
  const leadTime = db
    .prepare(
      `SELECT COALESCE(lt.lead_time_tier, 'unknown') as tier, COUNT(*) as count
       FROM trends t
       LEFT JOIN source_lead_time_tier lt ON t.source_name = lt.source_name
       WHERE t.id IN (${placeholders})
       GROUP BY tier
       ORDER BY count DESC`
    )
    .all(...ids) as Array<{ tier: string; count: number }>;

  // PESTEL distribution
  const pestelRaw = db
    .prepare(
      `SELECT pestel FROM trends WHERE id IN (${placeholders})`
    )
    .all(...ids) as Array<{ pestel: string }>;

  const pestelCounts: Record<string, number> = {};
  for (const row of pestelRaw) {
    try {
      const dims = JSON.parse(row.pestel || "[]") as string[];
      for (const d of dims) {
        pestelCounts[d] = (pestelCounts[d] || 0) + 1;
      }
    } catch { /* skip */ }
  }

  // Mega-trend distribution
  const megaTrends = db
    .prepare(
      `SELECT mega_trend, COUNT(*) as count
       FROM trends
       WHERE id IN (${placeholders}) AND mega_trend IS NOT NULL
       GROUP BY mega_trend
       ORDER BY count DESC
       LIMIT 15`
    )
    .all(...ids) as Array<{ mega_trend: string; count: number }>;

  // Cross-vertical distribution
  const verticals = db
    .prepare(
      `SELECT primary_vertical, COUNT(*) as count
       FROM trends
       WHERE id IN (${placeholders})
       GROUP BY primary_vertical
       ORDER BY count DESC`
    )
    .all(...ids) as Array<{ primary_vertical: string; count: number }>;

  // Co-occurrence: TF-IDF weighted tags
  // Step 1: tag counts within result set (TF)
  const tagsRaw = db
    .prepare(
      `SELECT tags FROM trends WHERE id IN (${placeholders})`
    )
    .all(...ids) as Array<{ tags: string }>;

  const tagTf: Record<string, number> = {};
  // Signal-type tags to exclude from co-occurrence
  const SIGNAL_TYPE_TAGS = new Set([
    "product_launch", "research", "market_shift", "consumer_behavior",
    "regulation", "funding", "partnership", "patent",
  ]);

  for (const row of tagsRaw) {
    try {
      const tags = JSON.parse(row.tags || "[]") as string[];
      for (const rawTag of tags) {
        // Normalize: underscores → spaces, lowercase, trim
        const tag = rawTag.replace(/_/g, " ").toLowerCase().trim();
        if (!tag || SIGNAL_TYPE_TAGS.has(rawTag)) continue;
        tagTf[tag] = (tagTf[tag] || 0) + 1;
      }
    } catch { /* skip */ }
  }

  // Step 2: corpus-wide document frequency (DF) for top TF tags
  const topTfTags = Object.entries(tagTf)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 50);

  const coOccurrence: Array<{ tag: string; count: number; tfidf: number }> = [];
  const totalDocs = db
    .prepare("SELECT COUNT(*) as c FROM trends WHERE status = 'published'")
    .get() as { c: number };

  for (const [tag, tf] of topTfTags) {
    if (tf < 2) continue; // skip singletons in result set
    // Count how many published trends contain this tag
    const dfRow = db
      .prepare(
        `SELECT COUNT(*) as c FROM trends
         WHERE status = 'published' AND tags LIKE ?`
      )
      .get(`%"${tag}"%`) as { c: number };

    const df = dfRow.c || 1;
    const idf = Math.log(totalDocs.c / df);
    const tfidf = Math.round((tf * idf) * 100) / 100;

    coOccurrence.push({ tag, count: tf, tfidf });
  }
  coOccurrence.sort((a, b) => b.tfidf - a.tfidf);

  return {
    total_matches: n,
    has_enough_data: hasEnough,
    timeline,
    lead_time: Object.fromEntries(leadTime.map((r) => [r.tier, r.count])),
    pestel: pestelCounts,
    mega_trends: megaTrends,
    co_occurrence: coOccurrence.slice(0, 20),
    verticals: Object.fromEntries(verticals.map((r) => [r.primary_vertical, r.count])),
  };
}

// ---------------------------------------------------------------------------
// Main handler
// ---------------------------------------------------------------------------
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const q = (searchParams.get("q") || "").trim();
  const vertical = searchParams.get("vertical")?.toUpperCase() || null;
  const limit = Math.min(parseInt(searchParams.get("limit") || "20", 10), 100);
  const threshold = parseFloat(searchParams.get("threshold") || "0.15");

  if (!q) {
    return NextResponse.json(
      { error: "q parameter required" },
      { status: 400 }
    );
  }

  const t0 = Date.now();

  // 1. Embed query
  const qVec = await embedQuery(q);

  // 2. FTS5 search
  const db = new Database(DB_PATH, { readonly: true });
  db.pragma("journal_mode = WAL");

  const ftsResults = fts5Search(db, q, vertical, limit);

  // 3. Embedding search (if Ollama available)
  let embResults: Array<{ id: number; score: number }> = [];
  if (qVec) {
    let qNorm = 0;
    for (let i = 0; i < EMBED_DIM; i++) qNorm += qVec[i] * qVec[i];
    qNorm = Math.sqrt(qNorm) || 1;

    const trends = loadEmbeddings();
    const pool = vertical
      ? trends.filter((t) => t.primary_vertical === vertical)
      : trends;

    const scored: Array<{ id: number; score: number }> = [];
    for (const t of pool) {
      const s = cosine(qVec, qNorm, t);
      if (s >= threshold) scored.push({ id: t.id, score: s });
    }
    scored.sort((a, b) => b.score - a.score);
    embResults = scored.slice(0, limit * 3);
  }

  // 4. Determine if this is a low-confidence embedding-only query
  //    (no FTS hits = query term doesn't appear literally in any trend)
  const ftsHasHits = ftsResults.length > 0;
  const embeddingOnly = !ftsHasHits && embResults.length > 0;

  // For embedding-only results, apply a stricter threshold to suppress noise.
  // qwen3-embedding yields ~0.45-0.55 cosine even for gibberish queries,
  // so we need a high threshold to avoid false positives.
  if (embeddingOnly) {
    const strictThreshold = 0.60;
    embResults = embResults.filter((r) => r.score >= strictThreshold);
  }

  // 4. RRF merge
  const merged = rrfMerge(ftsResults, embResults, limit);

  // 5. Collect ALL matching IDs for analytics (full FTS set + embedding hits)
  const ftsAllMatchIds = fts5AllIds(db, q, vertical);
  const allMatchIds = new Set(ftsAllMatchIds);
  for (const r of embResults) allMatchIds.add(r.id);
  const allIds = [...allMatchIds];

  // 6. Analytics
  const analytics = computeAnalytics({ ids: allIds, db });

  // 7. Hydrate top results
  const topIds = merged.map((m) => m.id);
  const placeholders = topIds.map(() => "?").join(",");
  const hydrated = topIds.length
    ? (db
        .prepare(
          `SELECT t.id, t.slug, t.title_en, t.summary_en,
                  t.primary_vertical, t.source_name, t.mega_trend, t.pestel, t.tags,
                  t.trend_signal_type, t.published_at, t.created_at,
                  COALESCE(lt.lead_time_tier, 'unknown') as lead_time_tier,
                  MIN(r.published_date, datetime('now')) as source_date
           FROM trends t
           LEFT JOIN raw_entries r ON t.raw_entry_id = r.id
           LEFT JOIN source_lead_time_tier lt ON t.source_name = lt.source_name
           WHERE t.id IN (${placeholders})`
        )
        .all(...topIds) as Array<Record<string, unknown>>)
    : [];
  db.close();

  const byId = new Map(hydrated.map((h) => [h.id as number, h]));
  const results = merged
    .map((m) => {
      const h = byId.get(m.id);
      if (!h) return null;
      return {
        ...h,
        pestel: JSON.parse((h.pestel as string) || "[]"),
        tags: JSON.parse((h.tags as string) || "[]"),
        rrf_score: m.rrf_score,
        fts_rank: m.fts_rank,
        emb_score: m.emb_score,
      };
    })
    .filter(Boolean);

  return NextResponse.json({
    query: q,
    vertical,
    limit,
    took_ms: Date.now() - t0,
    meta: {
      fts_hits: ftsResults.length,
      emb_hits: embResults.length,
      total_unique: allIds.length,
      embedding_available: qVec !== null,
      embedding_only: embeddingOnly,
    },
    analytics,
    results,
  });
}
