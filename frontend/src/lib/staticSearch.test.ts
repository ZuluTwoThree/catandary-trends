/**
 * Client-side search of the static export (design Schritt 5 / D): the pure
 * index build (truncation, order, serialization — deterministic) and the
 * pure filter/rank logic the browser runs over /trends/index.json.
 */
import { describe, it, expect } from "vitest";
import type { PublicIndexRow } from "@/lib/db";
import {
  MAX_RESULTS,
  SUMMARY_MAX,
  buildIndexEntries,
  buildSearchHash,
  entryId,
  entryToTrend,
  isActive,
  isoDate,
  matchesChips,
  megaOptions,
  parseSearchHash,
  prepareIndex,
  rowToEntry,
  search,
  serializeIndex,
  tokenize,
  truncateSummary,
  type IndexEntry,
  type SearchFilters,
} from "@/lib/staticSearch";

function row(over: Partial<PublicIndexRow> & { slug: string }): PublicIndexRow {
  return {
    title_en: "Title",
    summary_en: "Summary",
    primary_vertical: "TECH",
    verticals: ["TECH"],
    pestel: ["T"],
    mega_trend: "artificial_intelligence_and_automation",
    sort_date: "2026-09-01 10:00:00",
    trend_score: 0.7,
    source_name: "Source",
    trend_signal_type: "product_launch",
    source_type: "trade_media",
    ...over,
  };
}

function entry(over: Partial<IndexEntry> & { slug: string }): IndexEntry {
  return {
    title: "Title",
    summary: "Summary",
    verticals: ["TECH"],
    pestel: ["T"],
    mega_trend: null,
    sort_date: "2026-09-01",
    trend_score: 0.7,
    source_name: null,
    source_type: "trade_media",
    signal: null,
    ...over,
  };
}

const F = (over: Partial<SearchFilters> = {}): SearchFilters => ({
  q: "",
  verticals: [],
  pestel: [],
  mega: [],
  signal: [],
  ...over,
});

/* ---------- build side ---------- */

describe("truncateSummary", () => {
  it("leaves short text alone and collapses whitespace", () => {
    expect(truncateSummary("  Two   spaces\nand a line break ")).toBe("Two spaces and a line break");
    expect(truncateSummary(null)).toBe("");
  });

  it("cuts at a word boundary, ends in one ellipsis, never exceeds the limit", () => {
    const long = Array.from({ length: 60 }, (_, i) => `word${i}`).join(" ");
    const cut = truncateSummary(long);
    expect(cut.length).toBeLessThanOrEqual(SUMMARY_MAX);
    expect(cut.endsWith("…")).toBe(true);
    expect(cut).not.toMatch(/\s…$/);
    // the last kept token is a whole word of the input
    const lastWord = cut.slice(0, -1).split(" ").pop()!;
    expect(long.split(" ")).toContain(lastWord);
  });

  it("drops a dangling comma before the ellipsis and hard-cuts a single giant token", () => {
    const text = "Alpha beta gamma delta, " + "x".repeat(200);
    const cut = truncateSummary(text, 40);
    expect(cut.length).toBeLessThanOrEqual(40);
    expect(cut).toBe("Alpha beta gamma delta…");
    // A word boundary that would waste more than half the room loses to a
    // hard cut (one 200-character token after a short lead-in).
    expect(truncateSummary("Ab " + "x".repeat(200), 20)).toBe(`Ab ${"x".repeat(16)}…`);
    expect(truncateSummary("y".repeat(300), 20)).toBe(`${"y".repeat(19)}…`);
  });
});

describe("rowToEntry", () => {
  it("puts the primary vertical first, drops unknown ids, dates to ISO day, folds research", () => {
    const e = rowToEntry(
      row({
        slug: "a-1",
        primary_vertical: "HEALTH",
        verticals: ["TECH", "HEALTH", "BOGUS", "TECH"],
        pestel: '["S","T","X"]',
        sort_date: "2026-08-30 23:59:59.5",
        trend_signal_type: "research",
        source_type: "api",
        mega_trend: "",
        source_name: "",
      })
    );
    expect(e.verticals).toEqual(["HEALTH", "TECH"]);
    expect(e.pestel).toEqual(["S", "T"]);
    expect(e.sort_date).toBe("2026-08-30");
    expect(e.source_type).toBe("research");
    expect(e.signal).toBe("research");
    expect(rowToEntry(row({ slug: "b-2", trend_signal_type: "bogus" })).signal).toBeNull();
    expect(rowToEntry(row({ slug: "c-3", trend_signal_type: "partnership" })).signal).toBe("partnership");
    expect(e.mega_trend).toBeNull();
    expect(e.source_name).toBeNull();
    expect(isoDate("garbage")).toBeNull();
    expect(entryId("some-slug-4711")).toBe(4711);
    expect(entryId("no-id")).toBe(0);
  });
});

describe("buildIndexEntries + serializeIndex", () => {
  const rows = [
    row({ slug: "old-3", sort_date: "2026-08-20 08:00:00" }),
    row({ slug: "new-10", sort_date: "2026-09-01 10:00:00" }),
    row({ slug: "new-9", sort_date: "2026-09-01 10:00:00" }),
    row({ slug: "undated-1", sort_date: null }),
    row({ slug: "new-10", sort_date: "2026-09-01 10:00:00" }), // duplicate
  ];

  it("orders sort_date DESC, id DESC, nulls last, and is independent of input order", () => {
    const a = buildIndexEntries(rows);
    const b = buildIndexEntries([...rows].reverse());
    expect(a.map((e) => e.slug)).toEqual(["new-10", "new-9", "old-3", "undated-1"]);
    expect(serializeIndex(a)).toBe(serializeIndex(b));
  });

  it("serializes one entry per line as valid JSON with no timestamps of its own", () => {
    const out = serializeIndex(buildIndexEntries(rows));
    expect(out.endsWith("]\n")).toBe(true);
    expect(out.split("\n").length - 1).toBe(4); // wc -l == entries
    const parsed = JSON.parse(out) as IndexEntry[];
    expect(parsed).toHaveLength(4);
    expect(Object.keys(parsed[0])).toEqual([
      "slug", "title", "summary", "verticals", "pestel", "mega_trend",
      "sort_date", "trend_score", "source_name", "source_type", "signal",
    ]);
    expect(serializeIndex([])).toBe("[]\n");
  });
});

/* ---------- client side ---------- */

describe("tokenize", () => {
  it("lower-cases, splits on whitespace, de-duplicates, keeps order", () => {
    expect(tokenize("  Battery   storage battery\tEV ")).toEqual(["battery", "storage", "ev"]);
    expect(tokenize("")).toEqual([]);
    expect(tokenize("   ")).toEqual([]);
  });
});

describe("search", () => {
  const entries = [
    entry({ slug: "a-5", title: "Solid-state battery pilot", summary: "EV maker", sort_date: "2026-09-02" }),
    entry({ slug: "b-4", title: "Grid storage", summary: "battery storage for utilities", sort_date: "2026-09-02" }),
    entry({ slug: "c-3", title: "Battery recycling", summary: "circular", sort_date: "2026-08-30", verticals: ["ECO", "TECH"], pestel: ["En"] }),
    entry({ slug: "d-2", title: "Unrelated", summary: "nothing here", sort_date: "2026-08-29" }),
  ];
  const prepared = prepareIndex(entries);

  it("matches case-insensitively as a substring over title + summary", () => {
    const r = search(prepared, F({ q: "BATTERY" }));
    expect(r.total).toBe(3);
    expect(r.hits.map((h) => h.slug)).not.toContain("d-2");
  });

  it("ANDs multiple terms", () => {
    expect(search(prepared, F({ q: "battery storage" })).hits.map((h) => h.slug)).toEqual(["b-4"]);
    expect(search(prepared, F({ q: "battery nowhere" })).total).toBe(0);
  });

  it("ranks title hits before summary hits, then keeps the index order (date desc)", () => {
    expect(search(prepared, F({ q: "battery" })).hits.map((h) => h.slug)).toEqual([
      "a-5", // title, newest
      "c-3", // title, older
      "b-4", // summary only, newest
    ]);
  });

  it("returns everything in index order when there is no query, only chips", () => {
    expect(search(prepared, F({ verticals: ["TECH"] })).hits.map((h) => h.slug)).toEqual([
      "a-5", "b-4", "d-2",
    ]);
  });

  it("caps the hits but counts the total", () => {
    const many = prepareIndex(
      Array.from({ length: MAX_RESULTS + 7 }, (_, i) => entry({ slug: `e-${i}`, title: "hit" }))
    );
    const r = search(many, F({ q: "hit" }));
    expect(r.total).toBe(MAX_RESULTS + 7);
    expect(r.hits).toHaveLength(MAX_RESULTS);
    expect(search(many, F({ q: "hit" }), 5).hits).toHaveLength(5);
  });
});

describe("matchesChips", () => {
  const e = entry({ slug: "x-1", verticals: ["ECO", "TECH"], pestel: ["En", "T"], mega_trend: "circular_economy" });

  it("ORs within a dimension, ANDs across dimensions", () => {
    expect(matchesChips(e, F({ verticals: ["FOOD", "ECO"] }))).toBe(true);
    expect(matchesChips(e, F({ pestel: ["P", "T"] }))).toBe(true);
    expect(matchesChips(e, F({ verticals: ["ECO"], pestel: ["P"] }))).toBe(false);
    expect(matchesChips(e, F({ verticals: ["ECO"], pestel: ["En"], mega: ["circular_economy"] }))).toBe(true);
    expect(matchesChips(e, F({ mega: ["other"] }))).toBe(false);
  });

  it("matches the vertical chip on the PRIMARY vertical only (like /trends/v/<v>)", () => {
    expect(matchesChips(e, F({ verticals: ["TECH"] }))).toBe(false);
    expect(matchesChips(entry({ slug: "n-1", mega_trend: null }), F({ mega: ["any"] }))).toBe(false);
  });
});

describe("megaOptions", () => {
  it("counts keys, sorts by count then key, labels via the taxonomy, caps at the limit", () => {
    const entries = [
      entry({ slug: "1-1", mega_trend: "circular_economy" }),
      entry({ slug: "2-2", mega_trend: "artificial_intelligence_and_automation" }),
      entry({ slug: "3-3", mega_trend: "circular_economy" }),
      entry({ slug: "4-4", mega_trend: "zz_unknown_key" }),
      entry({ slug: "5-5", mega_trend: null }),
    ];
    const opts = megaOptions(entries);
    expect(opts.map((o) => o.key)).toEqual([
      "circular_economy",
      "artificial_intelligence_and_automation",
      "zz_unknown_key",
    ]);
    expect(opts[0].count).toBe(2);
    expect(opts[1].name).toBe("Artificial Intelligence & Automation");
    expect(opts[2].name).toBe("Zz Unknown Key");
    expect(megaOptions(entries, 1)).toHaveLength(1);
  });
});

describe("isActive + hash round trip", () => {
  it("treats the page's own vertical as inactive and everything else as active", () => {
    const defaults = F({ verticals: ["TECH"] });
    expect(isActive(F({ verticals: ["TECH"] }), defaults)).toBe(false);
    expect(isActive(F({ verticals: [] }), defaults)).toBe(true);
    expect(isActive(F({ q: "  " }))).toBe(false);
    expect(isActive(F({ q: "x" }))).toBe(true);
    expect(isActive(F({ pestel: ["S"] }))).toBe(true);
  });

  it("serializes and parses the state, dropping unknown ids", () => {
    const f = F({ q: "solar roof", verticals: ["ECO", "TECH"], pestel: ["En"], mega: ["circular_economy"] });
    const hash = buildSearchHash(f);
    expect(hash).toBe("#q=solar+roof&v=ECO%2CTECH&pestel=En&mega=circular_economy");
    expect(parseSearchHash(hash)).toEqual(f);
    expect(parseSearchHash("#v=NOPE,FOOD&pestel=Q&mega=Bad-Key")).toEqual(F({ verticals: ["FOOD"] }));
    expect(parseSearchHash("#v=NOPE")).toBeNull();
    expect(parseSearchHash("")).toBeNull();
    expect(buildSearchHash(F())).toBe("");
  });
});

describe("entryToTrend", () => {
  it("builds what TrendCard needs: id from the slug, primary vertical, local-noon date, labels", () => {
    const t = entryToTrend(
      entry({
        slug: "quantum-chip-123",
        verticals: ["TECH", "BIZ"],
        source_type: "research",
        source_name: "arXiv",
        trend_score: 0.81,
      })
    );
    expect(t.id).toBe(123);
    expect(t.slug).toBe("quantum-chip-123");
    expect(t.primary_vertical).toBe("TECH");
    expect(t.verticals).toEqual(["TECH", "BIZ"]);
    expect(t.source_date).toBe("2026-09-01T12:00:00");
    expect(t.trend_signal_type).toBe("research");
    expect(t.source_type).toBeNull();
    expect(t.status).toBe("published");
    expect(entryToTrend(entry({ slug: "p-1", source_type: "press_wire" })).source_type).toBe("press_wire");
  });
});

describe("signal type (#110)", () => {
  it("filters by chip, round-trips through the hash, drops unknown ids, and reaches the card", () => {
    const a = rowToEntry(row({ slug: "a-1", trend_signal_type: "regulation", source_type: "trade_media" }));
    const b = rowToEntry(row({ slug: "b-2", trend_signal_type: "market_shift", source_type: "trade_media" }));
    const c = rowToEntry(row({ slug: "c-3", trend_signal_type: null, source_type: "trade_media" }));
    expect(matchesChips(a, F({ signal: ["regulation"] }))).toBe(true);
    expect(matchesChips(b, F({ signal: ["regulation"] }))).toBe(false);
    expect(matchesChips(c, F({ signal: ["regulation"] }))).toBe(false);
    expect(matchesChips(c, F())).toBe(true);
    expect(isActive(F({ signal: ["regulation"] }))).toBe(true);
    const hash = buildSearchHash(F({ signal: ["regulation", "partnership"] }));
    expect(hash).toBe("#signal=regulation%2Cpartnership");
    expect(parseSearchHash(hash)?.signal).toEqual(["regulation", "partnership"]);
    expect(parseSearchHash("#signal=bogus,regulation,regulation")?.signal).toEqual(["regulation"]);
    expect(entryToTrend(a).trend_signal_type).toBe("regulation");
    expect(entryToTrend(c).trend_signal_type).toBe("market_shift");
  });
});
