/**
 * Parity tests for the garbage-detector port (#11, 2026-09-05). Same real-body
 * fixture as tests/test_content_guard.py — every incident body must be caught,
 * the 20 clean bodies must pass, and the reason strings must match Python's.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, it, expect } from "vitest";
import { garbageReasons, isGarbled } from "@/lib/content-guard";

interface Row { id: number; source_name: string; body: string; source: string }
const FIX = JSON.parse(
  readFileSync(resolve(__dirname, "../../../tests/fixtures/content_guard_bodies_2026-09-05.json"), "utf8")
) as { garbage: Row[]; cjk_leak: Row[]; legit_cjk: Row[]; clean: Row[] };

const kinds = (rs: string[]) => new Set(rs.map((r) => r.split(":")[0]));

const PROSE =
  "The company reported a measurable shift in procurement behaviour, with " +
  "buyers favouring suppliers that publish verified emissions data. Analysts " +
  "attribute the change to new disclosure rules and to pressure from lenders, " +
  "who increasingly price climate risk into credit terms. The report notes " +
  "that smaller manufacturers struggle to produce the required documentation " +
  "and may lose contracts as a result, while larger groups absorb the cost.";

describe("garbageReasons — parity with pipeline/content_guard.py", () => {
  it("catches all 22 incident bodies without a source", () => {
    expect(FIX.garbage).toHaveLength(22);
    for (const r of FIX.garbage) expect(garbageReasons(r.body), String(r.id)).not.toEqual([]);
    expect(FIX.garbage.every((r) => isGarbled(r.body))).toBe(true);
  });

  it("raises no alarm on 20 clean bodies from 20 sources", () => {
    for (const r of FIX.clean) {
      expect(garbageReasons(r.body), String(r.id)).toEqual([]);
      expect(garbageReasons(r.body, r.source), String(r.id)).toEqual([]);
    }
  });

  it("sees a CJK leak only against the source", () => {
    for (const r of FIX.cjk_leak) {
      expect(kinds(garbageReasons(r.body, r.source)).has("script_leak"), String(r.id)).toBe(true);
    }
  });

  it("allows CJK that stands in the source ('Chopstick 箸')", () => {
    for (const r of FIX.legit_cjk) expect(garbageReasons(r.body, r.source), String(r.id)).toEqual([]);
  });

  it("produces Python's reason strings", () => {
    expect(garbageReasons(": writing writing市/address : writing M M M M M       仪器(")).toEqual([
      "non_latin_script:5.4%", "word_repetition:M", "too_short:10w", "whitespace_run",
    ]);
    expect(garbageReasons("")).toEqual(["empty"]);
    expect(garbageReasons(PROSE)).toEqual([]);
    expect(kinds(garbageReasons(PROSE + " URLURLURL"))).toContain("glued_repetition");
    expect(kinds(garbageReasons(PROSE + " $1,000,000 in 2000."))).not.toContain("glued_repetition");
    expect(kinds(garbageReasons(PROSE.replace("procurement", "α-synuclein β-cell µm")))).not.toContain(
      "non_latin_script"
    );
  });
});
