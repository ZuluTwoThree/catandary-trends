import { describe, expect, it } from "vitest";
import { collisions, jobNameFromCommand, matchesDay, occurrences, parseCrontab, weekStart } from "./opsCron";

const CRONTAB = `
XDG_RUNTIME_DIR=/run/user/1000
# Full Cycle
0 4 * * 1-5 /home/dirk/projects/catandary-trends/scripts/full_cycle_cron.sh
45 2 * * * /x/.venv/bin/python /x/scripts/backup_db.py --dest /mnt --keep-days 4 >> /l 2>&1
45 7 * * 1-5 cd /x && .venv/bin/python -m scripts.cycle_watchdog >> /l 2>&1
0 6 * * 6 [ -x /x/scripts/weekly_ingesters.sh ] && /x/scripts/weekly_ingesters.sh || echo skip
0 2 5 * * /x/scripts/sync_openalex_monthly.sh
*/15 9-17 * * * /x/scripts/foo.sh
`;

describe("crontab parsing", () => {
  it("names jobs like the wrappers do", () => {
    expect(jobNameFromCommand("/x/scripts/full_cycle_cron.sh")).toBe("full_cycle_cron");
    expect(jobNameFromCommand("cd /x && .venv/bin/python -m scripts.cycle_watchdog >> l")).toBe("cycle_watchdog");
    expect(jobNameFromCommand("/x/.venv/bin/python /x/scripts/backup_db.py --dest /mnt")).toBe("backup_db");
    expect(jobNameFromCommand("[ -x /x/scripts/weekly_ingesters.sh ] && /x/scripts/weekly_ingesters.sh")).toBe("weekly_ingesters");
    expect(jobNameFromCommand("/usr/bin/foo bar")).toBe("foo");
  });
  it("skips env and comments, parses fields", () => {
    const e = parseCrontab(CRONTAB);
    expect(e.map((x) => x.job)).toEqual(["full_cycle_cron", "backup_db", "cycle_watchdog", "weekly_ingesters", "sync_openalex_monthly", "foo"]);
    expect([...e[0].dow]).toEqual([1, 2, 3, 4, 5]);
    expect(e[0].domStar).toBe(true);
    expect([...e[5].minute]).toEqual([0, 15, 30, 45]);
    expect([...e[5].hour]).toEqual([9, 10, 11, 12, 13, 14, 15, 16, 17]);
    expect(e[4].domStar).toBe(false);
    expect([...e[4].dom]).toEqual([5]);
  });
  it("day matching: dow, dom, and the vixie either-or", () => {
    const e = parseCrontab(CRONTAB);
    const sat = new Date(2026, 8, 12); // Sat 12.09.2026
    const mon = new Date(2026, 8, 14);
    expect(matchesDay(e[3], sat)).toBe(true);
    expect(matchesDay(e[3], mon)).toBe(false);
    expect(matchesDay(e[0], sat)).toBe(false);
    expect(matchesDay(e[0], mon)).toBe(true);
    expect(matchesDay(e[4], new Date(2026, 9, 5))).toBe(true);
    expect(matchesDay(e[4], new Date(2026, 9, 6))).toBe(false);
    const both = parseCrontab("0 0 1 * 3 x")[0];
    expect(matchesDay(both, new Date(2026, 9, 1))).toBe(true);  // dom 1
    expect(matchesDay(both, new Date(2026, 8, 16))).toBe(true); // Wednesday
    expect(matchesDay(both, new Date(2026, 8, 17))).toBe(false);
  });
  it("expands a week of occurrences in local time", () => {
    const e = parseCrontab(CRONTAB);
    const from = weekStart(new Date(2026, 8, 11, 15)); // Fri → Mon 07.09. 00:00
    expect(from.getDay()).toBe(1);
    expect(from.getHours()).toBe(0);
    const to = new Date(from);
    to.setDate(to.getDate() + 7);
    const cyc = occurrences(e[0], from, to);
    expect(cyc).toHaveLength(5);
    expect(cyc[0].start.getHours()).toBe(4);
    expect(occurrences(e[1], from, to)).toHaveLength(7);
    expect(occurrences(e[3], from, to).map((o) => o.start.getDay())).toEqual([6]);
    expect(occurrences(e[5], from, to)).toHaveLength(7 * 9 * 4);
  });
  it("collisions: overlapping blocks of different jobs", () => {
    const t = (h: number, m = 0) => new Date(2026, 8, 15, h, m);
    const blocks = [
      { job: "a", start: t(8), end: t(9, 30), source: "cron" as const },
      { job: "b", start: t(9), end: t(10), source: "cron" as const },
      { job: "c", start: t(11), end: t(12), source: "cron" as const },
      { job: "a", start: t(9, 15), end: t(9, 20), source: "cron" as const },
    ];
    const c = collisions(blocks);
    expect(c.map(([x, y]) => `${x.job}-${y.job}`)).toEqual(["a-b", "b-a"]);
  });
});
