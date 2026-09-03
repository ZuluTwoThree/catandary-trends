import { describe, it, expect, afterEach } from "vitest";
import {
  STATIC_PAGE_SIZE,
  verticalFeedHref,
  verticalSlug,
  verticalFromSlug,
  listingPath,
  pageCount,
  parsePageParam,
  pageWindow,
} from "@/lib/staticListing";
import { VERTICALS } from "@/lib/types";

describe("static listing URLs", () => {
  it("page 1 is the base path, later pages get /page/<n>", () => {
    expect(listingPath(null, 1)).toBe("/trends");
    expect(listingPath(null, 0)).toBe("/trends");
    expect(listingPath(null, 2)).toBe("/trends/page/2");
    expect(listingPath("TECH", 1)).toBe("/trends/v/tech");
    expect(listingPath("TECH", 7)).toBe("/trends/v/tech/page/7");
  });

  it("vertical slugs are the lowercase ids and round-trip", () => {
    for (const v of VERTICALS) {
      const slug = verticalSlug(v.id);
      expect(slug).toBe(slug.toLowerCase());
      expect(verticalFromSlug(slug)).toBe(v.id);
    }
  });

  it("only the exact lowercase slug resolves (uppercase is Apache's 301)", () => {
    expect(verticalFromSlug("TECH")).toBeNull();
    expect(verticalFromSlug("Tech")).toBeNull();
    expect(verticalFromSlug("tech/")).toBeNull();
    expect(verticalFromSlug("")).toBeNull();
    expect(verticalFromSlug("foresight")).toBeNull();
  });
});

describe("verticalFeedHref", () => {
  const saved = { s: process.env.STATIC_EXPORT, p: process.env.NEXT_PUBLIC_STATIC_EXPORT };
  afterEach(() => {
    if (saved.s === undefined) delete process.env.STATIC_EXPORT;
    else process.env.STATIC_EXPORT = saved.s;
    if (saved.p === undefined) delete process.env.NEXT_PUBLIC_STATIC_EXPORT;
    else process.env.NEXT_PUBLIC_STATIC_EXPORT = saved.p;
  });

  it("links the search-param feed on the workstation (param `v`, lib/filter-params.ts)", () => {
    delete process.env.STATIC_EXPORT;
    delete process.env.NEXT_PUBLIC_STATIC_EXPORT;
    expect(verticalFeedHref("TECH")).toBe("/trends?v=TECH");
  });

  it("links the static vertical page in the export", () => {
    process.env.STATIC_EXPORT = "1";
    expect(verticalFeedHref("TECH")).toBe("/trends/v/tech");
    expect(verticalFeedHref("LIFESTYLE")).toBe("/trends/v/lifestyle");
  });
});

describe("pageCount", () => {
  it("is at least 1 and rounds up", () => {
    expect(pageCount(0)).toBe(1);
    expect(pageCount(1)).toBe(1);
    expect(pageCount(STATIC_PAGE_SIZE)).toBe(1);
    expect(pageCount(STATIC_PAGE_SIZE + 1)).toBe(2);
    expect(pageCount(15229)).toBe(635);
    expect(pageCount(50, 10)).toBe(5);
  });
});

describe("parsePageParam", () => {
  it("accepts integers from 2 upwards", () => {
    expect(parsePageParam("2")).toBe(2);
    expect(parsePageParam("635")).toBe(635);
  });

  it("rejects page 1 (base path only) and anything that is not a plain integer", () => {
    for (const bad of ["1", "0", "01", "02", "-2", "1.5", "2a", "", " 2", "1e3", "9999999"]) {
      expect(parsePageParam(bad), bad).toBeNull();
    }
  });
});

describe("pageWindow", () => {
  it("shows first, last and two neighbours with gap markers", () => {
    expect(pageWindow(1, 1)).toEqual([1]);
    expect(pageWindow(1, 5)).toEqual([1, 2, 3, -1, 5]);
    expect(pageWindow(10, 20)).toEqual([1, -1, 8, 9, 10, 11, 12, -1, 20]);
    expect(pageWindow(20, 20)).toEqual([1, -1, 18, 19, 20]);
  });
});
