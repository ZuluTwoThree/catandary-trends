import { describe, expect, it } from "vitest";
import {
  accelText,
  ageIsMeaningful,
  ageText,
  caveats,
  historyTail,
  isYoung,
  noveltyText,
  actorText,
  dominantTier,
  groupNests,
  calendarFirst,
  calendarQuery,
  calendarSpark,
  leadText,
  nestTitle,
  runProvenance,
  tierSteps,
} from "./nestCard";
import type { EmergingNest, EmergingRun } from "./emerging";

function nest(over: Partial<EmergingNest> = {}): EmergingNest {
  return {
    id: 1,
    label: "Retrieval Augmented Generation · Natural Language Processing",
    llm_label: null,
    llm_label_note: null,
    size: 251,
    cohesion: 0.78,
    n_sources: 15,
    top_source: "arXiv Preprints",
    top_source_share: 0.31,
    tagged_share: 0.11,
    established_share: 0.85,
    verticals: ["TECH"],
    top_tags: ["rag"],
    new_terms: ["retrieval augmented generation"],
    first_month: "2025-12",
    age_months: 10,
    hits_total: 400,
    hits_recent: 330,
    novelty_lift: 4.17,
    accel: 2.4,
    history_months: ["2025-01", "2025-02", "2025-03"],
    history_hits: [0, 2, 40],
    tiers: {},
    tier_order: [],
    science_to_market_months: null,
    actors_early: 0,
    actors_late: 0,
    group_id: null,
    group_label: null,
    calendar: null,
    reps: [],
    ...over,
  };
}

function run(over: Partial<EmergingRun> = {}): EmergingRun {
  return {
    id: 3,
    scope: "global",
    since: "2026-06-17",
    window_days: 90,
    signals: 38000,
    cells: 784,
    nests: 83,
    scanned: 1749202,
    first_month: "1983-01",
    last_month: "2026-09",
    created_at: "2026-09-15",
    params: null,
    ...over,
  };
}

describe("emerging cards — age is the headline, weaknesses are printed", () => {
  it("states the age in months while it is still young, then the date", () => {
    expect(ageText(nest())).toBe("first seen 10 months ago");
    expect(ageText(nest({ age_months: 1 }))).toBe("first seen 1 month ago");
    expect(ageText(nest({ age_months: 309, first_month: "2001-01" }))).toBe("first seen 2001-01");
    expect(ageText(nest({ age_months: null, first_month: null }))).toBe("no datable history");
  });

  it("marks a pocket young only up to 18 months", () => {
    expect(isYoung(nest({ age_months: 18 }))).toBe(true);
    expect(isYoung(nest({ age_months: 19 }))).toBe(false);
    expect(isYoung(nest({ age_months: null }))).toBe(false);
  });

  it("does not call a pocket young when its sources are the new thing", () => {
    expect(isYoung(nest({ age_months: 3, established_share: 0.1 }))).toBe(false);
    expect(ageIsMeaningful(nest({ established_share: 0.1 }))).toBe(false);
    const c = caveats(nest({ established_share: 0.1 }));
    expect(c[0].key).toBe("young-sources");
    expect(c[0].text).toContain("about our intake");
  });

  it("puts the saturating novelty lift into words", () => {
    expect(noveltyText(nest({ novelty_lift: 4.5 }))).toContain("every trace");
    expect(noveltyText(nest({ novelty_lift: 2.4 }))).toContain("2.4x more concentrated");
    expect(noveltyText(nest({ novelty_lift: 1.0 }))).toContain("like everything else");
    expect(noveltyText(nest({ novelty_lift: null }))).toContain("Not enough history");
  });

  it("says plainly when there is no earlier evidence to compare against", () => {
    expect(accelText(nest({ accel: null }))).toContain("No earlier evidence");
    expect(accelText(nest({ accel: 2.4 }))).toContain("2.4x its own earlier rate");
    expect(accelText(nest({ accel: 1.1 }))).toBeNull();
  });

  it("names a single-source pocket as the weakness it is", () => {
    const c = caveats(nest({ n_sources: 1 }));
    expect(c[0].key).toBe("sources");
    expect(c[0].text).toContain("not corroboration");
  });

  it("flags a pocket that no stage of the pipeline ever classified", () => {
    const keys = caveats(nest({ tagged_share: 0 })).map((c) => c.key);
    expect(keys).toContain("unclassified");
  });

  it("flags concentration only when the source count looks broad enough to mislead", () => {
    const keys = caveats(nest({ n_sources: 12, top_source_share: 0.6 })).map((c) => c.key);
    expect(keys).toContain("concentration");
    expect(caveats(nest()).map((c) => c.key)).not.toContain("concentration");
  });

  it("has nothing to warn about for a broad, classified, sizeable pocket", () => {
    expect(
      caveats(nest({ tagged_share: 0.8, n_sources: 20, top_source_share: 0.2, established_share: 0.9 }))
    ).toEqual([]);
  });

  it("shows the model name with the measured label underneath", () => {
    expect(nestTitle(nest({ llm_label: "Retrieval Augmented Generation" }))).toEqual({
      name: "Retrieval Augmented Generation",
      sub: "Retrieval Augmented Generation · Natural Language Processing",
    });
  });

  it("shows the tag label alone when no name survived the check", () => {
    const t = nestTitle(nest({ llm_label: null }));
    expect(t.name).toBe("Retrieval Augmented Generation · Natural Language Processing");
    expect(t.sub).toBeNull();
  });

  it("names which conversation the pocket is, and when the others started", () => {
    const n = nest({
      tiers: {
        science: { first_month: "2020-08", age_months: 74, hits: 884, hits_recent: 300, share_of_nest: 0.96 },
        market: { first_month: "2026-06", age_months: 4, hits: 30, hits_recent: 30, share_of_nest: 0.04 },
      },
      tier_order: ["science", "market"],
      science_to_market_months: 70,
    });
    expect(tierSteps(n).map((s) => `${s.label} ${s.first_month}`)).toEqual([
      "research 2020-08",
      "market 2026-06",
    ]);
    expect(dominantTier(n)).toBe("science");
    expect(leadText(n)).toBe("Research led the market by 70 months.");
  });

  it("says plainly when the market got there first", () => {
    expect(leadText(nest({ science_to_market_months: -3 }))).toBe(
      "The market got there 3 months before the research did."
    );
    expect(leadText(nest({ science_to_market_months: null }))).toBeNull();
  });

  it("calls no tier dominant when the pocket is genuinely mixed", () => {
    const mixed = nest({
      tiers: {
        science: { first_month: "2024-01", age_months: 20, hits: 10, hits_recent: 5, share_of_nest: 0.4 },
        market: { first_month: "2024-06", age_months: 15, hits: 10, hits_recent: 5, share_of_nest: 0.4 },
      },
      tier_order: ["science", "market"],
    });
    expect(dominantTier(mixed)).toBeNull();
  });

  it("reports named companies as a floor, never as a census", () => {
    const t = actorText(nest({ actors_early: 4, actors_late: 20 }));
    expect(t).toContain("4 two years ago, 20 now");
    expect(t).toContain("floor");
    expect(actorText(nest({ actors_late: 0 }))).toBeNull();
  });

  it("states what the run did", () => {
    expect(runProvenance(run())).toBe(
      "83 pockets found by cutting the last 90 days into 784 cells and keeping only the tight ones. " +
        "Each was then dated against all 1,749,202 archived signals, back to 1983-01."
    );
  });

  it("names the history sample the run was dated against", () => {
    expect(runProvenance(run({ params: { history_sample: 1_104_000 } }))).toContain(
      "1,749,202 archived signals plus a sample of 1,104,000 past patents (from 1990) and research works (from 2010), back to"
    );
  });

  it("draws only the tail of a 40-year history", () => {
    const long = nest({
      history_months: Array.from({ length: 200 }, (_, i) => `m${i}`),
      history_hits: Array.from({ length: 200 }, (_, i) => i),
    });
    const tail = historyTail(long, 60);
    expect(tail.months).toHaveLength(60);
    expect(tail.values[59]).toBe(199);
  });
});


describe("live-discovered domain runs", () => {
  it("groups pockets by sub-group, biggest group first, page order kept inside", () => {
    const ns = [
      nest({ id: 1, size: 10, group_id: 2, group_label: "Thermal safety" }),
      nest({ id: 2, size: 50, group_id: 1, group_label: "Chemistries" }),
      nest({ id: 3, size: 12, group_id: 2, group_label: "Thermal safety" }),
      nest({ id: 4, size: 40, group_id: 1, group_label: "Chemistries" }),
    ];
    const g = groupNests(ns)!;
    expect(g.map((x) => x.id)).toEqual([1, 2]);
    expect(g[0].nests.map((n) => n.id)).toEqual([2, 4]);
    expect(g[0].size).toBe(90);
    expect(g[1].label).toBe("Thermal safety");
  });

  it("does not group a plain run or a run with one group", () => {
    expect(groupNests([nest(), nest({ id: 2 })])).toBeNull();
    expect(groupNests([nest({ group_id: 1 }), nest({ id: 2, group_id: 1 })])).toBeNull();
  });

  it("says how a live run was made: term, window, selection, relative density", () => {
    const text = runProvenance(
      run({
        scope: "domain:q_batteries",
        nests: 24,
        scanned: 98000,
        window_days: 360,
        params: { mode: "live", term: "batteries", also: ["accumulator"], window_months: 12,
                  members_window: 28000, in_pockets: 0.27, cohesion_quantile: 0.6 },
      })
    );
    expect(text).toContain('"batteries" (also accumulator)');
    expect(text).toContain("28,000 signals of the last 12 months");
    expect(text).toContain("densest 40 % of their cells");
    expect(text).toContain("27 %");
    expect(text).toContain("98,000");
  });
});


describe("dated by the research and patent calendar", () => {
  const series = (first: number | null, edge = false) => ({
    first, edge, takeoff: first, growth: 2.5, total: 120,
    years: [2024, 2025, 2026], counts: [10, 40, 70], per_million: [1, 4, 7],
  });
  const dated = (sci: number | null, pat: number | null, edge = false) =>
    nest({
      first_month: "2026-07",
      age_months: 3,
      established_share: 0.1,
      calendar: { anchor: ["batteries"], phrases: ["redox flow", "flow battery"],
                  science: series(sci, edge), patent: series(pat) },
    });

  it("leads with the earliest year on record, research or patents", () => {
    expect(calendarFirst(dated(2010, 2005))).toEqual({ year: 2005, edge: false, corpus: "patent" });
    expect(ageText(dated(2010, 2005))).toBe("on record since 2005");
    expect(ageText(dated(2010, null, true))).toBe("on record since 2010 or earlier");
    expect(ageIsMeaningful(dated(2010, 2005))).toBe(true);
  });

  it("is young only when the record itself is young — not because our signals are", () => {
    expect(isYoung(dated(2010, 2005), 2026)).toBe(false);          // signal space says 3 months
    expect(isYoung(dated(2025, 2026), 2026)).toBe(true);
    expect(isYoung(dated(2025, null, true), 2026)).toBe(false);    // edge: may be older
  });

  it("says what was counted and drops the running year from the curve", () => {
    expect(calendarQuery(dated(2010, 2005))).toBe('"batteries" and ("redox flow" or "flow battery")');
    expect(calendarSpark(series(2024), 2026)).toEqual({ years: ["2024", "2025"], values: [1, 4] });
  });
});
