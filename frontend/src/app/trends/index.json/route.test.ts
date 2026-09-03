/**
 * /trends/index.json — the static search index. Real rows only in a public
 * deployment (export / PUBLIC_MODE); the workstation build gets an empty
 * array and never fetches it. A database error fails the export build and
 * is swallowed elsewhere (CI builds without Postgres).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const getPublicIndexRows = vi.fn();
vi.mock("@/lib/db", () => ({ getPublicIndexRows: (...a: unknown[]) => getPublicIndexRows(...a) }));

import { GET, dynamic } from "./route";

const rows = [
  {
    slug: "b-2", title_en: "B", summary_en: "s", primary_vertical: "TECH", verticals: ["TECH"],
    pestel: ["T"], mega_trend: null, sort_date: "2026-09-01 10:00:00", trend_score: 0.5,
    source_name: "S", trend_signal_type: "product_launch", source_type: "trade_media",
  },
  {
    slug: "a-1", title_en: "A", summary_en: "s", primary_vertical: "ECO", verticals: ["ECO"],
    pestel: ["En"], mega_trend: "circular_economy", sort_date: "2026-09-02 10:00:00", trend_score: 0.6,
    source_name: "S", trend_signal_type: "research", source_type: "api",
  },
];

beforeEach(() => {
  getPublicIndexRows.mockReset();
  getPublicIndexRows.mockResolvedValue(rows);
});

afterEach(() => {
  delete process.env.STATIC_EXPORT;
  delete process.env.NEXT_PUBLIC_STATIC_EXPORT;
  delete process.env.PUBLIC_MODE;
});

describe("GET /trends/index.json", () => {
  it("is force-static (the export needs the literal)", () => {
    expect(dynamic).toBe("force-static");
  });

  it("writes the windowed index in the export, one entry per line, listing order", async () => {
    process.env.STATIC_EXPORT = "1";
    const res = await GET();
    expect(res.headers.get("content-type")).toMatch(/^application\/json/);
    const text = await res.text();
    expect(getPublicIndexRows).toHaveBeenCalledWith(30);
    expect(text.split("\n").length - 1).toBe(2);
    const parsed = JSON.parse(text);
    expect(parsed.map((e: { slug: string }) => e.slug)).toEqual(["a-1", "b-2"]);
    expect(parsed[0].source_type).toBe("research");
  });

  it("serves the index in the PUBLIC_MODE preview too", async () => {
    process.env.PUBLIC_MODE = "1";
    expect(JSON.parse(await (await GET()).text())).toHaveLength(2);
  });

  it("is an empty array on the workstation build (no query at all)", async () => {
    const text = await (await GET()).text();
    expect(text).toBe("[]\n");
    expect(getPublicIndexRows).not.toHaveBeenCalled();
  });

  it("fails the export on a database error, degrades to [] otherwise", async () => {
    getPublicIndexRows.mockRejectedValue(new Error("no db"));
    process.env.STATIC_EXPORT = "1";
    await expect(GET()).rejects.toThrow("no db");
    delete process.env.STATIC_EXPORT;
    process.env.PUBLIC_MODE = "1";
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    expect(await (await GET()).text()).toBe("[]\n");
    warn.mockRestore();
  });
});
