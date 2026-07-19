import { describe, it, expect, beforeEach, vi } from "vitest";
import {
  rateLimit,
  rateLimitInfo,
  clientIp,
  rateLimitKeyCount,
  _resetRateLimit,
  ConcurrencyGate,
} from "./rateLimit";

function req(headers: Record<string, string>): Request {
  return new Request("http://x/", { headers });
}

describe("rateLimit sliding window", () => {
  beforeEach(() => _resetRateLimit());

  it("allows up to `limit` then blocks", () => {
    for (let i = 0; i < 3; i++) expect(rateLimit("k", 3, 60_000)).toBe(true);
    expect(rateLimit("k", 3, 60_000)).toBe(false);
  });

  it("resets after the window elapses", () => {
    vi.useFakeTimers();
    try {
      for (let i = 0; i < 3; i++) rateLimit("k", 3, 1_000);
      expect(rateLimit("k", 3, 1_000)).toBe(false);
      vi.advanceTimersByTime(1_100);
      expect(rateLimit("k", 3, 1_000)).toBe(true);
    } finally {
      vi.useRealTimers();
    }
  });

  it("reports a positive Retry-After when blocked", () => {
    for (let i = 0; i < 2; i++) rateLimitInfo("k", 2, 60_000);
    const r = rateLimitInfo("k", 2, 60_000);
    expect(r.ok).toBe(false);
    expect(r.retryAfterSec).toBeGreaterThan(0);
    expect(r.retryAfterSec).toBeLessThanOrEqual(60);
  });

  it("separates keys", () => {
    expect(rateLimit("a", 1, 60_000)).toBe(true);
    expect(rateLimit("a", 1, 60_000)).toBe(false);
    expect(rateLimit("b", 1, 60_000)).toBe(true);
  });
});

describe("rateLimit memory bound", () => {
  beforeEach(() => _resetRateLimit());

  it("drops idle keys on periodic sweep instead of growing forever", () => {
    vi.useFakeTimers();
    try {
      for (let i = 0; i < 100; i++) rateLimit(`ip-${i}`, 5, 1_000);
      expect(rateLimitKeyCount()).toBe(100);
      // advance past IDLE_TTL, then touch one key to trigger the sweep
      vi.advanceTimersByTime(3_600_001 + 60_001);
      rateLimit("fresh", 5, 1_000);
      // all 100 idle keys swept; only the fresh one remains
      expect(rateLimitKeyCount()).toBe(1);
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("clientIp spoofing resistance", () => {
  it("ignores a client-spoofed leftmost XFF and trusts the proxy-appended entry", () => {
    // client sent a fake XFF; Caddy appended the real IP on the right
    expect(clientIp(req({ "x-forwarded-for": "9.9.9.9, 203.0.113.7" }))).toBe("203.0.113.7");
  });

  it("uses the single XFF entry set by the proxy", () => {
    expect(clientIp(req({ "x-forwarded-for": "203.0.113.7" }))).toBe("203.0.113.7");
  });

  it("falls back to x-real-ip when no XFF", () => {
    expect(clientIp(req({ "x-real-ip": "198.51.100.4" }))).toBe("198.51.100.4");
  });

  it("returns 'unknown' with no proxy headers (no crash)", () => {
    expect(clientIp(req({}))).toBe("unknown");
  });
});

describe("ConcurrencyGate", () => {
  it("caps concurrent holders and releases", () => {
    const g = new ConcurrencyGate(2);
    expect(g.tryAcquire()).toBe(true);
    expect(g.tryAcquire()).toBe(true);
    expect(g.tryAcquire()).toBe(false);
    g.release();
    expect(g.tryAcquire()).toBe(true);
  });
});
