import { describe, it, expect } from "vitest";
import {
  parseFilterParams,
  buildQueryString,
  getActiveChips,
  PARAM,
  type ParsedFilters,
} from "@/lib/filter-params";

/** Serialize a parsed filter state back into a query string via buildQueryString. */
function serialize(f: ParsedFilters): string {
  const mutations: Record<string, string | null> = {
    [PARAM.verticals]: f.verticals?.join(",") ?? null,
    [PARAM.pestel]: f.pestel?.join(",") ?? null,
    [PARAM.signal]: f.signal_types?.join(",") ?? null,
    [PARAM.mega]: f.mega_trend ?? null,
    [PARAM.excludeSources]: f.exclude_sources?.join(",") ?? null,
    [PARAM.minScore]: f.min_trend_score ? String(f.min_trend_score) : null,
    [PARAM.dateRange]: f.date_range ?? null,
    [PARAM.search]: f.search ?? null,
    [PARAM.sort]: f.sort_by ?? null,
    [PARAM.view]: f.view,
    [PARAM.page]: String(f.page),
  };
  return buildQueryString(new URLSearchParams(), mutations, { resetPage: false });
}

/** Turn a "?a=b&c=d" query string back into the RawParams shape parse expects. */
function qsToRaw(qs: string): Record<string, string> {
  return Object.fromEntries(new URLSearchParams(qs.replace(/^\?/, "")).entries());
}

describe("parseFilterParams — roundtrip stability", () => {
  it("parse → buildQueryString → parse is stable for a rich filter set", () => {
    const first = parseFilterParams({
      [PARAM.verticals]: "FOOD,TECH",
      [PARAM.pestel]: "T,En",
      [PARAM.signal]: "funding,research",
      [PARAM.mega]: "Generative_AI",
      [PARAM.excludeSources]: "TechCrunch,The Verge",
      [PARAM.minScore]: "40",
      [PARAM.dateRange]: "7d",
      [PARAM.search]: "protein bars",
      [PARAM.sort]: "score_desc",
      [PARAM.view]: "list",
      [PARAM.page]: "3",
    });
    const second = parseFilterParams(qsToRaw(serialize(first)));
    expect(second).toEqual(first);
  });

  it("parse → buildQueryString → parse is stable for empty params (all defaults)", () => {
    const first = parseFilterParams({});
    const second = parseFilterParams(qsToRaw(serialize(first)));
    expect(second).toEqual(first);
  });

  it("defaults are what the empty parse promises", () => {
    const f = parseFilterParams({});
    expect(f.status).toBe("published");
    expect(f.verticals).toBeUndefined();
    expect(f.pestel).toBeUndefined();
    expect(f.signal_types).toBeUndefined();
    expect(f.mega_trend).toBeUndefined();
    expect(f.exclude_sources).toBeUndefined();
    expect(f.min_trend_score).toBeUndefined();
    expect(f.date_range).toBe("all");
    expect(f.search).toBeUndefined();
    expect(f.sort_by).toBe("date_desc");
    expect(f.view).toBe("grid");
    expect(f.page).toBe(1);
    expect(f.offset).toBe(0);
  });
});

describe("parseFilterParams — invalid values fall back to defaults", () => {
  it("page=-1 falls back to page 1", () => {
    const f = parseFilterParams({ [PARAM.page]: "-1" });
    expect(f.page).toBe(1);
    expect(f.offset).toBe(0);
  });

  it("page=0 and non-numeric page fall back to page 1", () => {
    expect(parseFilterParams({ [PARAM.page]: "0" }).page).toBe(1);
    expect(parseFilterParams({ [PARAM.page]: "abc" }).page).toBe(1);
  });

  it("an unknown sort value falls back to date_desc", () => {
    const f = parseFilterParams({ [PARAM.sort]: "banana" });
    expect(f.sort_by).toBe("date_desc");
  });

  it("an unknown vertical is dropped entirely", () => {
    const f = parseFilterParams({ [PARAM.verticals]: "SPORTS" });
    expect(f.verticals).toBeUndefined();
  });

  it("a mixed vertical list keeps only whitelisted entries", () => {
    const f = parseFilterParams({ [PARAM.verticals]: "FOOD,SPORTS,TECH" });
    expect(f.verticals).toEqual(["FOOD", "TECH"]);
  });

  it("unknown date range, view and non-numeric min_score fall back to defaults", () => {
    const f = parseFilterParams({
      [PARAM.dateRange]: "90d",
      [PARAM.view]: "table",
      [PARAM.minScore]: "abc",
    });
    expect(f.date_range).toBe("all");
    expect(f.view).toBe("grid");
    expect(f.min_trend_score).toBeUndefined();
  });
});

describe("getActiveChips", () => {
  it("returns [] for empty filters", () => {
    expect(getActiveChips(parseFilterParams({}))).toEqual([]);
  });
});
