import { describe, expect, it } from "vitest";
import {
  clusterSummary,
  cohesionLabel,
  concentrationNote,
  deltaText,
  megaAttribution,
  runProvenance,
  spreadBySource,
} from "./clusterCard";
import type { ForesightCluster, ForesightRun } from "./foresight";

function cluster(over: Partial<ForesightCluster> = {}): ForesightCluster {
  return {
    id: 1,
    cluster_idx: 0,
    label: "Streetwear · Collaboration",
    size: 822,
    cohesion: 0.65,
    mega_trend: "future_of_food_and_agriculture",
    mega_purity: 0.78,
    verticals: ["FASHION"],
    top_tags: ["streetwear"],
    n_sources: 44,
    top_source: "Hypebeast",
    top_source_share: 0.41,
    vol_delta_pct: 120,
    share_early: 0.032,
    share_late: 0.055,
    momentum: "rising",
    sov_delta_pp: 4.16,
    tier: null,
    reps: [],
    monthly_series: [],
    ...over,
  };
}

function run(over: Partial<ForesightRun> = {}): ForesightRun {
  return {
    id: 104,
    scope: "vertical:FASHION",
    tier: null,
    k: 9,
    signals: 8001,
    first_month: "2024-09",
    last_month: "2026-08",
    created_at: "2026-09-15",
    since: "2024-09-01",
    window_months: 24,
    cohort_sources: 30,
    cohort_coverage: 0.61,
    cohort_applied: true,
    ...over,
  };
}

describe("cluster card wording — claims must match what was computed", () => {
  it("states attention and volume as two separate facts", () => {
    expect(clusterSummary(cluster())).toBe(
      "Gaining share of attention, +4.2 pp. 3.2 % of panel signals in the early window, 5.5 % in the late one."
    );
    expect(
      clusterSummary(cluster({ momentum: "declining", sov_delta_pp: -1.7, share_early: 0.21, share_late: 0.193 }))
    ).toBe(
      "Losing share of attention, -1.7 pp. 21 % of panel signals in the early window, 19 % in the late one."
    );
  });

  it("never claims sources 'confirmed' anything", () => {
    const text = clusterSummary(cluster()) + concentrationNote(cluster()).title;
    expect(text.toLowerCase()).not.toContain("confirmed");
  });

  it("names the concentration when one outlet dominates", () => {
    const n = concentrationNote(cluster({ top_source: "Hypebeast", top_source_share: 0.41 }));
    expect(n.text).toBe("largest 41 %");
    expect(n.title).toContain("Hypebeast supplies 41 %");
    expect(concentrationNote(cluster({ top_source: null, top_source_share: 0 })).text).toBe("");
  });

  it("never uses the raw item count as the second number (the corpus grew 20-5000 %)", () => {
    const text = clusterSummary(cluster({ vol_delta_pct: 2628 }));
    expect(text).not.toContain("2628");
    expect(text).toContain("panel signals");
  });

  it("says nothing further when the window was too short to judge", () => {
    expect(
      clusterSummary(cluster({ momentum: "unknown", share_early: null, share_late: null }))
    ).toBe("Too short an observation window to call a direction.");
  });

  it("only attributes a mega-trend when it is an actual majority", () => {
    expect(megaAttribution(cluster({ mega_purity: 0.78 }))).toBe(true);
    expect(megaAttribution(cluster({ mega_purity: 0.24 }))).toBe(false);
    expect(megaAttribution(cluster({ mega_trend: null, mega_purity: 0.9 }))).toBe(false);
  });

  it("puts cohesion into words on the measured range", () => {
    expect(cohesionLabel(0.73)).toBe("tight");
    expect(cohesionLabel(0.62)).toBe("broad");
    expect(cohesionLabel(0.51)).toBe("loose");
  });

  it("formats signed deltas", () => {
    expect(deltaText(4.157)).toBe("+4.2 pp");
    expect(deltaText(-1.2)).toBe("-1.2 pp");
  });

  it("states window and panel, and admits when no panel was held", () => {
    expect(runProvenance(run())).toBe(
      "8,001 signals from the last 24 months (2024-09 to 2026-08). Momentum is measured on 30 sources that delivered in both comparison windows, 61 % of the signals in those windows."
    );
    expect(runProvenance(run({ cohort_applied: false }))).toContain("counts every source");
    expect(runProvenance(run({ window_months: 0 }))).toContain("the full archive");
  });
});

describe("spreadBySource — one outlet must not own a list", () => {
  const row = (source_name: string | null, id: number) => ({ source_name, id });

  it("caps a source at two rows while the list can still be filled", () => {
    const rows = [
      ...Array.from({ length: 10 }, (_, i) => row("Bulk", i)),
      row("A", 100),
      row("B", 101),
      row("C", 102),
    ];
    const out = spreadBySource(rows, 4);
    expect(out.map((r) => r.source_name)).toEqual(["Bulk", "Bulk", "A", "B"]);
  });

  it("falls back to the capped rows rather than returning a short list", () => {
    const rows = Array.from({ length: 6 }, (_, i) => row("Only", i));
    expect(spreadBySource(rows, 4).map((r) => r.id)).toEqual([0, 1, 2, 3]);
  });

  it("keeps rows without a source name", () => {
    const rows = [row(null, 1), row(null, 2), row(null, 3)];
    expect(spreadBySource(rows, 3)).toHaveLength(3);
  });
});
