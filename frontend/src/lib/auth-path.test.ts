import { describe, it, expect, vi } from "vitest";

// auth.ts pulls in the pg pool and next/headers at module level; stub both so
// this pure-function test touches neither Postgres nor the Next runtime
// (same convention as auth.test.ts).
vi.mock("@/lib/pg", () => ({
  q: vi.fn(async () => []),
  q1: vi.fn(async () => null),
  getPool: vi.fn(),
  withTransaction: vi.fn(async () => null),
}));
vi.mock("next/headers", () => ({
  cookies: async () => ({ get: () => undefined, set: () => {}, delete: () => {} }),
}));

import { isSafeInternalPath } from "@/lib/auth";

describe("isSafeInternalPath — post-signin redirect guard", () => {
  it("accepts a plain internal path", () => {
    expect(isSafeInternalPath("/x")).toBe(true);
  });

  it("accepts an internal path with query string", () => {
    expect(isSafeInternalPath("/trends/pricing?a=b")).toBe(true);
  });

  it("rejects protocol-relative external redirects (//host)", () => {
    expect(isSafeInternalPath("//evil.com")).toBe(false);
  });

  it("rejects absolute URLs", () => {
    expect(isSafeInternalPath("https://evil.com")).toBe(false);
  });

  it("rejects the empty string", () => {
    expect(isSafeInternalPath("")).toBe(false);
  });

  it("rejects undefined and null", () => {
    expect(isSafeInternalPath(undefined)).toBe(false);
    expect(isSafeInternalPath(null)).toBe(false);
  });
});
