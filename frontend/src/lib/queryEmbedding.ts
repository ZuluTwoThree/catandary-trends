/**
 * Query vectors in the space of trends.embedding / embedding_1024.
 *
 * They come from the CPU embedding server (:8091, catandary-embed-cpu — the
 * same Qwen3-Embedding-8B as the pipeline, cos 0.9995 against the GPU vectors).
 * Until 2026-09-28 the cockpit search called Ollama on :11434, which has not run
 * since the move to llama.cpp: every query silently fell back to text match
 * only. Not :8090 either — that server carries whatever chat model is loaded,
 * and a chat model answering /v1/embeddings would put the query into another
 * space.
 */
const EMBED_HOST = process.env.RESEARCH_EMBED_HOST || "http://127.0.0.1:8091";
const EMBED_TIMEOUT_MS = 15_000;
export const EMBED_DIM = 4096;
/** ANN column dimension (Matryoshka prefix of the 4096-dim embedding). */
export const ANN_DIM = 1024;

/** The full 4096-dim query vector, or null when the embedder is unreachable. */
export async function embedQuery(query: string): Promise<number[] | null> {
  try {
    const resp = await fetch(`${EMBED_HOST}/v1/embeddings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ input: query }),
      signal: AbortSignal.timeout(EMBED_TIMEOUT_MS),
    });
    if (!resp.ok) return null;
    const data = (await resp.json()) as { data?: Array<{ embedding?: number[] }> };
    const vec = data.data?.[0]?.embedding;
    if (!vec || vec.length !== EMBED_DIM) return null;
    return vec;
  } catch {
    return null;
  }
}

/** pgvector literal of the 1024-dim prefix, for `embedding_1024 <=> $n::vector`. */
export function annLiteral(vec: number[]): string {
  return "[" + vec.slice(0, ANN_DIM).join(",") + "]";
}
