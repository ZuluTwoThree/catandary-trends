import { describe, expect, it } from "vitest";
import { ageHours, parseReport, proposalAt } from "./agentReport";

const RAW = JSON.stringify({
  date: "2026-09-22T17:00:00+00:00",
  model: "gemma",
  dry_run: true,
  items: [
    {
      id: 1797102,
      decision: "human",
      why: "role",
      figures: [{ token: "2026", ok: true, why: "date", evidence: "am 12. Juni 2026", form: "date", note: "" }],
      names: [
        { name: "David Lammy", ok: false, kind: "role_only", evidence: "the Foreign Secretary",
          source_form: "Foreign Secretary", note: "", title_not_in_source: [] },
      ],
      proposals: [{ kind: "drop_sentence", what: "David Lammy", note: "Satz streichen" }],
    },
    { id: "nonsense", decision: "human", why: "", figures: [], names: [], proposals: [] },
  ],
});

describe("parseReport", () => {
  it("indexes items by trend id and keeps quotes and classes", () => {
    const r = parseReport(RAW)!;
    expect(r.dryRun).toBe(true);
    expect(r.items.size).toBe(1); // die Zeile ohne gueltige id faellt raus
    const it = r.items.get(1797102)!;
    expect(it.names[0].kind).toBe("role_only");
    expect(it.names[0].source_form).toBe("Foreign Secretary");
    expect(it.figures[0].ok).toBe(true);
  });

  it("survives a broken or empty file instead of breaking the desk", () => {
    expect(parseReport("{not json")).toBeNull();
    expect(parseReport("{}")!.items.size).toBe(0);
  });
});

describe("proposalAt", () => {
  const r = parseReport(RAW);
  it("returns the proposal the report holds, by index", () => {
    expect(proposalAt(r, 1797102, 0)?.kind).toBe("drop_sentence");
  });
  it("returns null for an unknown trend, a stale index or no report", () => {
    expect(proposalAt(r, 999, 0)).toBeNull();
    expect(proposalAt(r, 1797102, 5)).toBeNull();
    expect(proposalAt(null, 1797102, 0)).toBeNull();
  });
});

describe("ageHours", () => {
  it("measures how stale the report is", () => {
    expect(ageHours(parseReport(RAW), new Date("2026-09-22T20:00:00Z"))).toBeCloseTo(3);
    expect(ageHours(null)).toBeNull();
  });
});
