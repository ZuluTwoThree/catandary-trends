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
 * Client key for per-IP limits.
 *
 * A route handler only sees headers, never the socket peer, so the only
 * source of a client address is `X-Forwarded-For` / `X-Real-IP` — and those
 * are attacker-controlled unless a proxy we run overwrites/appends them.
 * Without a proxy in front (the workstation instance answers directly on
 * :3001) trusting them lets any caller pick a fresh "IP" per request and
 * every per-IP limit collapses (security review 2026-09-02, E-3).
 *
 * So the headers are consulted ONLY with `TRUST_PROXY=1` — set on a deployment
 * that sits behind Caddy (which appends XFF and overwrites X-Real-IP). Then
 * the last `TRUSTED_PROXY_COUNT` hops (default 1) are ours and the entry just
 * inside them is the real client; a raw leftmost XFF value is never trusted.
 * Without `TRUST_PROXY` every request shares one bucket — coarse, but not
 * bypassable, and on a loopback-only instance the one bucket is the owner.
 *
 * Read per call (not at module load) so a test — or a config reload — can
 * flip the flag without re-importing the module.
 */
export const DIRECT_CLIENT = "direct";

function trustProxy(): boolean {
  return process.env.TRUST_PROXY === "1";
}

function trustedProxyCount(): number {
  return Math.max(1, parseInt(process.env.TRUSTED_PROXY_COUNT || "1", 10) || 1);
}

export function clientIp(request: Request): string {
  if (!trustProxy()) return DIRECT_CLIENT;
  const xff = request.headers.get("x-forwarded-for");
  if (xff) {
    const parts = xff.split(",").map((s) => s.trim()).filter(Boolean);
    if (parts.length) {
      const idx = parts.length - trustedProxyCount();
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
