import { afterEach, describe, expect, it } from "vitest";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { readMethodologyStatsSnapshot } from "./db";

const dirs: string[] = [];
afterEach(() => { for (const d of dirs.splice(0)) rmSync(d, { recursive: true, force: true }); });

describe("readMethodologyStatsSnapshot", () => {
  it("returns null without a file", () => {
    expect(readMethodologyStatsSnapshot(undefined)).toBeNull();
    expect(readMethodologyStatsSnapshot("/nonexistent/stats.json")).toBeNull();
  });
  it("reads the build snapshot and fills defaults", () => {
    const d = mkdtempSync(join(tmpdir(), "mstats-")); dirs.push(d);
    const f = join(d, "s.json");
    writeFileSync(f, JSON.stringify({ analyzed: 1200000, published: 89000, tierCounts: { market: 5 } }));
    const s = readMethodologyStatsSnapshot(f);
    expect(s?.analyzed).toBe(1200000);
    expect(s?.tierCounts.market).toBe(5);
    expect(s?.dateSpan).toEqual({ first: null, last: null });
  });
  it("rejects a malformed snapshot", () => {
    const d = mkdtempSync(join(tmpdir(), "mstats-")); dirs.push(d);
    const f = join(d, "s.json"); writeFileSync(f, "{\"analyzed\": \"x\"}");
    expect(readMethodologyStatsSnapshot(f)).toBeNull();
  });
});
