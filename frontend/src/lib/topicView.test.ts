import { describe, expect, it } from "vitest";
import { curveFor, monthAxis, monthsBetween, tierStripe, weaknesses } from "./topicView";
import type { TopicReport, TopicTier } from "./topicReport";

const tier = (over: Partial<TopicTier>): TopicTier => ({
  status: "ok", head: 0.8, head_min: 0.68, cut: 0.72, found: 400, hits: 40, capped: false, index: "tier",
  hits_damped: 40, sources: 6, top_source: "A", top_source_share: 0.3, series: [], first_hit: null,
  oldest: [], newest: [], sample: [], tagged_share: 0.9, ...over,
});

const report = (tiers: TopicReport["tiers"]): TopicReport =>
  ({
    query: "q", query_norm: "q", tiers_key: "science,market", tiers_requested: ["science", "market"],
    status: "ok", ambiguity: null,
    params: { head_min: {}, drop: 0.08, floor: 0.62, neighbours: 1000, walk_gate: 0.72, exact: false },
    corpus: { first_month: "1983-01", last_month: "2026-08", months: 100, computed_at: null },
    tiers, overall: { first_month: null, age_months: null, hits_total: 0, hits_recent: 0, novelty_lift: null,
      accel: null, established_share: 0.9, tier_order: [], science_to_market_months: null,
      actors_early: 0, actors_late: 0, actor_growth: null },
    fulltext_oldest: [], vocabulary: [], generated_at: "2026-09-17T00:00:00",
  }) as TopicReport;

describe("month axis and curves", () => {
  it("counts months and builds an axis across a year boundary", () => {
    expect(monthsBetween("2020-01", "2023-08")).toBe(43);
    expect(monthAxis("2026-02", 4)).toEqual(["2025-11", "2025-12", "2026-01", "2026-02"]);
  });
  it("places sparse series on the axis with zeros elsewhere", () => {
    const r = report({ market: tier({ series: [["2026-07", 3], ["2020-01", 9]] }) });
    const c = curveFor(r, "market", 3);
    expect(c.months).toEqual(["2026-06", "2026-07", "2026-08"]);
    expect(c.points).toEqual([0, 3, 0]);
  });
});

describe("tier stripe", () => {
  it("orders conversations by their sustained month and states the gaps", () => {
    const r = report({
      science: tier({ first_hit: "1996-04", first_month: "2020-01" }),
      market: tier({ first_hit: "2020-05", first_month: "2023-08" }),
      patent: tier({ status: "none", hits: 0 }),
    });
    const s = tierStripe(r);
    expect(s.map((x) => x.tier)).toEqual(["science", "market"]);
    expect(s[1].gap).toBe(43);
  });
  it("a tier with hits but no sustained month is placed by its first hit", () => {
    const r = report({
      science: tier({ first_hit: "2010-01", first_month: "2015-01" }),
      funding: tier({ status: "thin", hits: 3, first_hit: "2012-06", first_month: null }),
    });
    const s = tierStripe(r);
    expect(s.map((x) => x.tier)).toEqual(["funding", "science"]);
    expect(s[1].gap).toBe(31);
  });
});

describe("weaknesses", () => {
  it("names thin, capped, concentration, damping and new-source problems", () => {
    const w = weaknesses(
      tier({ status: "thin", hits: 6, capped: true, found: 1000, top_source_share: 0.7, hits_damped: 1, tagged_share: 0.1 }),
      0.2
    ).map((x) => x.key);
    expect(w).toEqual(["thin", "capped", "concentration", "damped", "untagged", "new-sources"]);
  });
  it("is empty for a healthy tier", () => {
    expect(weaknesses(tier({}), 0.9)).toEqual([]);
  });
});
