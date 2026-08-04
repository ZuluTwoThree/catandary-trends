/**
 * Parity tests for the TypeScript grounding port (issue #71).
 *
 * These use the SAME fixtures as tests/test_grounding.py — if the two
 * implementations ever drift, one of these fails.
 */
import { describe, it, expect } from "vitest";
import { ungroundedSpecifics, sourceFromParts } from "@/lib/grounding";

describe("ungroundedSpecifics — parity with pipeline/grounding.py", () => {
  it("flags an invented year and number", () => {
    const src = "The Ministry published a circular economy strategy to cut waste.";
    const body = "The strategy sets a 2027 deadline affecting 10,000 suppliers.";
    const flagged = new Set(ungroundedSpecifics(body, src));
    expect(flagged.has("2027")).toBe(true);
    expect(flagged.has("10,000")).toBe(true);
  });

  it("passes grounded numbers", () => {
    const src = "The programme created 7,980 jobs across 36 firms in 2024.";
    const body = "It created 7,980 jobs across 36 firms, per the 2024 review.";
    expect(ungroundedSpecifics(body, src)).toEqual([]);
  });

  it("treats German and English number formats as equal", () => {
    // '8.192' == '8,192' and '29,5' == '29.5' — ~half our sources are German,
    // so a format-blind check would flag correct figures.
    const src = "Bastler baut GPU mit 8.192 Chips; DE-CIX misst 29,5 TBit/s.";
    const body = "A GPU with 8,192 chips; the exchange measured 29.5 Tbit/s.";
    expect(ungroundedSpecifics(body, src)).toEqual([]);
  });

  it("handles empty input", () => {
    expect(ungroundedSpecifics("", "anything")).toEqual([]);
    expect(ungroundedSpecifics("no numbers here", "")).toEqual([]);
  });

  it("reproduces the real Intel hold from 2026-08-03", () => {
    // Held live: body claims '€5' billion, the RSS teaser never states it.
    const src = "Intel expands its Irish semiconductor operations.";
    const body = "Intel allocates €5 billion to expand Irish semiconductor capacity.";
    expect(ungroundedSpecifics(body, src).length).toBeGreaterThan(0);
  });
});

describe("sourceFromParts", () => {
  it("joins title, excerpt and token lists", () => {
    const s = sourceFromParts("Title 2027", "excerpt text", ["a claim"], ["7,980 jobs"], ["by Q3 2025"]);
    for (const token of ["Title 2027", "excerpt text", "a claim", "7,980 jobs", "by Q3 2025"]) {
      expect(s).toContain(token);
    }
  });

  it("tolerates nulls without injecting 'null'", () => {
    const s = sourceFromParts(null, null, null, [], ["2030"]);
    expect(s).not.toContain("null");
    expect(s).toContain("2030");
  });

  it("grounds a figure that only the full text contains", () => {
    // The false-hold class #11 fixed: RSS teaser omits the figure, the
    // extracted specifics carry it.
    const rss = "The ministry announced a new circular economy strategy.";
    const body = "The 2027 strategy will affect 10,000 suppliers.";
    const narrow = sourceFromParts("Circular strategy", rss);
    expect(ungroundedSpecifics(body, narrow).sort()).toEqual(["10,000", "2027"]);
    const wide = sourceFromParts("Circular strategy", rss, [], ["10,000 suppliers"], ["2027"]);
    expect(ungroundedSpecifics(body, wide)).toEqual([]);
  });
});

describe("CJK sources (regression 2026-08-04)", () => {
  it("sees a figure stated in a Japanese source", () => {
    // \b finds no boundary between a digit and a CJK character, so the number
    // was invisible and the body's correct figure was flagged as fabricated.
    expect(
      ungroundedSpecifics("covering 140 currencies across 180 countries.", "140以上の通貨、180以上の国・地域をカバーし")
    ).toEqual([]);
  });

  it("does not mangle a Korean grouped number into '2,'", () => {
    expect(ungroundedSpecifics("The bank serves 2,900 万 customers.", "약 2,900만 명의 고객을 보유")).not.toContain("2,");
  });
});

describe("quantities the source spells out in words (2026-08-04)", () => {
  it("grounds a numeral against the word form, EN and DE", () => {
    expect(ungroundedSpecifics("50% of melanoma cases", "Around half of melanomas carry a mutation")).toEqual([]);
    expect(ungroundedSpecifics("over 50% of all new uploads", "mehr als die Hälfte neu hochgeladener Songs")).toEqual([]);
    expect(ungroundedSpecifics("cut demand by 25%", "um ein Viertel senken")).toEqual([]);
    expect(ungroundedSpecifics("20% of the cohort", "one in five face lasting struggles")).toEqual([]);
  });

  it("scales a fraction against a magnitude word", () => {
    expect(ungroundedSpecifics("a $500 billion bill", "New York Faces Half a Trillion in Costs")).toEqual([]);
    expect(ungroundedSpecifics("committing €500 million", "Nestlé investiert halbe Milliarde")).toEqual([]);
  });

  it("still catches inventions — a word quantity is not a blanket pass", () => {
    // "half" implies 50; it must not wave through an invented 150.
    expect(ungroundedSpecifics("strongest in 150 years", "on track to be the strongest on record")).toEqual(["150"]);
    // an implied digit must never ground a larger figure by substring
    expect(ungroundedSpecifics("a 500,000 unit shortfall", "named five priorities")).toEqual(["500,000"]);
    expect(ungroundedSpecifics("benefited 80% of patients", "Most patients benefited, many reported fewer symptoms")).toEqual(["80%"]);
  });
});
