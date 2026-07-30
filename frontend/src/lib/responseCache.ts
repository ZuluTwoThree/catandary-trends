/**
 * Bounded in-process response cache for expensive API routes.
 *
 * Extracted from the ad-hoc `Map` in api/foresight/analyze/route.ts, which had
 * no size cap and no eviction: entries only ever expired when someone happened
 * to read them again, so a stream of distinct queries grew it without limit for
 * the lifetime of the process. Same single-process justification as
 * lib/rateLimit.ts — one Node server behind Caddy, so a shared store would be
 * more machinery than the problem warrants.
 *
 * Eviction is oldest-first on insert (the idiom in rateLimit.ts:29-40), plus a
 * TTL check on read.
 */

export interface CacheOptions {
  /** Hard cap on entries; oldest are evicted first. */
  maxEntries?: number;
  /** Time-to-live in milliseconds. */
  ttlMs?: number;
}

export class ResponseCache<T = unknown> {
  private store = new Map<string, { at: number; value: T }>();
  private readonly maxEntries: number;
  private readonly ttlMs: number;

  constructor({ maxEntries = 200, ttlMs = 15 * 60_000 }: CacheOptions = {}) {
    this.maxEntries = maxEntries;
    this.ttlMs = ttlMs;
  }

  get(key: string): T | null {
    const hit = this.store.get(key);
    if (!hit) return null;
    if (Date.now() - hit.at > this.ttlMs) {
      this.store.delete(key);
      return null;
    }
    // Refresh insertion order so hot keys survive eviction (Map preserves it).
    this.store.delete(key);
    this.store.set(key, hit);
    return hit.value;
  }

  set(key: string, value: T): void {
    if (this.store.has(key)) this.store.delete(key);
    this.store.set(key, { at: Date.now(), value });
    while (this.store.size > this.maxEntries) {
      const oldest = this.store.keys().next();
      if (oldest.done) break;
      this.store.delete(oldest.value);
    }
  }

  get size(): number {
    return this.store.size;
  }

  clear(): void {
    this.store.clear();
  }
}

/** Stable cache key from an arbitrary param bag — order-independent. */
export function cacheKey(parts: Record<string, string | number | undefined>): string {
  return Object.keys(parts)
    .sort()
    .map((k) => `${k}=${parts[k] ?? ""}`)
    .join("|");
}
