/**
 * PROTOTYPE — semantic search over trends via embeddings.
 *
 * Status: Backend-only prototype. No frontend integration yet.
 * See BACKLOG.md entry "Hybrid-Suche (FTS5 + Embedding-Similarity)" for the full plan.
 *
 * What's here:
 *   - Loads all trend embeddings once per process (cached in module scope).
 *   - Gets query embedding from Ollama (qwen3-embedding, same model as pipeline).
 *   - Brute-force cosine similarity, top-K, optional vertical filter.
 *
 * What's missing (intentionally):
 *   - FTS5 lexical leg
 *   - Reciprocal Rank Fusion
 *   - Cache invalidation on new trends (currently only cleared on process restart)
 *   - Query debouncing / rate limiting
 *
 * Usage:
 *   GET /api/search?q=Getränke&vertical=FOOD&limit=10
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

// Module-scoped cache: loaded on first request, kept for process lifetime.
type TrendVec = {
  id: number;
  primary_vertical: string;
  embedding: Float32Array;
  norm: number;
};
let cache: TrendVec[] | null = null;

function loadEmbeddings(): TrendVec[] {
  if (cache) return cache;
  const db = new Database(DB_PATH, { readonly: true });
  db.pragma("journal_mode = WAL");
  const rows = db
    .prepare(
      `SELECT id, primary_vertical, embedding
       FROM trends
       WHERE status = 'published' AND embedding IS NOT NULL`
    )
    .all() as Array<{ id: number; primary_vertical: string; embedding: Buffer }>;
  db.close();

  const out: TrendVec[] = [];
  for (const r of rows) {
    if (r.embedding.length !== EMBED_DIM * 4) continue; // skip malformed
    const vec = new Float32Array(
      r.embedding.buffer,
      r.embedding.byteOffset,
      EMBED_DIM
    ).slice(); // copy so Buffer can be GC'd
    let sum = 0;
    for (let i = 0; i < EMBED_DIM; i++) sum += vec[i] * vec[i];
    out.push({
      id: r.id,
      primary_vertical: r.primary_vertical,
      embedding: vec,
      norm: Math.sqrt(sum) || 1,
    });
  }
  cache = out;
  return out;
}

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

function cosineAgainst(
  q: Float32Array,
  qNorm: number,
  t: TrendVec
): number {
  let dot = 0;
  const v = t.embedding;
  for (let i = 0; i < EMBED_DIM; i++) dot += q[i] * v[i];
  return dot / (qNorm * t.norm);
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const q = (searchParams.get("q") || "").trim();
  const vertical = searchParams.get("vertical")?.toUpperCase() || null;
  const limit = Math.min(parseInt(searchParams.get("limit") || "10", 10), 50);
  const threshold = parseFloat(searchParams.get("threshold") || "0.3");

  if (!q) {
    return NextResponse.json({ error: "q parameter required" }, { status: 400 });
  }

  const t0 = Date.now();
  const qVec = await embedQuery(q);
  if (!qVec) {
    return NextResponse.json(
      { error: "embedding service unavailable" },
      { status: 503 }
    );
  }
  let qNorm = 0;
  for (let i = 0; i < EMBED_DIM; i++) qNorm += qVec[i] * qVec[i];
  qNorm = Math.sqrt(qNorm) || 1;

  const trends = loadEmbeddings();
  const pool = vertical
    ? trends.filter((t) => t.primary_vertical === vertical)
    : trends;

  const scored: Array<{ id: number; score: number }> = [];
  for (const t of pool) {
    const s = cosineAgainst(qVec, qNorm, t);
    if (s >= threshold) scored.push({ id: t.id, score: s });
  }
  scored.sort((a, b) => b.score - a.score);
  const top = scored.slice(0, limit);

  // Hydrate top IDs with minimal trend info for display
  const db = new Database(DB_PATH, { readonly: true });
  db.pragma("journal_mode = WAL");
  const placeholders = top.map(() => "?").join(",");
  const hydrated = top.length
    ? (db
        .prepare(
          `SELECT id, slug, title_de, title_en, summary_de, summary_en,
                  primary_vertical, source_name
           FROM trends WHERE id IN (${placeholders})`
        )
        .all(...top.map((t) => t.id)) as Array<Record<string, unknown>>)
    : [];
  db.close();

  const byId = new Map(hydrated.map((h) => [h.id as number, h]));
  const results = top
    .map((t) => {
      const h = byId.get(t.id);
      return h ? { ...h, score: Math.round(t.score * 1000) / 1000 } : null;
    })
    .filter(Boolean);

  return NextResponse.json({
    query: q,
    vertical,
    limit,
    threshold,
    pool_size: pool.length,
    took_ms: Date.now() - t0,
    results,
  });
}
