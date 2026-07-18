/**
 * Lightweight in-process guards for expensive API routes (#55/#5-hardening).
 *
 * Single-server deployment (one Node process behind Caddy) → module-level state is
 * shared across requests, no external store needed. Provides a sliding-window rate
 * limit (with bounded memory) + a global concurrency gate for heavy computations.
 *
 * Memory safety: rate-limit keys are pruned when their window empties, swept
 * periodically for idle keys, and hard-capped so an attacker flooding distinct
 * keys (spoofed IPs, many emails) cannot grow the map without bound.
 */

const windows = new Map<string, number[]>();
const MAX_KEYS = 50_000; // hard cap on distinct rate-limit keys (memory bound)
const IDLE_TTL_MS = 3_600_000; // a key untouched this long is definitely expired
const SWEEP_INTERVAL_MS = 60_000;
let lastSweep = 0;

/** Drop keys whose most recent hit is older than IDLE_TTL (any window has expired). */
function sweep(now: number): void {
  for (const [key, hits] of windows) {
    if (hits.length === 0 || now - hits[hits.length - 1] > IDLE_TTL_MS) {
      windows.delete(key);
    }
  }
}

/** Evict the single key with the oldest most-recent hit (bounded scan). */
function evictOldest(): void {
  let oldestKey: string | null = null;
  let oldestTs = Infinity;
  for (const [key, hits] of windows) {
    const last = hits.length ? hits[hits.length - 1] : 0;
    if (last < oldestTs) {
      oldestTs = last;
      oldestKey = key;
    }
  }
  if (oldestKey !== null) windows.delete(oldestKey);
}

export interface RateResult {
  ok: boolean;
  /** Seconds until the caller may retry (for a Retry-After header). */
  retryAfterSec: number;
}

/**
 * Sliding-window rate limit with bounded memory. Returns whether the call is
 * allowed plus a Retry-After hint. `limit` calls are permitted per `windowMs`.
 */
export function rateLimitInfo(key: string, limit: number, windowMs: number): RateResult {
  const now = Date.now();
  if (now - lastSweep > SWEEP_INTERVAL_MS) {
    lastSweep = now;
    sweep(now);
  }
  const hits = (windows.get(key) || []).filter((t) => now - t < windowMs);
  if (hits.length >= limit) {
    windows.set(key, hits);
    const retryAfterSec = Math.max(1, Math.ceil((hits[0] + windowMs - now) / 1000));
    return { ok: false, retryAfterSec };
  }
  hits.push(now);
  if (!windows.has(key) && windows.size >= MAX_KEYS) {
    sweep(now);
    if (windows.size >= MAX_KEYS) evictOldest();
  }
  windows.set(key, hits);
  return { ok: true, retryAfterSec: 0 };
}

/** Boolean convenience wrapper (backwards-compatible with the earlier callers). */
export function rateLimit(key: string, limit: number, windowMs: number): boolean {
  return rateLimitInfo(key, limit, windowMs).ok;
}

/** Number of distinct rate-limit keys currently tracked (for tests/observability). */
export function rateLimitKeyCount(): number {
  return windows.size;
}

/** Test helper: clear all rate-limit state. */
export function _resetRateLimit(): void {
  windows.clear();
  lastSweep = 0;
}

/**
 * Spoofing-resistant client IP. `X-Forwarded-For` is a comma list
 * `clientSpoofable, …, appendedByCaddy`; the LEFTMOST entries are attacker-
 * controlled, the RIGHTMOST are appended by our own trusted proxies. We trust the
 * last `TRUSTED_PROXY_COUNT` hops (default 1 = Caddy) and read the entry just
 * inside them as the real client. Never trust a raw leftmost XFF value.
 */
const TRUSTED_PROXIES = Math.max(1, parseInt(process.env.TRUSTED_PROXY_COUNT || "1", 10) || 1);

export function clientIp(request: Request): string {
  const xff = request.headers.get("x-forwarded-for");
  if (xff) {
    const parts = xff.split(",").map((s) => s.trim()).filter(Boolean);
    if (parts.length) {
      const idx = parts.length - TRUSTED_PROXIES;
      return parts[idx >= 0 ? idx : 0];
    }
  }
  // X-Real-IP is set (overwritten, not appended) by Caddy → not client-spoofable.
  return request.headers.get("x-real-ip") || "unknown";
}

/** A global concurrency gate: at most `max` holders at once. */
export class ConcurrencyGate {
  private active = 0;
  constructor(private readonly max: number) {}
  tryAcquire(): boolean {
    if (this.active >= this.max) return false;
    this.active += 1;
    return true;
  }
  release(): void {
    this.active = Math.max(0, this.active - 1);
  }
  get inFlight(): number {
    return this.active;
  }
}
