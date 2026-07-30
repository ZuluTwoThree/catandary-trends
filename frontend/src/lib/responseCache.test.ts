import { describe, expect, it, vi } from "vitest";
import { ResponseCache, cacheKey } from "./responseCache";

describe("ResponseCache", () => {
  it("returns what was stored", () => {
    const c = new ResponseCache<string>();
    c.set("a", "one");
    expect(c.get("a")).toBe("one");
    expect(c.get("missing")).toBeNull();
  });

  it("evicts the oldest entry instead of growing without bound", () => {
    // The bug this class exists to fix: analyze/route.ts used a plain Map with
    // no cap, so a stream of distinct queries grew it for the process lifetime.
    const c = new ResponseCache<number>({ maxEntries: 3 });
    c.set("a", 1);
    c.set("b", 2);
    c.set("c", 3);
    c.set("d", 4);
    expect(c.size).toBe(3);
    expect(c.get("a")).toBeNull();
    expect(c.get("d")).toBe(4);
  });

  it("keeps hot keys alive across evictions", () => {
    const c = new ResponseCache<number>({ maxEntries: 3 });
    c.set("a", 1);
    c.set("b", 2);
    c.set("c", 3);
    c.get("a"); // touch
    c.set("d", 4);
    expect(c.get("a")).toBe(1);
    expect(c.get("b")).toBeNull();
  });

  it("expires entries on read once the TTL has passed", () => {
    vi.useFakeTimers();
    try {
      const c = new ResponseCache<string>({ ttlMs: 1000 });
      c.set("a", "one");
      vi.advanceTimersByTime(999);
      expect(c.get("a")).toBe("one");
      vi.advanceTimersByTime(2);
      expect(c.get("a")).toBeNull();
      expect(c.size).toBe(0);
    } finally {
      vi.useRealTimers();
    }
  });

  it("overwrites rather than duplicating a key", () => {
    const c = new ResponseCache<string>();
    c.set("a", "one");
    c.set("a", "two");
    expect(c.size).toBe(1);
    expect(c.get("a")).toBe("two");
  });
});

describe("cacheKey", () => {
  it("is independent of key order", () => {
    expect(cacheKey({ b: 2, a: 1 })).toBe(cacheKey({ a: 1, b: 2 }));
  });

  it("distinguishes an absent value from an empty one only by content", () => {
    expect(cacheKey({ a: undefined })).toBe("a=");
    expect(cacheKey({ a: 1 })).not.toBe(cacheKey({ a: 2 }));
  });
});
