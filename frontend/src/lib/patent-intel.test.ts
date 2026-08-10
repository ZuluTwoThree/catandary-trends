import { describe, it, expect } from "vitest";
import {
  nplShare, ceasedWithin, topCountries, countryShare,
  oppositionRate, emergingGroups,
} from "./patent-intel";

describe("nplShare", () => {
  it("computes the share and handles missing years", () => {
    const rows = [{ publn_year: 2023, citations: 200, npl_citations: 50 }];
    expect(nplShare(rows, 2023)).toBeCloseTo(0.25);
    expect(nplShare(rows, 2020)).toBeNull();
  });
});

describe("ceasedWithin", () => {
  const rows = [
    { filing_year: 2012, cohort_size: 100, age_years: 3, cessations: 10 },
    { filing_year: 2012, cohort_size: 100, age_years: 9, cessations: 5 },
    { filing_year: 2012, cohort_size: 100, age_years: 12, cessations: 30 },
    { filing_year: 2013, cohort_size: 50, age_years: -1, cessations: 0 },
  ];
  it("sums cessations strictly below the age cutoff", () => {
    expect(ceasedWithin(rows, 2012, 10)).toBeCloseTo(0.15);
  });
  it("treats a cohort with only the -1 sentinel as fully surviving", () => {
    expect(ceasedWithin(rows, 2013, 10)).toBe(0);
  });
  it("returns null for unknown cohorts", () => {
    expect(ceasedWithin(rows, 1999, 10)).toBeNull();
  });
});

describe("topCountries / countryShare", () => {
  const rows = [
    { filing_year: 2023, ctry: "KR", families: 60 },
    { filing_year: 2023, ctry: "CN", families: 30 },
    { filing_year: 2023, ctry: "JP", families: 10 },
    { filing_year: 2015, ctry: "JP", families: 80 },
    { filing_year: 2015, ctry: "KR", families: 20 },
  ];
  it("ranks countries and computes shares within the year", () => {
    const top = topCountries(rows, 2023, 2);
    expect(top.map((t) => t.ctry)).toEqual(["KR", "CN"]);
    expect(top[0].share).toBeCloseTo(0.6);
  });
  it("computes a single country's share incl. zero for absent countries", () => {
    expect(countryShare(rows, 2015, "KR")).toBeCloseTo(0.2);
    expect(countryShare(rows, 2015, "CN")).toBe(0);
    expect(countryShare(rows, 1990, "KR")).toBeNull();
  });
});

describe("oppositionRate", () => {
  it("computes 26/(26+26N) per year", () => {
    const rows = [
      { event_year: 2020, event_code: "26", applications: 5 },
      { event_year: 2020, event_code: "26N", applications: 95 },
    ];
    expect(oppositionRate(rows, 2020)).toBeCloseTo(0.05);
    expect(oppositionRate(rows, 2019)).toBeNull();
  });
});

describe("emergingGroups", () => {
  const mk = (g: string, y: number, f: number) => ({ cpc_group: g, filing_year: y, families: f });
  it("ranks by growth of recent vs base average and applies the base floor", () => {
    const rows = [
      mk("G06N10", 2014, 30), mk("G06N10", 2015, 30), mk("G06N10", 2020, 300),
      mk("G06N3", 2014, 1000), mk("G06N3", 2015, 1000), mk("G06N3", 2020, 1500),
      mk("G06N99", 2014, 2), mk("G06N99", 2020, 400), // Basis unter Floor → raus
    ];
    const top = emergingGroups(rows, 2018, 3);
    expect(top.map((t) => t.group)).toEqual(["G06N10", "G06N3"]);
    expect(top[0].growth).toBeCloseTo(9);
  });
});
