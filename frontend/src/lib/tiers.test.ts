import { describe, it, expect } from "vitest";
import type { Tier } from "@/lib/auth"; // type-only: does not pull auth.ts at runtime
import { TIERS, HYPERCARE, tierAllows, tierLabel } from "@/lib/tiers";

const ALL_TIERS: Tier[] = ["free", "starter", "pro", "superpro"];

describe("tierAllows — full have × need matrix", () => {
  // Explicit expectations (not derived from the rank map under test): a tier
  // satisfies itself and everything below it, never anything above it.
  const MATRIX: Array<[have: Tier, need: Tier, allowed: boolean]> = [
    ["free", "free", true],
    ["free", "starter", false],
    ["free", "pro", false],
    ["free", "superpro", false],
    ["starter", "free", true],
    ["starter", "starter", true],
    ["starter", "pro", false],
    ["starter", "superpro", false],
    ["pro", "free", true],
    ["pro", "starter", true],
    ["pro", "pro", true],
    ["pro", "superpro", false],
    ["superpro", "free", true],
    ["superpro", "starter", true],
    ["superpro", "pro", true],
    ["superpro", "superpro", true],
  ];

  it("covers every pair exactly once", () => {
    expect(MATRIX).toHaveLength(ALL_TIERS.length * ALL_TIERS.length);
    const seen = new Set(MATRIX.map(([h, n]) => `${h}>${n}`));
    expect(seen.size).toBe(MATRIX.length);
  });

  it.each(MATRIX)("tierAllows(%s, %s) === %s", (have, need, allowed) => {
    expect(tierAllows(have, need)).toBe(allowed);
  });
});

describe("tierLabel", () => {
  it.each([
    ["free", "Free"],
    ["starter", "Starter"],
    ["pro", "Pro"],
    ["superpro", "Super Pro+"],
  ] as Array<[Tier, string]>)("labels %s as %s", (tier, label) => {
    expect(tierLabel(tier)).toBe(label);
  });

  it('falls back to "Free" for an unknown tier value', () => {
    // Runtime values can drift from the compile-time union (stale cookie/DB row).
    expect(tierLabel("enterprise" as Tier)).toBe("Free");
  });
});

describe("TIERS invariants", () => {
  it("contains all four tiers with unique ids", () => {
    expect(TIERS.map((t) => t.id)).toEqual(ALL_TIERS);
  });

  it("ranks are strictly ascending", () => {
    for (let i = 1; i < TIERS.length; i++) {
      expect(TIERS[i].rank).toBeGreaterThan(TIERS[i - 1].rank);
    }
  });

  it("every tier has a non-empty feature list with non-blank entries", () => {
    for (const tier of TIERS) {
      expect(tier.features.length).toBeGreaterThan(0);
      for (const feature of tier.features) {
        expect(feature.trim().length).toBeGreaterThan(0);
      }
    }
  });

  it("every tier has a price hint and label", () => {
    for (const tier of TIERS) {
      expect(tier.priceHint.trim().length).toBeGreaterThan(0);
      expect(tier.label.trim().length).toBeGreaterThan(0);
    }
  });

  it('never advertises "Saved searches" (honesty rule regression)', () => {
    // The feature does not exist in the product; it must not reappear in any
    // tier copy (labels, blurbs, features, price hints) — including Hypercare.
    const allCopy = JSON.stringify([TIERS, HYPERCARE]);
    expect(allCopy).not.toMatch(/saved search/i);
  });
});
