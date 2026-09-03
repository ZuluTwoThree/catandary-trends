/**
 * Foresight Cockpit — Hybrid Search API (PostgreSQL + pgvector)
 *
 * Combines Postgres full-text lexical search + qwen3-embedding semantic search
 * (ANN over the 1024-dim Matryoshka-prefix column, HNSW-indexed) via
 * Reciprocal Rank Fusion (RRF). Returns results + analytics for the
 * Foresight Cockpit dashboard.
 *
 * GET /api/search?q=...&vertical=FOOD&limit=20
 *
 * Response shape:
 *   { query, vertical, results[], analytics: { timeline, lead_time, pestel, mega_trends, co_occurrence, verticals }, meta }
 */
import { NextResponse } from "next/server";
import { getPool, q, q1 } from "@/lib/pg";
import { rateLimitInfo, clientIp } from "@/lib/rateLimit";
import { archiveWindowDays } from "@/lib/archiveWindow";

// Every search embeds the query (local GPU) + runs several DB aggregates, so an
// unguarded public GET is a resource-exhaustion vector (#5-hardening). Per-IP
// sliding-window limit; the trajectory route keeps its own stricter gate.
const SEARCH_RL_LIMIT = 30; // requests …
const SEARCH_RL_WINDOW_MS = 60_000; // … per minute per client

const OLLAMA_URL =
  process.env.OLLAMA_CLIENT_HOST || "http://127.0.0.1:11434";
const EMBED_MODEL = "qwen3-embedding";
const EMBED_DIM = 4096;
/** ANN column dimension (Matryoshka prefix of the 4096-dim embedding). */
const ANN_DIM = 1024;

const RRF_K = 60; // RRF smoothing constant
const ANALYTICS_MIN_N = 30; // minimum hits for analytics overlays
// Cap the analytics ID set so a broad query ("AI", "protein") can't materialize a
// huge int[] and drive several corpus-wide aggregates in one request (#56). Beyond
// this we report analytics as `sampled` (newest N) instead of scanning everything.
const ANALYTICS_MAX_IDS = 8000;

/** Must textually match the idx_trends_fts GIN index expression. */
const FTS_VECTOR =
  "to_tsvector('english', coalesce(title_en,'') || ' ' || coalesce(summary_en,'') || ' ' || coalesce(tags::text,''))";

// ---------------------------------------------------------------------------
// Ollama query embedding
// ---------------------------------------------------------------------------
async function embedQuery(query: string): Promise<number[] | null> {
  try {
    const resp = await fetch(`${OLLAMA_URL}/api/embed`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model: EMBED_MODEL, input: query }),
    });
    if (!resp.ok) return null;
    const data = (await resp.json()) as { embeddings?: number[][] };
    const vec = data.embeddings?.[0];
    if (!vec || vec.length !== EMBED_DIM) return null;
    return vec;
  } catch {
    return null;
  }
}

/** pgvector literal for the truncated (ANN) query vector. */
function toAnnLiteral(vec: number[]): string {
  return "[" + vec.slice(0, ANN_DIM).join(",") + "]";
}

// ---------------------------------------------------------------------------
// Lexical search (Postgres FTS)
// ---------------------------------------------------------------------------
async function ftsSearch(
  query: string,
  vertical: string | null,
  maxResults: number,
  maxAgeDays: number | null
): Promise<Array<{ id: number }>> {
  const params: unknown[] = [query];
  let sql = `SELECT t.id FROM trends t
     WHERE ${FTS_VECTOR} @@ websearch_to_tsquery('english', $1)
       AND t.status = 'published'`;
  if (vertical) {
    params.push(vertical);
    sql += ` AND t.primary_vertical = $${params.length}`;
  }
  if (maxAgeDays != null) {
    params.push(`${maxAgeDays} days`);
    sql += ` AND t.sort_date >= NOW() - $${params.length}::interval`;
  }
  params.push(maxResults * 3);
  sql += ` ORDER BY ts_rank(${FTS_VECTOR}, websearch_to_tsquery('english', $1)) DESC
     LIMIT $${params.length}`;
  try {
    return await q<{ id: number }>(sql, params);
  } catch {
    return [];
  }
}

/** ALL lexical matching IDs (no limit) for analytics */
async function ftsAllIds(
  query: string,
  vertical: string | null,
  maxAgeDays: number | null
): Promise<number[]> {
  const params: unknown[] = [query];
  let sql = `SELECT t.id FROM trends t
     WHERE ${FTS_VECTOR} @@ websearch_to_tsquery('english', $1)
       AND t.status = 'published'`;
  if (vertical) {
    params.push(vertical);
    sql += ` AND t.primary_vertical = $${params.length}`;
  }
  if (maxAgeDays != null) {
    params.push(`${maxAgeDays} days`);
    sql += ` AND t.sort_date >= NOW() - $${params.length}::interval`;
  }
  // Bound the analytics ID set (#56): newest ANALYTICS_MAX_IDS+1 so the caller can
  // detect truncation and flag the analytics as sampled.
  sql += ` ORDER BY t.id DESC LIMIT ${ANALYTICS_MAX_IDS + 1}`;
  try {
    return (await q<{ id: number }>(sql, params)).map((r) => r.id);
  } catch {
    return [];
  }
}

// ---------------------------------------------------------------------------
// Semantic search (pgvector ANN over embedding_1024, HNSW)
// ---------------------------------------------------------------------------
async function annSearch(
  qVec: number[],
  vertical: string | null,
  k: number,
  threshold: number,
  maxAgeDays: number | null
): Promise<Array<{ id: number; score: number }>> {
  const lit = toAnnLiteral(qVec);
  const params: unknown[] = [lit];
  // `status = 'published'` matches the partial HNSW index
  // idx_trends_emb1024_pub_hnsw; a vertical filter is applied post-scan, so we
  // raise ef_search (SET LOCAL, needs a transaction) to keep enough candidates
  // after filtering.
  let sql = `SELECT id, 1 - (embedding_1024 <=> $1::vector) as score
     FROM trends
     WHERE status = 'published' AND embedding_1024 IS NOT NULL`;
  if (vertical) {
    params.push(vertical);
    sql += ` AND primary_vertical = $${params.length}`;
  }
  if (maxAgeDays != null) {
    params.push(`${maxAgeDays} days`);
    sql += ` AND sort_date >= NOW() - $${params.length}::interval`;
  }
  params.push(k);
  sql += ` ORDER BY embedding_1024 <=> $1::vector LIMIT $${params.length}`;
  const client = await getPool().connect();
  try {
    await client.query("BEGIN");
    await client.query("SET LOCAL hnsw.ef_search = 200");
    const res = await client.query(sql, params as never[]);
    await client.query("COMMIT");
    return (res.rows as Array<{ id: number; score: number }>)
      .map((r) => ({ id: r.id, score: Number(r.score) }))
      .filter((r) => r.score >= threshold);
  } catch {
    try {
      await client.query("ROLLBACK");
    } catch {
      /* ignore */
    }
    return [];
  } finally {
    client.release();
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

  ftsResults.forEach((r, i) => {
    const rank = i + 1;
    const existing = scores.get(r.id) || { rrf: 0, fts_rank: null, emb_score: null };
    existing.rrf += 1 / (RRF_K + rank);
    existing.fts_rank = rank;
    scores.set(r.id, existing);
  });

  embResults.forEach((r, i) => {
    const rank = i + 1;
    const existing = scores.get(r.id) || { rrf: 0, fts_rank: null, emb_score: null };
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
async function computeAnalytics(ids: number[], sampled = false) {
  const n = ids.length;
  const hasEnough = n >= ANALYTICS_MIN_N;

  if (!hasEnough) {
    return {
      total_matches: n,
      has_enough_data: false,
      sampled,
      timeline: [],
      lead_time: {},
      pestel: {},
      mega_trends: [],
      co_occurrence: [],
      verticals: {},
    };
  }

  // Timeline: monthly histogram
  const timeline = await q<{ month: string; count: number }>(
    `SELECT to_char(COALESCE(r.published_date, t.created_at), 'YYYY-MM') as month,
            COUNT(*)::int as count
     FROM trends t
     LEFT JOIN raw_entries r ON t.raw_entry_id = r.id
     WHERE t.id = ANY($1::int[])
     GROUP BY month
     ORDER BY month`,
    [ids]
  );

  // Lead-time tier breakdown
  const leadTime = await q<{ tier: string; count: number }>(
    `SELECT COALESCE(lt.lead_time_tier, 'unknown') as tier, COUNT(*)::int as count
     FROM trends t
     LEFT JOIN source_lead_time_tier lt ON t.source_name = lt.source_name
     WHERE t.id = ANY($1::int[])
     GROUP BY tier
     ORDER BY count DESC`,
    [ids]
  );

  // PESTEL distribution (jsonb arrays, unnested in SQL)
  const pestelRows = await q<{ dim: string; count: number }>(
    `SELECT d.dim, COUNT(*)::int as count
     FROM trends t, jsonb_array_elements_text(t.pestel) as d(dim)
     WHERE t.id = ANY($1::int[])
     GROUP BY d.dim`,
    [ids]
  );
  const pestelCounts: Record<string, number> = {};
  for (const r of pestelRows) pestelCounts[r.dim] = r.count;

  // Mega-trend distribution
  const megaTrends = await q<{ mega_trend: string; count: number }>(
    `SELECT mega_trend, COUNT(*)::int as count
     FROM trends
     WHERE id = ANY($1::int[]) AND mega_trend IS NOT NULL
     GROUP BY mega_trend
     ORDER BY count DESC
     LIMIT 15`,
    [ids]
  );

  // Cross-vertical distribution
  const verticals = await q<{ primary_vertical: string; count: number }>(
    `SELECT primary_vertical, COUNT(*)::int as count
     FROM trends
     WHERE id = ANY($1::int[])
     GROUP BY primary_vertical
     ORDER BY count DESC`,
    [ids]
  );

  // Co-occurrence: TF-IDF weighted tags — TF within the result set (SQL-side),
  // DF corpus-wide per candidate tag.
  const SIGNAL_TYPE_TAGS = new Set([
    "product_launch", "research", "market_shift", "consumer_behavior",
    "regulation", "funding", "partnership", "patent",
  ]);
  const tfRows = await q<{ raw_tag: string; tf: number }>(
    `SELECT tag.t as raw_tag, COUNT(*)::int as tf
     FROM trends tr, jsonb_array_elements_text(tr.tags) as tag(t)
     WHERE tr.id = ANY($1::int[])
     GROUP BY tag.t
     ORDER BY tf DESC
     LIMIT 80`,
    [ids]
  );
  const tagTf: Record<string, number> = {};
  for (const r of tfRows) {
    const tag = r.raw_tag.replace(/_/g, " ").toLowerCase().trim();
    if (!tag || SIGNAL_TYPE_TAGS.has(r.raw_tag)) continue;
    tagTf[tag] = (tagTf[tag] || 0) + r.tf;
  }
  const topTfTags = Object.entries(tagTf)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 50);

  const totalDocs =
    (await q1<{ c: number }>(
      "SELECT COUNT(*)::int as c FROM trends WHERE status = 'published'"
    ))?.c ?? 1;

  // Document frequency for ALL candidate tags in ONE corpus pass (#56) — replaces
  // up to 50 corpus-wide `tags::text ILIKE` full scans (one per tag). Normalize the
  // stored tags the same way as the TF keys (underscore→space, lower) and match the
  // candidate set exactly.
  const candidateTags = topTfTags.filter(([, tf]) => tf >= 2).map(([tag]) => tag);
  const dfMap: Record<string, number> = {};
  if (candidateTags.length) {
    const dfRows = await q<{ norm: string; df: number }>(
      `SELECT lower(replace(tag.t, '_', ' ')) AS norm, COUNT(DISTINCT tr.id)::int AS df
       FROM trends tr, jsonb_array_elements_text(tr.tags) AS tag(t)
       WHERE tr.status = 'published'
         AND lower(replace(tag.t, '_', ' ')) = ANY($1)
       GROUP BY norm`,
      [candidateTags]
    );
    for (const r of dfRows) dfMap[r.norm] = r.df;
  }
  const coOccurrence: Array<{ tag: string; count: number; tfidf: number }> = [];
  for (const [tag, tf] of topTfTags) {
    if (tf < 2) continue; // skip singletons in result set
    const df = dfMap[tag] || 1;
    const idf = Math.log(totalDocs / df);
    coOccurrence.push({ tag, count: tf, tfidf: Math.round(tf * idf * 100) / 100 });
  }
  coOccurrence.sort((a, b) => b.tfidf - a.tfidf);

  return {
    total_matches: n,
    has_enough_data: hasEnough,
    sampled,
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
  const query = (searchParams.get("q") || "").trim();
  const vertical = searchParams.get("vertical")?.toUpperCase() || null;
  const limit = Math.min(parseInt(searchParams.get("limit") || "20", 10), 100);
  const threshold = parseFloat(searchParams.get("threshold") || "0.15");

  if (!query) {
    return NextResponse.json({ error: "q parameter required" }, { status: 400 });
  }

  const rl = rateLimitInfo(`search:${clientIp(request)}`, SEARCH_RL_LIMIT, SEARCH_RL_WINDOW_MS);
  if (!rl.ok) {
    return NextResponse.json(
      { error: "rate limit exceeded — please slow down" },
      { status: 429, headers: { "retry-after": String(rl.retryAfterSec) } }
    );
  }

  const t0 = Date.now();

  // Public window (#93): in PUBLIC_MODE the search API must not leak
  // archive articles past the window — enforced in all three query paths.
  const windowDays = archiveWindowDays();

  // 1. Embed query + lexical search (parallel)
  const [qVec, ftsResults] = await Promise.all([
    embedQuery(query),
    ftsSearch(query, vertical, limit, windowDays),
  ]);

  // 2. Semantic ANN search (pgvector HNSW on the 1024-dim prefix)
  let embResults: Array<{ id: number; score: number }> = [];
  if (qVec) {
    embResults = await annSearch(qVec, vertical, limit * 3, threshold, windowDays);
  }

  // 3. Low-confidence handling: no lexical hits = query term doesn't appear
  //    literally anywhere → require a stricter semantic score to suppress noise.
  const ftsHasHits = ftsResults.length > 0;
  const embeddingOnly = !ftsHasHits && embResults.length > 0;
  if (embeddingOnly) {
    const strictThreshold = 0.6;
    embResults = embResults.filter((r) => r.score >= strictThreshold);
  }

  // 4. RRF merge
  const merged = rrfMerge(ftsResults, embResults, limit);

  // 5. Collect matching IDs for analytics (bounded lexical set + semantic hits)
  const ftsIds = await ftsAllIds(query, vertical, windowDays);
  const sampled = ftsIds.length > ANALYTICS_MAX_IDS;
  const allMatchIds = new Set(sampled ? ftsIds.slice(0, ANALYTICS_MAX_IDS) : ftsIds);
  for (const r of embResults) allMatchIds.add(r.id);
  const allIds = [...allMatchIds];

  // 6. Analytics (flagged `sampled` when the match set was truncated)
  const analytics = await computeAnalytics(allIds, sampled);

  // 7. Hydrate top results
  const topIds = merged.map((m) => m.id);
  const hydrated = topIds.length
    ? await q(
        `SELECT t.id, t.slug, t.title_en, t.summary_en,
                t.primary_vertical, t.source_name, t.mega_trend, t.pestel, t.tags,
                t.trend_signal_type, t.published_at::text as published_at,
                t.created_at::text as created_at,
                COALESCE(lt.lead_time_tier, 'unknown') as lead_time_tier,
                LEAST(r.published_date, NOW())::text as source_date
         FROM trends t
         LEFT JOIN raw_entries r ON t.raw_entry_id = r.id
         LEFT JOIN source_lead_time_tier lt ON t.source_name = lt.source_name
         WHERE t.id = ANY($1::int[])`,
        [topIds]
      )
    : [];

  const byId = new Map(hydrated.map((h) => [h.id as number, h]));
  const results = merged
    .map((m) => {
      const h = byId.get(m.id);
      if (!h) return null;
      return {
        ...h,
        pestel: Array.isArray(h.pestel) ? h.pestel : [],
        tags: Array.isArray(h.tags) ? h.tags : [],
        rrf_score: m.rrf_score,
        fts_rank: m.fts_rank,
        emb_score: m.emb_score,
      };
    })
    .filter(Boolean);

  return NextResponse.json({
    query,
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
