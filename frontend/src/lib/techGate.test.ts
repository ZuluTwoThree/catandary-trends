import { describe, expect, it } from "vitest";
import {
  clusterChoices, clusterHeadline, clusterHint, gateVerdict, offTopicHeadline,
  suggestionQueries, type Gate,
} from "./techGate";

// Mirror of the #67 acceptance in tests/test_query_gate.py: the Python side
// decides the verdict, this side must render it honestly and re-queryably.

describe("gateVerdict", () => {
  it("prefers the gate verdict and falls back to the legacy boolean", () => {
    expect(gateVerdict({ gate: { verdict: "ambiguous" } })).toBe("ambiguous");
    expect(gateVerdict({ gate: { verdict: "off_topic" }, off_topic: false })).toBe("off_topic");
    expect(gateVerdict({ off_topic: true })).toBe("off_topic");
    expect(gateVerdict({ off_topic: false })).toBe("ok");
    expect(gateVerdict({})).toBe("ok");
    expect(gateVerdict({ gate: null })).toBe("ok");
  });
});

describe("offTopicHeadline", () => {
  it("names the phrase and never claims a number", () => {
    expect(offTopicHeadline("unicorn breeding")).toBe("We don't see a technology signature for “unicorn breeding”.");
    expect(offTopicHeadline("  ")).toBe("We don't see a technology signature for that phrase.");
  });
});

describe("suggestionQueries", () => {
  const gate: Gate = {
    verdict: "off_topic",
    suggestions: [
      { symbol: "A01K2227/107", label: "Animals characterised by species", dist: 0.35 },
      { symbol: "A61D19/00", label: "Instruments or methods for reproduction or fertilisation", dist: 0.363 },
      { symbol: "A01K67/30", label: "  animals   characterised by species ", dist: 0.381 }, // dup after normalising
      { symbol: "X", label: "ab", dist: 0.4 },                                              // too short to re-query
      { symbol: "A01K67/34", label: "Insects", dist: 0.383 },
    ],
  };
  it("keeps 2–3 unique, re-queryable labels in distance order", () => {
    expect(suggestionQueries(gate)).toEqual([
      "Animals characterised by species",
      "Instruments or methods for reproduction or fertilisation",
      "Insects",
    ]);
    expect(suggestionQueries(gate, 2)).toHaveLength(2);
  });
  it("is empty without suggestions", () => {
    expect(suggestionQueries(undefined)).toEqual([]);
    expect(suggestionQueries({ verdict: "ok" })).toEqual([]);
  });
  it("clamps an over-long label to the API bound", () => {
    const long = { verdict: "off_topic" as const, suggestions: [{ symbol: "Z", label: "x".repeat(250) }] };
    expect(suggestionQueries(long)[0]).toHaveLength(200);
  });
});

describe("clusterChoices", () => {
  const gate: Gate = {
    verdict: "ambiguous",
    reason: "the words point to G06N (55% of matching patent titles) but the closest classes are in H03M, H04L",
    clusters: [
      { subclass: "H03M", label: "Coding; decoding; code conversion in general", symbols: ["H03M13/63", "H03M13/13"], source: "embedding" },
      { subclass: "G06N", label: "Computing arrangements based on specific computational models", symbols: ["G06N10/70", "G06N10/40"], source: "words" },
      { subclass: "H04L", label: "Block codes", symbols: ["H04L1/0057"], source: "embedding" },
      { subclass: "H04L", label: "dup", symbols: ["H04L1/0061"], source: "embedding" },
      { subclass: "B99Z", label: "empty", symbols: [], source: "embedding" },
    ],
  };
  it("puts the words-derived field first, one per subclass, drops empty clusters", () => {
    expect(clusterChoices(gate).map((c) => c.subclass)).toEqual(["G06N", "H03M", "H04L"]);
    expect(clusterChoices(gate, 2).map((c) => c.subclass)).toEqual(["G06N", "H03M"]);
  });
  it("is empty for ok / missing gates", () => {
    expect(clusterChoices({ verdict: "ok" })).toEqual([]);
    expect(clusterChoices(null)).toEqual([]);
  });
  it("labels a choice with field, subclass and class count", () => {
    const [words, emb] = clusterChoices(gate);
    expect(clusterHeadline(words)).toBe("Computing arrangements based on specific computational models · G06N · 2 classes");
    expect(clusterHeadline({ subclass: "H04L", label: "Block codes", symbols: ["H04L1/0057"] })).toBe("Block codes · H04L · 1 class");
    expect(clusterHint(words)).toMatch(/words of your phrase/);
    expect(clusterHint(emb)).toMatch(/closest patent classes/);
  });
});
