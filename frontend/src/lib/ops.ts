/**
 * Ops-Dashboard `/trends/ops` (#104): types and pure helpers — formatting,
 * fill projection, SVG path building, job colours. No I/O here; the queries
 * live in `opsDb.ts`, so this file stays unit-testable.
 */

export interface DiskMount {
  part: string;
  mount: string;
  size_bytes: number;
  used_bytes: number;
  avail_bytes: number;
}

export interface DiskSmart {
  passed?: boolean | null;
  temp_c?: number | null;
  power_on_hours?: number | null;
  type?: "nvme" | "ata";
  percentage_used?: number | null;
  available_spare?: number | null;
  media_errors?: number | null;
  critical_warning?: number | null;
  reallocated?: number | null;
  pending?: number | null;
  uncorrectable?: number | null;
  error?: string;
  standby?: boolean;
}

export interface DiskInfo {
  dev: string;
  model: string | null;
  rotational: boolean;
  size_bytes: number;
  temp_c: number | null;
  mounts: DiskMount[];
  read_bytes_s: number | null;
  write_bytes_s: number | null;
  busy_pct: number | null;
  smart?: DiskSmart | null;
}

export interface Sample {
  ts: Date;
  is_full: boolean;
  gpu_mem_used_mib: number | null;
  gpu_mem_total_mib: number | null;
  gpu_util_pct: number | null;
  gpu_temp_c: number | null;
  gpu_power_w: number | null;
  gpu_model: string | null;
  gpu_job: string | null;
  remote_backend: string | null;
  remote_in_window: boolean | null;
  remote_model: string | null;
  cpu_pct: number | null;
  load1: number | null;
  mem_used_mib: number | null;
  mem_total_mib: number | null;
  db_size_bytes: number | null;
  db_connections: number | null;
  db_max_connections: number | null;
  db_long_queries: number | null;
  disks: DiskInfo[] | null;
  tables: Record<string, number> | null;
  backlog_unprocessed: number | null;
  review_queue: number | null;
  fulltext_vectors_missing: number | null;
}

export interface OpsEvent {
  id: number;
  job: string;
  host: string;
  started_at: Date;
  ended_at: Date | null;
  rc: number | null;
  note: string | null;
}

export interface JobStat {
  job: string;
  runs: number;
  median_s: number | null;
  last_started: Date;
  last_rc: number | null;
  last_s: number | null;
}

export interface SeriesPoint {
  t: Date;
  v: number | null;
}

export interface Band {
  job: string;
  start: Date;
  end: Date | null;
  rc?: number | null;
}

/* ---------- formatting ---------- */

const GB = 1024 ** 3;

export function fmtBytes(n: number | null | undefined, digits = 1): string {
  if (n == null || !Number.isFinite(n)) return "—";
  if (n >= 1024 ** 4) return `${(n / 1024 ** 4).toFixed(digits)} TB`;
  if (n >= GB) return `${(n / GB).toFixed(digits)} GB`;
  if (n >= 1024 ** 2) return `${(n / 1024 ** 2).toFixed(0)} MB`;
  if (n >= 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${n} B`;
}

export function fmtRate(bytesPerSec: number | null | undefined): string {
  if (bytesPerSec == null) return "—";
  return `${fmtBytes(bytesPerSec, bytesPerSec >= GB ? 1 : 0)}/s`;
}

export function fmtMiB(mib: number | null | undefined): string {
  if (mib == null) return "—";
  return mib >= 1024 ? `${(mib / 1024).toFixed(1)} GB` : `${mib} MB`;
}

export function fmtDuration(ms: number | null | undefined): string {
  if (ms == null || !Number.isFinite(ms) || ms < 0) return "—";
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s`;
  const h = Math.floor(m / 60);
  if (h < 48) return `${h}h ${m % 60}m`;
  const d = Math.floor(h / 24);
  return `${d}d ${h % 24}h`;
}

export function fmtAgo(d: Date | null | undefined, now: Date = new Date()): string {
  if (!d) return "—";
  const ms = now.getTime() - d.getTime();
  if (ms < 45_000) return "just now";
  if (ms < 90 * 60_000) return `${Math.round(ms / 60_000)} min ago`;
  if (ms < 36 * 3_600_000) return `${Math.round(ms / 3_600_000)} h ago`;
  return `${Math.round(ms / 86_400_000)} d ago`;
}

export function fmtTime(d: Date, withDate = false): string {
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  if (!withDate) return `${hh}:${mm}`;
  const dd = String(d.getDate()).padStart(2, "0");
  const mo = String(d.getMonth() + 1).padStart(2, "0");
  return `${dd}.${mo}. ${hh}:${mm}`;
}

export function pct(used: number | null, total: number | null): number | null {
  if (used == null || total == null || total <= 0) return null;
  return Math.round((100 * used) / total);
}

/* ---------- disks ---------- */

export type Tone = "ok" | "warn" | "bad" | "unknown";

/** The one-line verdict for a disk's health chip, with the reason. */
export function smartVerdict(d: DiskInfo): { tone: Tone; label: string } {
  const s = d.smart;
  if (!s) return { tone: "unknown", label: "no SMART" };
  if (s.standby) return { tone: "unknown", label: "standby" };
  if (s.error) return { tone: "unknown", label: "SMART error" };
  if (s.passed === false) return { tone: "bad", label: "SMART FAILED" };
  const bad: string[] = [];
  const warn: string[] = [];
  if (s.type === "nvme") {
    if ((s.critical_warning ?? 0) > 0) bad.push("critical warning");
    if ((s.media_errors ?? 0) > 0) warn.push(`${s.media_errors} media errors`);
    if ((s.percentage_used ?? 0) >= 90) bad.push(`${s.percentage_used}% worn`);
    else if ((s.percentage_used ?? 0) >= 70) warn.push(`${s.percentage_used}% worn`);
    if (s.available_spare != null && s.available_spare < 10) bad.push(`spare ${s.available_spare}%`);
  } else if (s.type === "ata") {
    if ((s.reallocated ?? 0) > 0) warn.push(`${s.reallocated} reallocated`);
    if ((s.pending ?? 0) > 0) warn.push(`${s.pending} pending`);
    if ((s.uncorrectable ?? 0) > 0) bad.push(`${s.uncorrectable} uncorrectable`);
  }
  const temp = s.temp_c ?? d.temp_c;
  if (temp != null) {
    const limit = d.rotational ? 50 : 65;
    if (temp > limit) warn.push(`${temp} °C`);
  }
  if (bad.length) return { tone: "bad", label: bad.join(", ") };
  if (warn.length) return { tone: "warn", label: warn.join(", ") };
  return { tone: "ok", label: "PASSED" };
}

/** Fullness tone: the system/DB disk gets the stricter 80 % line. */
export function fillTone(percent: number | null, strict = false): Tone {
  if (percent == null) return "unknown";
  if (percent >= 90) return "bad";
  if (percent >= (strict ? 80 : 85)) return "warn";
  return "ok";
}

/**
 * Least-squares slope over (t, used) → days until the mount is full.
 * Null when the trend is flat or falling, or when there are too few points.
 */
export function fillProjection(
  points: { t: Date; used: number }[],
  size: number
): { daysUntilFull: number | null; bytesPerDay: number | null } {
  if (points.length < 3 || size <= 0) return { daysUntilFull: null, bytesPerDay: null };
  const t0 = points[0].t.getTime();
  const xs = points.map((p) => (p.t.getTime() - t0) / 86_400_000);
  const ys = points.map((p) => p.used);
  const n = xs.length;
  const mx = xs.reduce((a, b) => a + b, 0) / n;
  const my = ys.reduce((a, b) => a + b, 0) / n;
  let num = 0;
  let den = 0;
  for (let i = 0; i < n; i++) {
    num += (xs[i] - mx) * (ys[i] - my);
    den += (xs[i] - mx) ** 2;
  }
  if (den === 0) return { daysUntilFull: null, bytesPerDay: null };
  const slope = num / den; // bytes per day
  if (slope <= 0) return { daysUntilFull: null, bytesPerDay: slope };
  const last = ys[n - 1];
  return { daysUntilFull: (size - last) / slope, bytesPerDay: slope };
}

/* ---------- series / SVG ---------- */

export function niceMax(v: number): number {
  if (v <= 0) return 1;
  const exp = Math.floor(Math.log10(v));
  const base = 10 ** exp;
  const m = v / base;
  const nice = m <= 1 ? 1 : m <= 2 ? 2 : m <= 2.5 ? 2.5 : m <= 5 ? 5 : 10;
  return nice * base;
}

/**
 * SVG path for a series inside a box; a null value breaks the line so a gap
 * in the samples (sampler down, machine off) shows as a gap, not a bridge.
 */
export function seriesPath(
  points: SeriesPoint[],
  from: Date,
  to: Date,
  yMax: number,
  box: { x: number; y: number; w: number; h: number },
  yMin = 0
): string {
  const span = to.getTime() - from.getTime();
  if (span <= 0 || yMax <= yMin) return "";
  let d = "";
  let pen = false;
  for (const p of points) {
    if (p.v == null) {
      pen = false;
      continue;
    }
    const x = box.x + ((p.t.getTime() - from.getTime()) / span) * box.w;
    const clamped = Math.min(Math.max(p.v, yMin), yMax);
    const y = box.y + box.h - ((clamped - yMin) / (yMax - yMin)) * box.h;
    d += `${pen ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`;
    pen = true;
  }
  return d;
}

/**
 * Carry the last known value forward across nulls — for the sparse series
 * that only the full (every-10-minutes) sample fills, so a 5-minute bucket
 * without a full sample does not tear the line.
 */
export function carryForward(points: SeriesPoint[]): SeriesPoint[] {
  let last: number | null = null;
  return points.map((p) => {
    if (p.v != null) last = p.v;
    return { t: p.t, v: last };
  });
}

export function xOf(t: Date, from: Date, to: Date, box: { x: number; w: number }): number {
  const span = to.getTime() - from.getTime();
  return box.x + (Math.min(Math.max(t.getTime(), from.getTime()), to.getTime()) - from.getTime()) / span * box.w;
}

/** Tick times: every 6 h for a day, every day for a week — on round hours. */
export function timeTicks(from: Date, to: Date): Date[] {
  const spanH = (to.getTime() - from.getTime()) / 3_600_000;
  const stepH = spanH <= 30 ? 6 : 24;
  const ticks: Date[] = [];
  const t = new Date(from);
  t.setMinutes(0, 0, 0);
  t.setHours(Math.ceil(t.getHours() / stepH) * stepH);
  while (t.getTime() <= to.getTime()) {
    if (t.getTime() >= from.getTime()) ticks.push(new Date(t));
    t.setHours(t.getHours() + stepH);
  }
  return ticks;
}

export const RANGES = {
  "24h": { hours: 24, bucketSec: 300, label: "24 h" },
  "7d": { hours: 168, bucketSec: 1800, label: "7 d" },
} as const;
export type RangeKey = keyof typeof RANGES;

export function parseRange(v: string | string[] | undefined): RangeKey {
  const s = Array.isArray(v) ? v[0] : v;
  return s === "7d" ? "7d" : "24h";
}

/* ---------- jobs ---------- */

const JOB_PALETTE = [
  "#d4ff3a", "#60a5fa", "#f97316", "#34d399", "#f472b6", "#a78bfa", "#22d3ee", "#fb7185",
  "#c084fc", "#facc15", "#4ade80", "#38bdf8",
];

/** Stable colour per job name (hash → palette), so the same job always looks the same. */
export function jobColor(job: string): string {
  let h = 0;
  for (let i = 0; i < job.length; i++) h = (h * 31 + job.charCodeAt(i)) >>> 0;
  return JOB_PALETTE[h % JOB_PALETTE.length];
}

export function eventDurationMs(ev: OpsEvent, now: Date = new Date()): number {
  return (ev.ended_at ?? now).getTime() - ev.started_at.getTime();
}

/** Human label for how a run ended. */
export function runOutcome(ev: OpsEvent, now: Date = new Date()): { tone: Tone; label: string } {
  if (ev.ended_at == null) {
    const h = eventDurationMs(ev, now) / 3_600_000;
    return h > 6 ? { tone: "warn", label: "running > 6 h" } : { tone: "ok", label: "running" };
  }
  if (ev.rc === 0) return { tone: "ok", label: "ok" };
  if (ev.rc === 75) return { tone: "warn", label: "blocked" };
  // ended_at set but no rc: the process died without an end entry and the
  // sampler closed the row (pipeline.ops_events.close_orphans) — real end unknown.
  if (ev.rc == null) return { tone: "bad", label: "aborted" };
  return { tone: "bad", label: `rc ${ev.rc}` };
}
