import { describe, expect, it } from "vitest";
import { classifyMomentum } from "./momentum";

// Mirror tests exist in tests/test_mega_momentum.py — same cases, same
// expectations. If one side changes thresholds, both suites must move.
describe("classifyMomentum", () => {
  it("returns null below the evidence floor — no claim beats a wrong claim", () => {
    expect(classifyMomentum(4, 5, 1000, 1000)).toBeNull();
    expect(classifyMomentum(0, 0, 1000, 1000)).toBeNull();
  });

  it("classifies by share change, not raw counts", () => {
    // raw count doubles, but the corpus doubled too → share flat → stable
    expect(classifyMomentum(200, 100, 20000, 10000)).toBe("stable");
    // share +50 % → rising even though raw counts fell
    expect(classifyMomentum(30, 40, 1000, 2000)).toBe("rising");
    // share −50 % → declining
    expect(classifyMomentum(20, 40, 1000, 1000)).toBe("declining");
  });

  it("±15 % is the boundary", () => {
    expect(classifyMomentum(114, 100, 1000, 1000)).toBe("stable");
    expect(classifyMomentum(116, 100, 1000, 1000)).toBe("rising");
    expect(classifyMomentum(86, 100, 1000, 1000)).toBe("stable");
    expect(classifyMomentum(84, 100, 1000, 1000)).toBe("declining");
  });

  it("emerging = present now, absent in the prior window", () => {
    expect(classifyMomentum(12, 0, 1000, 1000)).toBe("emerging");
  });

  it("degenerate totals produce no claim", () => {
    expect(classifyMomentum(50, 50, 0, 1000)).toBeNull();
    expect(classifyMomentum(50, 50, 1000, 0)).toBeNull();
  });
});
