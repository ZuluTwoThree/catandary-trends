import { describe, it, expect } from "vitest";
import {
  pulseWeekSlug, parsePulseWeek, isoWeekOf, lastCompletedWeek, pulsePath, cliWeek,
  weekMondayIso, volumeRatio, ratioTone, ratioLabel, growthLabel, firstSentence,
  sparkBars, type PulseStats,
} from "@/lib/researchPulse";

describe("week scheme", () => {
  it("shares the newsletter slug form and accepts the CLI spelling", () => {
    expect(pulseWeekSlug(2026, 35)).toBe("2026-w35");
    expect(pulseWeekSlug(2026, 5)).toBe("2026-w05");
    expect(parsePulseWeek("2026-w35")).toEqual({ year: 2026, week: 35 });
    expect(parsePulseWeek("2026-W35")).toEqual({ year: 2026, week: 35 });
    expect(parsePulseWeek("2026-35")).toBeNull();
    expect(parsePulseWeek(undefined)).toBeNull();
    expect(cliWeek({ year: 2026, week: 5 })).toBe("2026-W05");
  });

  it("computes ISO weeks incl. year boundaries", () => {
    expect(isoWeekOf(new Date(Date.UTC(2026, 7, 27)))).toEqual({ year: 2026, week: 35 });
    expect(isoWeekOf(new Date(Date.UTC(2026, 7, 24)))).toEqual({ year: 2026, week: 35 }); // Monday
    expect(isoWeekOf(new Date(Date.UTC(2026, 7, 30)))).toEqual({ year: 2026, week: 35 }); // Sunday
    expect(isoWeekOf(new Date(Date.UTC(2026, 0, 1)))).toEqual({ year: 2026, week: 1 });
    expect(isoWeekOf(new Date(Date.UTC(2025, 11, 29)))).toEqual({ year: 2026, week: 1 });
    expect(isoWeekOf(new Date(Date.UTC(2027, 0, 1)))).toEqual({ year: 2026, week: 53 });
  });

  it("defaults to the last completed week (same rule as the CLI)", () => {
    expect(lastCompletedWeek(new Date(Date.UTC(2026, 8, 5)))).toEqual({ year: 2026, week: 35 });
    expect(lastCompletedWeek(new Date(Date.UTC(2026, 7, 31)))).toEqual({ year: 2026, week: 35 });
    expect(lastCompletedWeek(new Date(Date.UTC(2026, 0, 4)))).toEqual({ year: 2025, week: 52 });
  });

  it("builds paths and Monday dates", () => {
    expect(pulsePath()).toBe("/trends/foresight/research/pulse");
    expect(pulsePath(undefined, { year: 2026, week: 35 })).toBe("/trends/foresight/research/pulse?week=2026-w35");
    expect(pulsePath("clean_energy_transition", { year: 2026, week: 3 }))
      .toBe("/trends/foresight/research/pulse/clean_energy_transition?week=2026-w03");
    expect(weekMondayIso({ year: 2026, week: 35 })).toBe("2026-08-24");
  });
});

describe("volume ratio", () => {
  it("uses the median of the prior weeks and refuses a zero baseline", () => {
    expect(volumeRatio(120, [100, 90, 110, 400])).toBeCloseTo(120 / 105, 3);
    expect(volumeRatio(1267, [1799, 1748, 1749, 400])).toBeCloseTo(1267 / 1748.5, 3);
    expect(volumeRatio(50, [0, 0, 0, 0])).toBeNull();
    expect(volumeRatio(50, [])).toBeNull();
    expect(volumeRatio(0, [10, 10])).toBe(0);
  });

  it("labels tone with a ±5 % noise band", () => {
    expect(ratioTone(1.09)).toBe("up");
    expect(ratioTone(0.646)).toBe("down");
    expect(ratioTone(1.02)).toBe("flat");
    expect(ratioTone(0.96)).toBe("flat");
    expect(ratioTone(null)).toBe("none");
    expect(ratioLabel(1.09)).toBe("+9 %");
    expect(ratioLabel(0.646)).toBe("−35 %");
    expect(ratioLabel(1.02)).toBe("≈ level");
    expect(ratioLabel(null)).toBe("no baseline");
    expect(ratioLabel(2.4)).toBe("+140 %");
  });

  it("labels cluster growth", () => {
    expect(growthLabel(1.31)).toBe("×1.3");
    expect(growthLabel(22.72)).toBe("×23");
    expect(growthLabel(null)).toBe("no baseline");
  });
});

describe("text helpers", () => {
  it("takes the first sentence without breaking on decimals", () => {
    const t = "Research volume reached 5084 papers, a 9% increase over the prior median of 4663.5. The largest cluster focused on LLMs.";
    expect(firstSentence(t)).toBe("Research volume reached 5084 papers, a 9% increase over the prior median of 4663.5.");
    expect(firstSentence("One sentence only")).toBe("One sentence only");
    expect(firstSentence(null)).toBe("");
    const long = `${"word ".repeat(60)}end. Next.`;
    const s = firstSentence(long, 50);
    expect(s.length).toBeLessThanOrEqual(50);
    expect(s.endsWith("…")).toBe(true);
  });

  it("builds sparkline bars scaled to the max week", () => {
    const stats: PulseStats = {
      window: { start: "2026-08-24", end: "2026-08-30" }, week_n: 50, embedded_n: 50,
      prior_weeks: [{ year: 2026, week: 31, n: 100 }, { year: 2026, week: 32, n: 0 }],
      prior_median: 50, ratio: 1, sources: {}, top_sources: [], top_concepts: [], oa_n: 0, k: 5,
    };
    const bars = sparkBars(stats);
    expect(bars.map((b) => b.h)).toEqual([1, 0, 0.5]);
    expect(bars[2]).toMatchObject({ label: "now", current: true, n: 50 });
  });
});
