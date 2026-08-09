import { describe, it, expect } from "vitest";
import { computeTransferSeries } from "./transfer";

describe("computeTransferSeries", () => {
  it("aggregates per year and computes the university share", () => {
    const series = computeTransferSeries([
      { filing_year: 2020, psn_sector: "COMPANY", families: 80 },
      { filing_year: 2020, psn_sector: "UNIVERSITY", families: 20 },
      { filing_year: 2021, psn_sector: "COMPANY", families: 50 },
      { filing_year: 2021, psn_sector: "UNIVERSITY", families: 40 },
      { filing_year: 2021, psn_sector: "INDIVIDUAL", families: 10 },
    ]);
    expect(series).toHaveLength(2);
    expect(series[0]).toEqual({ year: 2020, total: 100, university: 20, uniShare: 0.2 });
    expect(series[1].uniShare).toBeCloseTo(0.4);
  });

  it("counts mixed sectors containing UNIVERSITY as university", () => {
    const series = computeTransferSeries([
      { filing_year: 2019, psn_sector: "GOV NON-PROFIT UNIVERSITY", families: 5 },
      { filing_year: 2019, psn_sector: "COMPANY UNIVERSITY", families: 5 },
      { filing_year: 2019, psn_sector: "GOV NON-PROFIT", families: 10 },
    ]);
    expect(series[0].university).toBe(10);
    expect(series[0].uniShare).toBeCloseTo(0.5);
  });

  it("sorts years ascending and handles empty input", () => {
    expect(computeTransferSeries([])).toEqual([]);
    const series = computeTransferSeries([
      { filing_year: 2022, psn_sector: "COMPANY", families: 1 },
      { filing_year: 2010, psn_sector: "COMPANY", families: 1 },
    ]);
    expect(series.map((p) => p.year)).toEqual([2010, 2022]);
  });
});
