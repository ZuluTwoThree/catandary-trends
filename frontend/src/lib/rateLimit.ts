/**
 * Lightweight in-process guards for expensive API routes (#55).
 *
 * Single-server deployment (one Node process behind Caddy) → module-level state is
 * shared across requests, no external store needed. Sliding-window rate limit +
 * a global concurrency gate for heavy (GPU/subprocess) computations.
 */

const windows = new Map<string, number[]>();

/** Sliding-window rate limit. Returns true if the call is allowed (and records it). */
export function rateLimit(key: string, limit: number, windowMs: number): boolean {
  const now = Date.now();
  const hits = (windows.get(key) || []).filter((t) => now - t < windowMs);
  if (hits.length >= limit) {
    windows.set(key, hits);
    return false;
  }
  hits.push(now);
  windows.set(key, hits);
  return true;
}

/** Best-effort client IP from proxy headers (Caddy sets X-Forwarded-For). */
export function clientIp(request: Request): string {
  const xff = request.headers.get("x-forwarded-for");
  if (xff) return xff.split(",")[0].trim();
  return request.headers.get("x-real-ip") || "local";
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
