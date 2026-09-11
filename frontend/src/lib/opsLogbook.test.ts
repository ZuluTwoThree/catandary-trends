import { describe, expect, it } from "vitest";
import { parseDuration, parseLogbook, planStart, sortLogbook } from "./opsLogbook";

const MD = `# Ops-Logbuch

Intro text that is not an entry.

## 2026-09-15 14:00 · plan · Backfill Volltext-Vektoren
duration: 3h
gpu: bequiet

Nur im Fenster. Zweite Zeile.

## 2026-09-11 · change · Ops-Dashboard
Stufen 1–3.

## 2026-09 · idea · zweite Karte?
Nur ein Gedanke.
key: value inside body, not meta
`;

describe("logbook parsing", () => {
  it("splits entries, reads head and meta, keeps body markdown", () => {
    const e = parseLogbook(MD);
    expect(e).toHaveLength(3);
    expect(e[0]).toMatchObject({ date: "2026-09-15", time: "14:00", kind: "plan", title: "Backfill Volltext-Vektoren",
      meta: { duration: "3h", gpu: "bequiet" }, body: "Nur im Fenster. Zweite Zeile.", line: 5 });
    expect(e[1]).toMatchObject({ date: "2026-09-11", time: null, kind: "change", meta: {}, body: "Stufen 1–3." });
    expect(e[2].date).toBe("2026-09");
    expect(e[2].meta).toEqual({});
    expect(e[2].body).toContain("key: value inside body");
  });
  it("sorts newest first with month-only entries as the 1st", () => {
    const e = sortLogbook(parseLogbook(MD));
    expect(e.map((x) => x.title)).toEqual(["Backfill Volltext-Vektoren", "Ops-Dashboard", "zweite Karte?"]);
  });
  it("durations and plan starts", () => {
    expect(parseDuration("3h")).toBe(3 * 3_600_000);
    expect(parseDuration("2h30m")).toBe(2.5 * 3_600_000);
    expect(parseDuration("45 min")).toBe(45 * 60_000);
    expect(parseDuration("1d")).toBe(86_400_000);
    expect(parseDuration("soon")).toBeNull();
    expect(parseDuration(undefined)).toBeNull();
    const e = parseLogbook(MD);
    const s = planStart(e[0])!;
    expect([s.getFullYear(), s.getMonth(), s.getDate(), s.getHours()]).toEqual([2026, 8, 15, 14]);
    expect(planStart(e[1])).toBeNull();   // change, not plan
    expect(planStart(e[2])).toBeNull();   // no day
  });
});
