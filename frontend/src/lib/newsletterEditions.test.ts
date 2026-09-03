import { describe, it, expect } from "vitest";
import {
  editionSlug,
  editionPath,
  parseEditionSlug,
  isoWeekMonday,
  isoWeekMondayIso,
  isoWeekRangeLabel,
  articleSlugOf,
  resolveEditionHref,
  rewriteMarkdownLinks,
  collectEditionSlugs,
  editionSources,
  rewriteEditionForExport,
  editionNeighbours,
  editionExcerpt,
  type NewsletterEdition,
} from "@/lib/newsletterEditions";

describe("edition URL scheme", () => {
  it("formats zero-padded week slugs and round-trips them", () => {
    expect(editionSlug(2026, 35)).toBe("2026-w35");
    expect(editionSlug(2026, 5)).toBe("2026-w05");
    expect(editionPath(2026, 5)).toBe("/trends/newsletter/2026-w05");
    expect(parseEditionSlug("2026-w35")).toEqual({ year: 2026, week: 35 });
    expect(parseEditionSlug("2026-w05")).toEqual({ year: 2026, week: 5 });
  });

  it("accepts exactly one form per edition", () => {
    for (const bad of ["2026-w5", "2026-W35", "2026-35", "w35", "2026-w00", "2026-w54", "1999-w01", ""]) {
      expect(parseEditionSlug(bad), bad).toBeNull();
    }
  });
});

describe("ISO week dates", () => {
  it("finds the Monday of an ISO week without a clock", () => {
    expect(isoWeekMondayIso(2026, 35)).toBe("2026-08-24");
    expect(isoWeekMondayIso(2026, 1)).toBe("2025-12-29");
    expect(isoWeekMondayIso(2025, 1)).toBe("2024-12-30");
    expect(isoWeekMondayIso(2027, 1)).toBe("2027-01-04");
    expect(isoWeekMonday(2026, 35).getUTCDay()).toBe(1);
  });

  it("labels a week as a date range", () => {
    expect(isoWeekRangeLabel(2026, 35)).toBe("24–30 Aug 2026");
    expect(isoWeekRangeLabel(2026, 40)).toBe("28 Sep – 4 Oct 2026");
    expect(isoWeekRangeLabel(2026, 1)).toBe("29 Dec 2025 – 4 Jan 2026");
  });
});

const ctx = {
  inWindow: new Set(["fresh-signal-123"]),
  sourceBySlug: new Map([
    ["old-signal-42", "https://example.org/report"],
    ["evil-signal-7", "javascript:alert(1)"],
  ]),
};

describe("article link rule", () => {
  it("recognises article hrefs and leaves hubs alone", () => {
    expect(articleSlugOf("/trends/fresh-signal-123")).toBe("fresh-signal-123");
    expect(articleSlugOf("/trends/mega")).toBeNull();
    expect(articleSlugOf("/trends/newsletter")).toBeNull();
    expect(articleSlugOf("/trends")).toBeNull();
    expect(articleSlugOf("https://example.org/x-1")).toBeNull();
    expect(articleSlugOf("/trends/fresh-signal-123/extra")).toBeNull();
  });

  it("keeps in-window articles internal, re-points the rest to the source, else drops the link", () => {
    expect(resolveEditionHref("/trends/fresh-signal-123", ctx)).toBe("/trends/fresh-signal-123");
    expect(resolveEditionHref("/trends/old-signal-42", ctx)).toBe("https://example.org/report");
    expect(resolveEditionHref("/trends/gone-signal-99", ctx)).toBeNull();
    // An unsafe source is as good as none (safeHref).
    expect(resolveEditionHref("/trends/evil-signal-7", ctx)).toBeNull();
    // Non-article hrefs pass through untouched.
    expect(resolveEditionHref("/trends/mega", ctx)).toBe("/trends/mega");
    expect(resolveEditionHref("https://example.org/", ctx)).toBe("https://example.org/");
  });

  it("rewrites markdown links in text", () => {
    const text =
      "[AI](/trends/mega) meets [Fresh](/trends/fresh-signal-123), [Old](/trends/old-signal-42) and [Gone](/trends/gone-signal-99).";
    expect(rewriteMarkdownLinks(text, ctx)).toBe(
      "[AI](/trends/mega) meets [Fresh](/trends/fresh-signal-123), [Old](https://example.org/report) and Gone."
    );
  });
});

const edition: NewsletterEdition = {
  id: 1,
  year: 2026,
  week: 35,
  editorial: "Lead: [Fresh](/trends/fresh-signal-123) and [Gone](/trends/gone-signal-99).",
  vertical_summaries: { TECH: "See [Old](/trends/old-signal-42).", FOOD: "Nothing linked." },
  mega_trend_radar: [],
  trend_refs: {
    TECH: [
      { title: "Fresh", slug: "fresh-signal-123", source_name: "A" },
      { title: "Old", slug: "old-signal-42", source_name: "B", source_url: "https://example.org/report" },
      { title: "Gone", slug: "gone-signal-99", source_name: "C" },
    ],
  },
  total_signals: 3,
  created_at: "2026-08-31 09:00:19",
};

describe("edition rewrite for the export", () => {
  it("collects every article slug the edition refers to, sorted", () => {
    expect(collectEditionSlugs(edition)).toEqual(["fresh-signal-123", "gone-signal-99", "old-signal-42"]);
    expect([...editionSources(edition)]).toEqual([["old-signal-42", "https://example.org/report"]]);
  });

  it("rewrites text and resolves trend_refs hrefs, leaving the input untouched", () => {
    const out = rewriteEditionForExport(edition, ctx);
    expect(out.editorial).toBe("Lead: [Fresh](/trends/fresh-signal-123) and Gone.");
    expect(out.vertical_summaries.TECH).toBe("See [Old](https://example.org/report).");
    expect(out.vertical_summaries.FOOD).toBe("Nothing linked.");
    expect(out.trend_refs.TECH.map((r) => r.href)).toEqual([
      "/trends/fresh-signal-123",
      "https://example.org/report",
      null,
    ]);
    expect(edition.trend_refs.TECH[0].href).toBeUndefined();
    expect(edition.editorial).toContain("[Gone](/trends/gone-signal-99)");
  });

  it("is idempotent (a second pass changes nothing)", () => {
    const once = rewriteEditionForExport(edition, ctx);
    expect(rewriteEditionForExport(once, ctx)).toEqual(once);
  });
});

describe("edition neighbours", () => {
  const archive = [
    { year: 2026, week: 35 },
    { year: 2026, week: 34 },
    { year: 2026, week: 33 },
  ];
  it("previous = older, next = newer, in a newest-first list", () => {
    expect(editionNeighbours(archive, 2026, 34)).toEqual({
      previous: { year: 2026, week: 33 },
      next: { year: 2026, week: 35 },
    });
    expect(editionNeighbours(archive, 2026, 35).next).toBeNull();
    expect(editionNeighbours(archive, 2026, 33).previous).toBeNull();
    expect(editionNeighbours(archive, 2025, 1)).toEqual({ previous: null, next: null });
  });
});

describe("edition excerpt", () => {
  it("takes the first paragraph without markdown links, capped at 160 chars", () => {
    expect(editionExcerpt("Lead: [Fresh](/trends/fresh-signal-123) rises.\n\nSecond paragraph.")).toBe(
      "Lead: Fresh rises."
    );
    const long = `${"word ".repeat(60).trim()}\n\nmore`;
    const out = editionExcerpt(long);
    expect(out.length).toBeLessThanOrEqual(160);
    expect(out.endsWith("…")).toBe(true);
    expect(editionExcerpt(null)).toBe("");
  });
});
