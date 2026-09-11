/**
 * Queries for the ops dashboard (#104). Reads `ops_samples` (one row per
 * minute, written by scripts/ops_sampler.py) and `ops_events` (one row per
 * job run). Everything is aggregated in SQL — the page never pulls 10,000
 * raw rows through Node.
 */
import { q, q1 } from "./pg";
import type { Band, JobStat, OpsEvent, Sample, SeriesPoint } from "./ops";

const num = (v: unknown): number | null =>
  v == null ? null : Number.isFinite(Number(v)) ? Number(v) : null;

function toSample(r: Record<string, unknown>): Sample {
  return {
    ts: new Date(r.ts as string),
    is_full: Boolean(r.is_full),
    gpu_mem_used_mib: num(r.gpu_mem_used_mib),
    gpu_mem_total_mib: num(r.gpu_mem_total_mib),
    gpu_util_pct: num(r.gpu_util_pct),
    gpu_temp_c: num(r.gpu_temp_c),
    gpu_power_w: num(r.gpu_power_w),
    gpu_model: (r.gpu_model as string) ?? null,
    gpu_job: (r.gpu_job as string) ?? null,
    remote_backend: (r.remote_backend as string) ?? null,
    remote_in_window: r.remote_in_window == null ? null : Boolean(r.remote_in_window),
    remote_model: (r.remote_model as string) ?? null,
    cpu_pct: num(r.cpu_pct),
    load1: num(r.load1),
    mem_used_mib: num(r.mem_used_mib),
    mem_total_mib: num(r.mem_total_mib),
    db_size_bytes: num(r.db_size_bytes),
    db_connections: num(r.db_connections),
    db_max_connections: num(r.db_max_connections),
    db_long_queries: num(r.db_long_queries),
    disks: (r.disks as Sample["disks"]) ?? null,
    tables: (r.tables as Sample["tables"]) ?? null,
    backlog_unprocessed: num(r.backlog_unprocessed),
    review_queue: num(r.review_queue),
    fulltext_vectors_missing: num(r.fulltext_vectors_missing),
  };
}

function toEvent(r: Record<string, unknown>): OpsEvent {
  return {
    id: Number(r.id),
    job: String(r.job),
    host: String(r.host ?? "local"),
    started_at: new Date(r.started_at as string),
    ended_at: r.ended_at ? new Date(r.ended_at as string) : null,
    rc: num(r.rc),
    note: (r.note as string) ?? null,
  };
}

export async function opsTablesReady(): Promise<boolean> {
  const r = await q1<{ ok: boolean }>(
    "SELECT to_regclass('public.ops_samples') IS NOT NULL AND to_regclass('public.ops_events') IS NOT NULL AS ok"
  );
  return Boolean(r?.ok);
}

export async function latestSample(): Promise<Sample | null> {
  const r = await q1("SELECT * FROM ops_samples ORDER BY ts DESC LIMIT 1");
  return r ? toSample(r) : null;
}

export async function latestFullSample(): Promise<Sample | null> {
  const r = await q1("SELECT * FROM ops_samples WHERE is_full ORDER BY ts DESC LIMIT 1");
  return r ? toSample(r) : null;
}

export interface BucketRow {
  t: Date;
  vram: number | null;
  gpu_util: number | null;
  gpu_temp: number | null;
  gpu_power: number | null;
  cpu: number | null;
  mem: number | null;
  db_size: number | null;
  backlog: number | null;
  ftm: number | null;
  review: number | null;
  connections: number | null;
}

/** Time-bucketed aggregates for the charts (max for "how full", avg for "how busy"). */
export async function sampleBuckets(hours: number, bucketSec: number): Promise<BucketRow[]> {
  const rows = await q<Record<string, unknown>>(
    `SELECT to_timestamp(floor(extract(epoch FROM ts) / $2) * $2) AS t,
            max(gpu_mem_used_mib)        AS vram,
            avg(gpu_util_pct)            AS gpu_util,
            max(gpu_temp_c)              AS gpu_temp,
            avg(gpu_power_w)             AS gpu_power,
            avg(cpu_pct)                 AS cpu,
            max(mem_used_mib)            AS mem,
            max(db_size_bytes)           AS db_size,
            max(backlog_unprocessed)     AS backlog,
            max(fulltext_vectors_missing) AS ftm,
            max(review_queue)            AS review,
            max(db_connections)          AS connections
       FROM ops_samples
      WHERE ts > now() - ($1 || ' hours')::interval
      GROUP BY 1 ORDER BY 1`,
    [String(hours), bucketSec]
  );
  return rows.map((r) => ({
    t: new Date(r.t as string),
    vram: num(r.vram), gpu_util: num(r.gpu_util), gpu_temp: num(r.gpu_temp), gpu_power: num(r.gpu_power),
    cpu: num(r.cpu), mem: num(r.mem), db_size: num(r.db_size), backlog: num(r.backlog),
    ftm: num(r.ftm), review: num(r.review), connections: num(r.connections),
  }));
}

/** Per-device busy % per bucket, from the disks JSON. */
export async function diskBusyBuckets(hours: number, bucketSec: number): Promise<Map<string, SeriesPoint[]>> {
  const rows = await q<{ t: string; dev: string; busy: string | null }>(
    `SELECT to_timestamp(floor(extract(epoch FROM s.ts) / $2) * $2) AS t,
            x->>'dev' AS dev,
            avg((x->>'busy_pct')::float) AS busy
       FROM ops_samples s, jsonb_array_elements(s.disks) x
      WHERE s.ts > now() - ($1 || ' hours')::interval
      GROUP BY 1, 2 ORDER BY 1`,
    [String(hours), bucketSec]
  );
  const out = new Map<string, SeriesPoint[]>();
  for (const r of rows) {
    if (!out.has(r.dev)) out.set(r.dev, []);
    out.get(r.dev)!.push({ t: new Date(r.t), v: num(r.busy) });
  }
  return out;
}

export interface FillPoint {
  t: Date;
  mount: string;
  used: number;
  size: number;
}

/** Hourly used-bytes per mount over the last week — input for the fill projection. */
export async function diskFillHistory(days = 7): Promise<Map<string, FillPoint[]>> {
  const rows = await q<{ t: string; mount: string; used: string; size: string }>(
    `SELECT date_trunc('hour', s.ts) AS t, m->>'mount' AS mount,
            max((m->>'used_bytes')::bigint) AS used, max((m->>'size_bytes')::bigint) AS size
       FROM ops_samples s, jsonb_array_elements(s.disks) d, jsonb_array_elements(d->'mounts') m
      WHERE s.ts > now() - ($1 || ' days')::interval
      GROUP BY 1, 2 ORDER BY 1`,
    [String(days)]
  );
  const out = new Map<string, FillPoint[]>();
  for (const r of rows) {
    if (!out.has(r.mount)) out.set(r.mount, []);
    out.get(r.mount)!.push({ t: new Date(r.t), mount: r.mount, used: Number(r.used), size: Number(r.size) });
  }
  return out;
}

export async function recentEvents(limit = 40): Promise<OpsEvent[]> {
  const rows = await q<Record<string, unknown>>(
    "SELECT * FROM ops_events ORDER BY started_at DESC LIMIT $1", [limit]
  );
  return rows.map(toEvent);
}

export async function openEvents(): Promise<OpsEvent[]> {
  const rows = await q<Record<string, unknown>>(
    "SELECT * FROM ops_events WHERE ended_at IS NULL ORDER BY started_at"
  );
  return rows.map(toEvent);
}

/** Runs overlapping the chart window, as bands. */
export async function eventBands(hours: number): Promise<Band[]> {
  const rows = await q<Record<string, unknown>>(
    `SELECT job, started_at, ended_at, rc FROM ops_events
      WHERE started_at > now() - ($1 || ' hours')::interval
         OR (ended_at IS NULL) OR ended_at > now() - ($1 || ' hours')::interval
      ORDER BY started_at`,
    [String(hours)]
  );
  return rows.map((r) => ({
    job: String(r.job),
    start: new Date(r.started_at as string),
    end: r.ended_at ? new Date(r.ended_at as string) : null,
    rc: num(r.rc),
  }));
}

/** Per job: runs in the last `days`, median duration of finished runs, last run. */
export async function jobStats(days = 28): Promise<JobStat[]> {
  const rows = await q<Record<string, unknown>>(
    `WITH e AS (
       SELECT job, started_at, ended_at, rc,
              extract(epoch FROM (ended_at - started_at)) AS secs
         FROM ops_events WHERE started_at > now() - ($1 || ' days')::interval
     ), last AS (
       SELECT DISTINCT ON (job) job, started_at AS last_started, rc AS last_rc, secs AS last_s
         FROM e ORDER BY job, started_at DESC
     )
     SELECT e.job, count(*) AS runs,
            percentile_cont(0.5) WITHIN GROUP (ORDER BY e.secs) FILTER (WHERE e.ended_at IS NOT NULL AND e.rc = 0) AS median_s,
            l.last_started, l.last_rc, l.last_s
       FROM e JOIN last l USING (job)
      GROUP BY e.job, l.last_started, l.last_rc, l.last_s
      ORDER BY l.last_started DESC`,
    [String(days)]
  );
  return rows.map((r) => ({
    job: String(r.job),
    runs: Number(r.runs),
    median_s: num(r.median_s),
    last_started: new Date(r.last_started as string),
    last_rc: num(r.last_rc),
    last_s: num(r.last_s),
  }));
}

export async function samplerHealth(): Promise<{ last: Date | null; rowsToday: number }> {
  const r = await q1<{ last: string | null; n: string }>(
    "SELECT max(ts) AS last, count(*) FILTER (WHERE ts > now() - interval '24 hours') AS n FROM ops_samples"
  );
  return { last: r?.last ? new Date(r.last) : null, rowsToday: Number(r?.n ?? 0) };
}
