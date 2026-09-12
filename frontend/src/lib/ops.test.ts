import { describe, expect, it } from "vitest";
import {
  carryForward, fillProjection, fillTone, fmtAgo, fmtBytes, fmtDuration, jobColor, niceMax,
  parseRange, runOutcome, seriesPath, smartVerdict, timeTicks, type DiskInfo, type OpsEvent,
} from "./ops";

const disk = (over: Partial<DiskInfo> = {}): DiskInfo => ({
  dev: "sda", model: "ST2000", rotational: true, size_bytes: 2e12, temp_c: 37, mounts: [],
  read_bytes_s: 0, write_bytes_s: 0, busy_pct: 0, smart: null, ...over,
});

describe("formatting", () => {
  it("bytes, durations, ago", () => {
    expect(fmtBytes(482_682_969_111)).toBe("449.5 GB");
    expect(fmtBytes(2_048_408_248_320)).toBe("1.9 TB");
    expect(fmtBytes(null)).toBe("—");
    expect(fmtDuration(45_000)).toBe("45s");
    expect(fmtDuration(9_359_000)).toBe("2h 35m");
    expect(fmtDuration(3 * 86_400_000)).toBe("3d 0h");
    const now = new Date("2026-09-11T17:00:00Z");
    expect(fmtAgo(new Date("2026-09-11T16:58:00Z"), now)).toBe("2 min ago");
    expect(fmtAgo(new Date("2026-09-11T16:59:50Z"), now)).toBe("just now");
    expect(fmtAgo(new Date("2026-09-09T12:00:00Z"), now)).toBe("2 d ago");
  });
  it("parseRange defaults to 24h", () => {
    expect(parseRange(undefined)).toBe("24h");
    expect(parseRange("7d")).toBe("7d");
    expect(parseRange(["7d"])).toBe("7d");
    expect(parseRange("x")).toBe("24h");
  });
});

describe("disks", () => {
  it("SMART verdict: nvme wear and ata sectors", () => {
    expect(smartVerdict(disk())).toEqual({ tone: "unknown", label: "no SMART" });
    expect(smartVerdict(disk({ smart: { passed: false } })).tone).toBe("bad");
    expect(smartVerdict(disk({ rotational: false, smart: { passed: true, type: "nvme", percentage_used: 1, available_spare: 100, media_errors: 0, critical_warning: 0, temp_c: 40 } })))
      .toEqual({ tone: "ok", label: "PASSED" });
    expect(smartVerdict(disk({ rotational: false, smart: { passed: true, type: "nvme", percentage_used: 92, available_spare: 100 } })).tone).toBe("bad");
    expect(smartVerdict(disk({ smart: { passed: true, type: "ata", reallocated: 3, pending: 0 } })))
      .toEqual({ tone: "warn", label: "3 reallocated" });
    expect(smartVerdict(disk({ smart: { passed: true, type: "ata", temp_c: 55 } })).label).toBe("55 °C");
    expect(smartVerdict(disk({ smart: { standby: true } })).label).toBe("standby");
  });
  it("fill tone: system disk warns at 80", () => {
    expect(fillTone(79, true)).toBe("ok");
    expect(fillTone(81, true)).toBe("warn");
    expect(fillTone(81, false)).toBe("ok");
    expect(fillTone(91)).toBe("bad");
    expect(fillTone(null)).toBe("unknown");
  });
  it("fill projection: linear growth → days until full; flat → null", () => {
    const d0 = new Date("2026-09-01T00:00:00Z");
    const pts = [0, 1, 2, 3].map((i) => ({ t: new Date(d0.getTime() + i * 86_400_000), used: 100 + i * 10 }));
    const p = fillProjection(pts, 200);
    expect(p.bytesPerDay).toBeCloseTo(10);
    expect(p.daysUntilFull).toBeCloseTo(7);
    expect(fillProjection(pts.map((x) => ({ ...x, used: 100 })), 200).daysUntilFull).toBeNull();
    expect(fillProjection(pts.slice(0, 2), 200).daysUntilFull).toBeNull();
  });
});

describe("series / svg", () => {
  const from = new Date("2026-09-11T00:00:00Z");
  const to = new Date("2026-09-12T00:00:00Z");
  const box = { x: 0, y: 0, w: 100, h: 100 };
  it("path breaks at nulls and clamps", () => {
    const pts = [
      { t: from, v: 0 }, { t: new Date("2026-09-11T12:00:00Z"), v: 50 },
      { t: new Date("2026-09-11T18:00:00Z"), v: null }, { t: to, v: 200 },
    ];
    expect(seriesPath(pts, from, to, 100, box)).toBe("M0.0,100.0L50.0,50.0M100.0,0.0");
    expect(seriesPath(pts, from, to, 100, box, 50)).toBe("M0.0,100.0L50.0,100.0M100.0,0.0");
    expect(seriesPath([], from, to, 100, box)).toBe("");
  });
  it("carryForward fills gaps from the left only", () => {
    const out = carryForward([{ t: from, v: null }, { t: from, v: 3 }, { t: from, v: null }, { t: from, v: 5 }]);
    expect(out.map((p) => p.v)).toEqual([null, 3, 3, 5]);
  });
  it("niceMax and ticks", () => {
    expect(niceMax(24576)).toBe(25000);
    expect(niceMax(87)).toBe(100);
    expect(niceMax(0)).toBe(1);
    const t24 = timeTicks(new Date("2026-09-11T03:20:00"), new Date("2026-09-12T03:20:00"));
    expect(t24.map((t) => t.getHours())).toEqual([6, 12, 18, 0]);
    const t7 = timeTicks(new Date("2026-09-05T10:00:00"), new Date("2026-09-12T10:00:00"));
    expect(t7).toHaveLength(7);
    expect(t7.every((t) => t.getHours() === 0)).toBe(true);
  });
});

describe("jobs", () => {
  it("stable colours and outcomes", () => {
    expect(jobColor("full_cycle_cron")).toBe(jobColor("full_cycle_cron"));
    expect(jobColor("full_cycle_cron")).toMatch(/^#/);
    const now = new Date("2026-09-11T12:00:00Z");
    const ev = (o: Partial<OpsEvent>): OpsEvent => ({
      id: 1, job: "x", host: "local", started_at: new Date("2026-09-11T04:00:00Z"), ended_at: null, rc: null, note: null, ...o,
    });
    expect(runOutcome(ev({}), now)).toEqual({ tone: "warn", label: "running > 6 h" });
    expect(runOutcome(ev({ started_at: new Date("2026-09-11T11:00:00Z") }), now).label).toBe("running");
    expect(runOutcome(ev({ ended_at: now, rc: 0 }), now).tone).toBe("ok");
    expect(runOutcome(ev({ ended_at: now, rc: 75 }), now).label).toBe("blocked");
    expect(runOutcome(ev({ ended_at: now, rc: 2 }), now)).toEqual({ tone: "bad", label: "rc 2" });
    // closed by the sampler's orphan sweep: ended, no rc
    expect(runOutcome(ev({ ended_at: now, rc: null }), now)).toEqual({ tone: "bad", label: "aborted" });
  });
});
