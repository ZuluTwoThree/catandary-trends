/**
 * Crontab → week plan (#104, Stufe 4). Parses the five-field schedule of each
 * crontab line, names the job from the script it runs (the same name the
 * wrappers write into ops_events), and expands the schedule into concrete
 * start times inside a window. Pure functions; the file/`crontab -l` read
 * lives in opsDb.ts.
 */

export interface CronEntry {
  minute: Set<number>;
  hour: Set<number>;
  dom: Set<number>;
  month: Set<number>;
  dow: Set<number>; // 0 = Sunday … 6
  domStar: boolean;
  dowStar: boolean;
  job: string;
  command: string;
  line: string;
}

function parseField(spec: string, min: number, max: number): Set<number> {
  const out = new Set<number>();
  for (const part of spec.split(",")) {
    const [rangeSpec, stepSpec] = part.split("/");
    const step = stepSpec ? Math.max(1, parseInt(stepSpec, 10)) : 1;
    let lo = min;
    let hi = max;
    if (rangeSpec !== "*") {
      const m = rangeSpec.match(/^(\d+)(?:-(\d+))?$/);
      if (!m) continue;
      lo = parseInt(m[1], 10);
      hi = m[2] ? parseInt(m[2], 10) : stepSpec ? max : lo;
    }
    for (let v = lo; v <= hi; v += step) if (v >= min && v <= max) out.add(v === 7 && max === 6 ? 0 : v);
  }
  return out;
}

/** Job name from the command: scripts/<name>.sh|.py, -m scripts.<name>, else the first token's basename. */
export function jobNameFromCommand(cmd: string): string {
  const m = cmd.match(/scripts\/([A-Za-z0-9_]+)\.(?:sh|py)\b/) ?? cmd.match(/-m scripts\.([A-Za-z0-9_]+)/);
  if (m) return m[1];
  const first = cmd.trim().split(/\s+/)[0] ?? "";
  return first.split("/").pop() ?? first;
}

export function parseCrontab(text: string): CronEntry[] {
  const out: CronEntry[] = [];
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line || line.startsWith("#") || /^[A-Z_]+=/.test(line)) continue;
    const m = line.match(/^(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(.+)$/);
    if (!m) continue;
    const [, mi, ho, dm, mo, dw, command] = m;
    out.push({
      minute: parseField(mi, 0, 59),
      hour: parseField(ho, 0, 23),
      dom: parseField(dm, 1, 31),
      month: parseField(mo, 1, 12),
      dow: parseField(dw, 0, 6),
      domStar: dm === "*",
      dowStar: dw === "*",
      job: jobNameFromCommand(command),
      command,
      line,
    });
  }
  return out;
}

export function matchesDay(e: CronEntry, d: Date): boolean {
  if (!e.month.has(d.getMonth() + 1)) return false;
  const domOk = e.dom.has(d.getDate());
  const dowOk = e.dow.has(d.getDay());
  // Vixie rule: when both day fields are restricted, either one may match.
  if (!e.domStar && !e.dowStar) return domOk || dowOk;
  if (!e.domStar) return domOk;
  if (!e.dowStar) return dowOk;
  return true;
}

export interface Occurrence {
  job: string;
  start: Date;
}

/** All start times of `e` in [from, to) — local time, as cron itself runs. */
export function occurrences(e: CronEntry, from: Date, to: Date): Occurrence[] {
  const out: Occurrence[] = [];
  const day = new Date(from);
  day.setHours(0, 0, 0, 0);
  const hours = [...e.hour].sort((a, b) => a - b);
  const minutes = [...e.minute].sort((a, b) => a - b);
  while (day.getTime() < to.getTime()) {
    if (matchesDay(e, day)) {
      for (const h of hours) for (const mi of minutes) {
        const t = new Date(day);
        t.setHours(h, mi, 0, 0);
        if (t.getTime() >= from.getTime() && t.getTime() < to.getTime()) out.push({ job: e.job, start: t });
      }
    }
    day.setDate(day.getDate() + 1);
  }
  return out.sort((a, b) => a.start.getTime() - b.start.getTime());
}

/** Monday 00:00 of the week containing `d` (local time). */
export function weekStart(d: Date): Date {
  const s = new Date(d);
  s.setHours(0, 0, 0, 0);
  const dow = (s.getDay() + 6) % 7; // Monday = 0
  s.setDate(s.getDate() - dow);
  return s;
}

export interface PlannedBlock {
  job: string;
  start: Date;
  end: Date;
  source: "cron" | "plan";
  label?: string;
}

/** Overlapping pairs among blocks — the collisions the owner wants to see before adding a run. */
export function collisions(blocks: PlannedBlock[]): [PlannedBlock, PlannedBlock][] {
  const sorted = [...blocks].sort((a, b) => a.start.getTime() - b.start.getTime());
  const out: [PlannedBlock, PlannedBlock][] = [];
  for (let i = 0; i < sorted.length; i++) {
    for (let j = i + 1; j < sorted.length; j++) {
      if (sorted[j].start.getTime() >= sorted[i].end.getTime()) break;
      if (sorted[i].job === sorted[j].job) continue;
      out.push([sorted[i], sorted[j]]);
    }
  }
  return out;
}
