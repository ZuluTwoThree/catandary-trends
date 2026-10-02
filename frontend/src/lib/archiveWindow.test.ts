/**
 * Day-boundary archive window (lib/archiveWindow.ts) — shared by the
 * entitlement layer, the windowed queries and the static export.
 */
import { describe, it, expect, afterEach } from "vitest";
import {
  windowStart,
  windowStartIso,
  withinWindow,
  parsePublicWindowDays,
  publicWindowDays,
  DEFAULT_PUBLIC_WINDOW_DAYS,
  DEFAULT_PUBLIC_NEWSLETTER_EDITIONS,
  parsePublicNewsletterEditions,
  publicNewsletterEditions,
} from "@/lib/archiveWindow";

const NOW = new Date("2026-09-02T18:45:12Z");

afterEach(() => {
  delete process.env.PUBLIC_WINDOW_DAYS;
});

describe("windowStart", () => {
  it("is the start of the current UTC day minus N days", () => {
    expect(windowStartIso(30, NOW)).toBe("2026-08-03T00:00:00.000Z");
    expect(windowStartIso(0, NOW)).toBe("2026-09-02T00:00:00.000Z");
  });

  it("does not move within a day — the determinism gate for two builds minutes apart", () => {
    const a = windowStart(30, new Date("2026-09-02T00:00:01Z"));
    const b = windowStart(30, new Date("2026-09-02T23:59:59Z"));
    expect(a.getTime()).toBe(b.getTime());
    const c = windowStart(30, new Date("2026-09-03T00:00:00Z"));
    expect(c.getTime() - a.getTime()).toBe(86_400_000);
  });
});

describe("withinWindow", () => {
  it("accepts dates on or after the boundary, rejects earlier ones", () => {
    expect(withinWindow("2026-08-03T00:00:00Z", 30, NOW)).toBe(true);
    expect(withinWindow("2026-08-02T23:59:59Z", 30, NOW)).toBe(false);
    expect(withinWindow(new Date("2026-09-01T00:00:00Z"), 30, NOW)).toBe(true);
  });

  it("null window = unlimited", () => {
    expect(withinWindow("2020-01-01", null, NOW)).toBe(true);
  });

  it("fails open on missing or unparseable dates", () => {
    expect(withinWindow(null, 30, NOW)).toBe(true);
    expect(withinWindow(undefined, 30, NOW)).toBe(true);
    expect(withinWindow("kein-datum", 30, NOW)).toBe(true);
  });
});

describe("PUBLIC_WINDOW_DAYS", () => {
  it("defaults to 14 (Owner 2026-10-02; 30 before)", () => {
    expect(DEFAULT_PUBLIC_WINDOW_DAYS).toBe(14);
    expect(parsePublicWindowDays(undefined)).toBe(14);
    expect(parsePublicWindowDays("")).toBe(14);
    expect(publicWindowDays()).toBe(14);
  });

  it("takes a positive integer from the env", () => {
    expect(parsePublicWindowDays("3")).toBe(3);
    expect(parsePublicWindowDays("90")).toBe(90);
    process.env.PUBLIC_WINDOW_DAYS = "7";
    expect(publicWindowDays()).toBe(7);
  });

  it("falls back on garbage", () => {
    for (const v of ["0", "-5", "1.5", "abc", "99999"]) {
      expect(parsePublicWindowDays(v)).toBe(14);
    }
  });
});

describe("newsletter archive size (PUBLIC_NEWSLETTER_EDITIONS)", () => {
  afterEach(() => {
    delete process.env.PUBLIC_NEWSLETTER_EDITIONS;
  });

  it("defaults to 12 editions", () => {
    expect(DEFAULT_PUBLIC_NEWSLETTER_EDITIONS).toBe(12);
    expect(parsePublicNewsletterEditions(undefined)).toBe(12);
    expect(parsePublicNewsletterEditions("")).toBe(12);
    expect(publicNewsletterEditions()).toBe(12);
  });

  it("accepts positive integers and falls back on anything else", () => {
    expect(parsePublicNewsletterEditions("4")).toBe(4);
    expect(parsePublicNewsletterEditions("520")).toBe(520);
    for (const bad of ["0", "-1", "1.5", "abc", "521"]) {
      expect(parsePublicNewsletterEditions(bad)).toBe(12);
    }
    process.env.PUBLIC_NEWSLETTER_EDITIONS = "6";
    expect(publicNewsletterEditions()).toBe(6);
  });
});
