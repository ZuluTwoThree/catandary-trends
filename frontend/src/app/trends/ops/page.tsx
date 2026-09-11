import Link from "next/link";
import { notFound } from "next/navigation";
import AutoRefresh from "@/components/ops/AutoRefresh";
import Chart from "@/components/ops/Chart";
import WeekPlan from "@/components/ops/WeekPlan";
import MarkdownBody from "@/components/MarkdownBody";
import {
  RANGES, carryForward, eventDurationMs, fillProjection, fillTone, fmtAgo, fmtBytes, fmtDuration,
  fmtMiB, fmtRate, fmtTime, jobColor, parseRange, pct, runOutcome, smartVerdict,
  type DiskInfo, type OpsEvent, type Sample, type Tone,
} from "@/lib/ops";
import { canOps } from "@/lib/ops-access";
import { collisions, occurrences, parseCrontab, weekStart, type PlannedBlock } from "@/lib/opsCron";
import { readCrontab, readLogbook } from "@/lib/opsFiles";
import { parseDuration, parseLogbook, planStart, sortLogbook, type LogKind } from "@/lib/opsLogbook";
import {
  alerts, diskBusyBuckets, diskFillHistory, eventBands, jobStats, latestFullSample, latestSample,
  openEvents, opsTablesReady, recentEvents, sampleBuckets, samplerHealth,
} from "@/lib/opsDb";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Ops — Catandary",
  robots: { index: false, follow: false },
};

/* ---------- small presentational bits ---------- */

const TONE_TEXT: Record<Tone, string> = {
  ok: "text-rising", warn: "text-warn", bad: "text-declining", unknown: "text-muted",
};
const TONE_BG: Record<Tone, string> = {
  ok: "bg-rising", warn: "bg-warn", bad: "bg-declining", unknown: "bg-border-strong",
};

function Label({ children }: { children: React.ReactNode }) {
  return <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">{children}</div>;
}

function Chip({ tone, children }: { tone: Tone; children: React.ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-[0.12em] ${TONE_TEXT[tone]}`}>
      <span className={`inline-block w-1.5 h-1.5 ${TONE_BG[tone]}`} />
      {children}
    </span>
  );
}

function Bar({ percent, tone }: { percent: number | null; tone: Tone }) {
  return (
    <div className="h-1.5 w-full bg-border">
      <div className={`h-full ${TONE_BG[tone]}`} style={{ width: `${Math.min(100, percent ?? 0)}%` }} />
    </div>
  );
}

function Tile({ title, children, tone }: { title: string; children: React.ReactNode; tone?: Tone }) {
  return (
    <section className={`border p-4 bg-card ${tone === "warn" || tone === "bad" ? "border-warn" : "border-border"}`}>
      <Label>{title}</Label>
      <div className="mt-2 space-y-1 font-sans text-sm text-text">{children}</div>
    </section>
  );
}

function Big({ children }: { children: React.ReactNode }) {
  return <div className="font-display text-[22px] leading-tight text-paper">{children}</div>;
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-3">
      <span className="text-muted">{k}</span>
      <span className="text-right font-mono text-[12px] text-paper">{v}</span>
    </div>
  );
}

const basename = (p: string | null) => (p ? p.split("/").pop() ?? p : "—");

const KIND_CLASS: Record<LogKind, string> = {
  change: "text-rising", plan: "text-accent", decision: "text-paper", idea: "text-muted",
};

/* ---------- sections ---------- */

function NowGrid({ s, full, open, sampler, now }: {
  s: Sample; full: Sample | null; open: OpsEvent[]; sampler: { last: Date | null; rowsToday: number }; now: Date;
}) {
  const vramPct = pct(s.gpu_mem_used_mib, s.gpu_mem_total_mib);
  const memPct = pct(s.mem_used_mib, s.mem_total_mib);
  const samplerAge = sampler.last ? now.getTime() - sampler.last.getTime() : Infinity;
  const samplerTone: Tone = samplerAge > 5 * 60_000 ? "bad" : samplerAge > 3 * 60_000 ? "warn" : "ok";
  const holder = s.gpu_job ?? open.find((e) => e.host === "local")?.job ?? null;
  const remoteTone: Tone = s.remote_backend === "down" ? "unknown" : s.remote_backend ? "ok" : "unknown";
  const tables = full?.tables ? Object.entries(full.tables).slice(0, 4) : [];
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <Tile title="GPU · RTX 3090 (local)">
        <Big>{fmtMiB(s.gpu_mem_used_mib)} <span className="text-muted text-base">/ {fmtMiB(s.gpu_mem_total_mib)}</span></Big>
        <Bar percent={vramPct} tone={vramPct != null && vramPct > 95 ? "warn" : "ok"} />
        <Row k="utilisation" v={s.gpu_util_pct != null ? `${s.gpu_util_pct} %` : "—"} />
        <Row k="temperature · power" v={`${s.gpu_temp_c ?? "—"} °C · ${s.gpu_power_w != null ? Math.round(s.gpu_power_w) : "—"} W`} />
        <Row k="model served" v={basename(s.gpu_model)} />
        <Row k="held by" v={holder ? <span className="text-accent">{holder}</span> : <span className="text-muted">idle</span>} />
      </Tile>
      <Tile title="GPU · RTX 5080 (bequiet)" tone={remoteTone === "unknown" && s.remote_in_window ? undefined : undefined}>
        <Big>
          <Chip tone={remoteTone}>{s.remote_backend ?? "not configured"}</Chip>
        </Big>
        <Row k="window 01:00–17:00" v={s.remote_in_window ? "open" : "closed (owner's time)"} />
        <Row k="model loaded" v={s.remote_model ?? "—"} />
        <div className="text-muted text-xs pt-1">API-only view; VRAM/utilisation not exposed by the model server.</div>
      </Tile>
      <Tile title="CPU · RAM">
        <Big>{s.cpu_pct != null ? `${s.cpu_pct} %` : "—"} <span className="text-muted text-base">cpu</span></Big>
        <Row k="load (1 min)" v={s.load1 ?? "—"} />
        <Row k="memory" v={`${fmtMiB(s.mem_used_mib)} / ${fmtMiB(s.mem_total_mib)}`} />
        <Bar percent={memPct} tone={memPct != null && memPct > 90 ? "warn" : "ok"} />
      </Tile>
      <Tile title="PostgreSQL">
        <Big>{fmtBytes(s.db_size_bytes)}</Big>
        <Row k="connections" v={`${s.db_connections ?? "—"} / ${s.db_max_connections ?? "—"}`} />
        <Row k="queries > 60 s" v={s.db_long_queries ?? "—"} />
        {tables.map(([name, bytes]) => <Row key={name} k={name} v={fmtBytes(bytes)} />)}
      </Tile>
      <Tile title={`Queues${full ? ` · ${fmtTime(full.ts)}` : ""}`}>
        <Row k="backlog (cycle-eligible)" v={full?.backlog_unprocessed?.toLocaleString("en-US") ?? "—"} />
        <Row k="review queue" v={full?.review_queue?.toLocaleString("en-US") ?? "—"} />
        <div className="text-muted text-xs pt-1">Counted every 10 minutes (the expensive ones).</div>
      </Tile>
      <Tile title="Sampler" tone={samplerTone}>
        <Big><Chip tone={samplerTone}>{sampler.last ? fmtAgo(sampler.last, now) : "no samples"}</Chip></Big>
        <Row k="samples · 24 h" v={`${sampler.rowsToday} / 1440`} />
        <Row k="running jobs" v={open.length ? open.map((e) => e.job).join(", ") : "none"} />
        <div className="text-muted text-xs pt-1">catandary-ops-sampler.timer · one row per minute</div>
      </Tile>
    </div>
  );
}

function DiskCard({ d, history, now }: { d: DiskInfo; history: Map<string, { t: Date; used: number; size: number }[]>; now: Date }) {
  const verdict = smartVerdict(d);
  const isSystem = d.mounts.some((m) => m.mount === "/");
  const main = d.mounts.reduce<typeof d.mounts[number] | null>(
    (a, m) => (a == null || m.size_bytes > a.size_bytes ? m : a), null
  );
  const proj = main ? fillProjection((history.get(main.mount) ?? []).map((p) => ({ t: p.t, used: p.used })), main.size_bytes) : null;
  const s = d.smart ?? {};
  const temp = s.temp_c ?? d.temp_c;
  return (
    <section className={`border p-4 bg-card ${verdict.tone === "bad" ? "border-declining" : verdict.tone === "warn" ? "border-warn" : "border-border"}`}>
      <div className="flex items-baseline justify-between gap-2">
        <Label>{d.dev} {isSystem && <span className="text-accent">· system + db</span>}</Label>
        <Chip tone={verdict.tone}>{verdict.label}</Chip>
      </div>
      <div className="font-display text-[16px] text-paper mt-1 truncate" title={d.model ?? ""}>{d.model ?? "unknown model"}</div>
      <div className="mt-2 space-y-2">
        {d.mounts.length === 0 && <div className="text-muted text-xs">not mounted</div>}
        {d.mounts.filter((m) => m.size_bytes > 2 * 1024 ** 3).map((m) => {
          const p = pct(m.used_bytes, m.size_bytes);
          return (
            <div key={m.part}>
              <div className="flex justify-between font-mono text-[11px] text-text">
                <span className="truncate">{m.mount}</span>
                <span>{fmtBytes(m.used_bytes)} / {fmtBytes(m.size_bytes)} · {p ?? "—"} %</span>
              </div>
              <Bar percent={p} tone={fillTone(p, isSystem)} />
            </div>
          );
        })}
      </div>
      <div className="mt-3 space-y-1 font-sans text-sm">
        <Row k="read · write" v={`${fmtRate(d.read_bytes_s)} · ${fmtRate(d.write_bytes_s)}`} />
        <Row k="busy" v={d.busy_pct != null ? `${d.busy_pct} %` : "—"} />
        <Row k="temperature" v={temp != null ? `${temp} °C` : "—"} />
        {s.type === "nvme" && <Row k="wear · spare" v={`${s.percentage_used ?? "—"} % · ${s.available_spare ?? "—"} %`} />}
        {s.type === "ata" && <Row k="reallocated · pending" v={`${s.reallocated ?? "—"} · ${s.pending ?? "—"}`} />}
        {s.power_on_hours != null && <Row k="power-on" v={`${s.power_on_hours.toLocaleString("en-US")} h`} />}
        <Row k="full in" v={
          proj?.daysUntilFull != null
            ? `~${Math.round(proj.daysUntilFull).toLocaleString("en-US")} d (${fmtBytes(proj.bytesPerDay)}/d)`
            : proj?.bytesPerDay != null ? "not growing" : "— (need a few hours of data)"
        } />
      </div>
      <div className="sr-only">{fmtAgo(now, now)}</div>
    </section>
  );
}

function RunsTable({ events, now }: { events: OpsEvent[]; now: Date }) {
  return (
    <div className="overflow-x-auto border border-border bg-card">
      <table className="w-full text-sm font-sans">
        <thead>
          <tr className="text-left font-mono text-[10px] uppercase tracking-[0.14em] text-muted border-b border-border">
            <th className="px-3 py-2">job</th><th className="px-3 py-2">started</th>
            <th className="px-3 py-2">duration</th><th className="px-3 py-2">result</th><th className="px-3 py-2">note</th>
          </tr>
        </thead>
        <tbody>
          {events.length === 0 && (
            <tr><td colSpan={5} className="px-3 py-4 text-muted">No runs recorded yet — the first cron after the merge writes the first row.</td></tr>
          )}
          {events.map((e) => {
            const o = runOutcome(e, now);
            return (
              <tr key={e.id} className="border-b border-border/60">
                <td className="px-3 py-1.5 whitespace-nowrap">
                  <span className="inline-block w-2 h-2 mr-2 align-middle" style={{ background: jobColor(e.job) }} />
                  <span className="text-paper">{e.job}</span>
                  {e.host !== "local" && <span className="text-muted"> · {e.host}</span>}
                </td>
                <td className="px-3 py-1.5 font-mono text-[12px] whitespace-nowrap">{fmtTime(e.started_at, true)}</td>
                <td className="px-3 py-1.5 font-mono text-[12px] whitespace-nowrap">{fmtDuration(eventDurationMs(e, now))}</td>
                <td className="px-3 py-1.5 whitespace-nowrap"><Chip tone={o.tone}>{o.label}</Chip></td>
                <td className="px-3 py-1.5 text-muted text-xs">{e.note ?? ""}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/* ---------- page ---------- */

export default async function OpsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  if (!canOps()) notFound();
  const sp = await searchParams;
  const rangeKey = parseRange(sp.range);
  const range = RANGES[rangeKey];
  const now = new Date();
  const from = new Date(now.getTime() - range.hours * 3_600_000);

  const ready = await opsTablesReady();
  if (!ready) {
    return (
      <main className="mx-auto max-w-6xl px-4 py-10">
        <h1 className="font-display text-3xl text-paper">Ops</h1>
        <p className="mt-4 text-text">The ops tables do not exist yet — run <code className="font-mono">python -c &quot;from pipeline.db import init_db; init_db()&quot;</code> (#104).</p>
      </main>
    );
  }

  const [s, full, buckets, busy, fills, bands, open, events, stats, sampler, al] = await Promise.all([
    latestSample(), latestFullSample(), sampleBuckets(range.hours, range.bucketSec),
    diskBusyBuckets(range.hours, range.bucketSec), diskFillHistory(7), eventBands(range.hours),
    openEvents(), recentEvents(40), jobStats(28), samplerHealth(), alerts(15),
  ]);

  const series = (pick: (b: (typeof buckets)[number]) => number | null) => buckets.map((b) => ({ t: b.t, v: pick(b) }));

  // Week plan: the installed crontab, expanded into this week, each run sized
  // by the job's measured median (10 min until we have one); logbook plans
  // with a day join the grid.
  const wk0 = weekStart(now);
  const wk1 = new Date(wk0);
  wk1.setDate(wk1.getDate() + 7);
  const cron = readCrontab();
  const medianMs = new Map(stats.map((j) => [j.job, (j.median_s ?? 600) * 1000]));
  const cronBlocks: PlannedBlock[] = parseCrontab(cron.text).flatMap((e) =>
    occurrences(e, wk0, wk1).map((o) => ({
      job: o.job, start: o.start, end: new Date(o.start.getTime() + (medianMs.get(o.job) ?? 600_000)), source: "cron" as const,
    }))
  );
  const logbookRaw = readLogbook();
  const logbook = logbookRaw ? sortLogbook(parseLogbook(logbookRaw)) : [];
  const planBlocks: PlannedBlock[] = logbook.flatMap((e) => {
    const st = planStart(e);
    if (!st || st.getTime() < wk0.getTime() || st.getTime() >= wk1.getTime()) return [];
    return [{ job: `plan:${e.title}`, label: e.title, start: st, end: new Date(st.getTime() + (parseDuration(e.meta.duration) ?? 3_600_000)), source: "plan" as const }];
  });
  const weekBlocks = [...cronBlocks, ...planBlocks];
  const clashes = collisions(weekBlocks).filter(([a, b]) => a.source === "plan" || b.source === "plan" || medianMs.has(a.job) && medianMs.has(b.job));
  const jobsInWindow = [...new Set(bands.map((b) => b.job))];
  const sysDisk = s?.disks?.find((d) => d.mounts.some((m) => m.mount === "/"))?.dev ?? "nvme1n1";
  const hdd = s?.disks?.find((d) => d.rotational)?.dev;

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <Label>Owner · not public</Label>
          <h1 className="font-display text-3xl text-paper mt-1">Ops</h1>
          <p className="text-muted text-sm mt-1">What the machine is doing — GPU, disks, database, every job run. One sample per minute, seven days kept.</p>
        </div>
        <div className="flex items-center gap-4">
          <nav className="flex gap-1 font-mono text-[10px] uppercase tracking-[0.14em]">
            {(Object.keys(RANGES) as (keyof typeof RANGES)[]).map((k) => (
              <Link key={k} href={`/trends/ops?range=${k}`}
                    className={`px-2 py-1 border ${k === rangeKey ? "border-accent text-accent" : "border-border text-muted hover:text-paper"}`}>
                {RANGES[k].label}
              </Link>
            ))}
          </nav>
          <AutoRefresh seconds={60} />
        </div>
      </header>

      <section className="space-y-2">
        <Label>Alerts · {al.open.length === 0 ? "none open" : `${al.open.length} open`} · thresholds in ops_alerts.yaml · one mail on raise, one on resolve</Label>
        {al.open.length > 0 && (
          <ul className="border border-warn bg-warn/10 p-3 space-y-1">
            {al.open.map((a) => (
              <li key={a.id} className="flex flex-wrap gap-x-3 text-sm">
                <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-warn self-center">{a.kind}</span>
                <span className="text-paper">{a.message}</span>
                <span className="font-mono text-[11px] text-muted self-center">since {fmtTime(a.raised_at, true)} ({fmtAgo(a.raised_at, now)})</span>
              </li>
            ))}
          </ul>
        )}
        {al.resolved.length > 0 && (
          <details className="text-sm">
            <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-[0.12em] text-muted">last resolved ({al.resolved.length})</summary>
            <ul className="mt-1 space-y-0.5 text-muted">
              {al.resolved.map((a) => (
                <li key={a.id}><span className="font-mono text-[11px]">{fmtTime(a.raised_at, true)} – {a.resolved_at ? fmtTime(a.resolved_at, true) : "?"}</span> · {a.kind} · {a.message}</li>
              ))}
            </ul>
          </details>
        )}
      </section>

      {!s ? (
        <p className="text-warn">No samples yet — is <code className="font-mono">catandary-ops-sampler.timer</code> running?</p>
      ) : (
        <>
          <section className="space-y-3">
            <Label>Now · sample {fmtTime(s.ts)} ({fmtAgo(s.ts, now)})</Label>
            <NowGrid s={s} full={full} open={open} sampler={sampler} now={now} />
          </section>

          <section className="space-y-3">
            <Label>Disks{full ? ` · SMART ${fmtTime(full.ts)}` : ""}</Label>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {(full?.disks ?? s.disks ?? []).map((d) => {
                // live I/O from the latest sample, SMART from the latest full one
                const live = s.disks?.find((x) => x.dev === d.dev);
                const merged: DiskInfo = { ...d, ...(live ? { read_bytes_s: live.read_bytes_s, write_bytes_s: live.write_bytes_s, busy_pct: live.busy_pct, mounts: live.mounts, temp_c: live.temp_c } : {}) };
                return <DiskCard key={d.dev} d={merged} history={fills} now={now} />;
              })}
            </div>
          </section>
        </>
      )}

      <section className="space-y-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <Label>Last {range.label} · bands = job runs</Label>
          <div className="flex flex-wrap gap-x-3 gap-y-1 font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
            {jobsInWindow.length === 0 && <span>no runs in window</span>}
            {jobsInWindow.map((j) => (
              <span key={j} className="inline-flex items-center gap-1">
                <span className="inline-block w-2 h-2" style={{ background: jobColor(j) }} />{j}
              </span>
            ))}
          </div>
        </div>
        <div className="grid gap-3 lg:grid-cols-2">
          <Chart title="GPU memory" unit="GB" from={from} to={now} bands={bands}
                 yMax={s?.gpu_mem_total_mib ?? 24576} format={(v) => (v / 1024).toFixed(0)}
                 series={[{ label: "vram", points: series((b) => b.vram) }]}
                 current={s ? fmtMiB(s.gpu_mem_used_mib) : undefined} />
          <Chart title="GPU utilisation" unit="%" from={from} to={now} bands={bands} yMax={100}
                 series={[{ label: "gpu", points: series((b) => b.gpu_util) }]}
                 current={s?.gpu_util_pct != null ? `${s.gpu_util_pct} %` : undefined} />
          <Chart title="GPU temperature" unit="°C" from={from} to={now} bands={bands} yMax={100} guide={88}
                 series={[{ label: "temp", points: series((b) => b.gpu_temp), color: "#fb7185" }]}
                 current={s?.gpu_temp_c != null ? `${s.gpu_temp_c} °C` : undefined} />
          <Chart title="CPU" unit="%" from={from} to={now} bands={bands} yMax={100}
                 series={[{ label: "cpu", points: series((b) => b.cpu), color: "#60a5fa" }]}
                 current={s?.cpu_pct != null ? `${s.cpu_pct} %` : undefined} />
          <Chart title="Disk busy" unit="%" from={from} to={now} bands={bands} yMax={100}
                 series={[
                   { label: sysDisk, points: busy.get(sysDisk) ?? [], color: "#d4ff3a" },
                   ...(hdd ? [{ label: hdd, points: busy.get(hdd) ?? [], color: "#f97316" }] : []),
                 ]} />
          <Chart title="Memory" unit="GB" from={from} to={now} bands={bands}
                 yMax={s?.mem_total_mib ?? undefined} format={(v) => (v / 1024).toFixed(0)}
                 series={[{ label: "ram", points: series((b) => b.mem), color: "#a78bfa" }]}
                 current={s ? fmtMiB(s.mem_used_mib) : undefined} />
          <Chart title="Database size" unit="GB" from={from} to={now} bands={bands} yAuto
                 format={(v) => (v / 1024 ** 3).toFixed(1)}
                 series={[{ label: "db", points: series((b) => b.db_size), color: "#34d399" }]}
                 current={s ? fmtBytes(s.db_size_bytes) : undefined} />
          <Chart title="Backlog · review queue" unit="entries" from={from} to={now} bands={bands}
                 series={[
                   { label: "backlog", points: carryForward(series((b) => b.backlog)), color: "#d4ff3a" },
                   { label: "review", points: carryForward(series((b) => b.review)), color: "#f472b6" },
                 ]} />
        </div>
      </section>

      <section className="space-y-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <Label>Week plan · {fmtTime(wk0, true).slice(0, 6)} – {fmtTime(new Date(wk1.getTime() - 1), true).slice(0, 6)} · from {cron.source === "crontab" ? "the installed crontab" : cron.source === "template" ? "deploy/crontab.txt (crontab -l unavailable)" : "nothing — no crontab found"}</Label>
          <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">block width = median duration of the last 28 days (10 min until measured)</span>
        </div>
        <WeekPlan weekStart={wk0} blocks={weekBlocks} now={now} />
        {clashes.length > 0 && (
          <div className="border border-warn/60 bg-card p-3 text-sm">
            <Label>Overlaps this week</Label>
            <ul className="mt-2 space-y-1 font-mono text-[12px] text-text">
              {clashes.slice(0, 12).map(([a, b], i) => (
                <li key={i}>
                  <span className="text-muted">{fmtTime(a.start, true)}</span> {a.label ?? a.job}
                  <span className="text-muted"> overlaps </span>
                  <span className="text-muted">{fmtTime(b.start, true)}</span> {b.label ?? b.job}
                </li>
              ))}
              {clashes.length > 12 && <li className="text-muted">… {clashes.length - 12} more</li>}
            </ul>
            <p className="text-muted text-xs mt-2">Overlaps between measured cron jobs and planned runs. The GPU guard serialises GPU jobs anyway — an overlap means waiting, not breakage.</p>
          </div>
        )}
      </section>

      <section className="space-y-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <Label>Logbook · docs/ops/logbook.md</Label>
          <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">edit in the repo, commit — the page reads the file</span>
        </div>
        {logbook.length === 0 ? (
          <p className="text-muted text-sm">No logbook yet — create <code className="font-mono">docs/ops/logbook.md</code> with <code className="font-mono">## YYYY-MM-DD · change|plan|decision|idea · title</code> headings.</p>
        ) : (
          <ol className="space-y-3">
            {logbook.map((e) => (
              <li key={`${e.line}`} className={`border p-4 bg-card ${e.kind === "plan" ? "border-accent/60" : "border-border"}`}>
                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  <span className="font-mono text-[11px] text-paper">{e.date}{e.time ? ` ${e.time}` : ""}</span>
                  <span className={`font-mono text-[10px] uppercase tracking-[0.14em] ${KIND_CLASS[e.kind]}`}>{e.kind}</span>
                  <span className="font-display text-[17px] text-paper">{e.title}</span>
                  {Object.entries(e.meta).map(([k, v]) => (
                    <span key={k} className="font-mono text-[10px] text-muted">{k}: {v}</span>
                  ))}
                </div>
                {e.body && <div className="mt-2 [&_p]:text-[14px] [&_p]:leading-[1.6]"><MarkdownBody source={e.body} /></div>}
              </li>
            ))}
          </ol>
        )}
      </section>

      <section className="space-y-3">
        <Label>Jobs · last 28 days</Label>
        <div className="overflow-x-auto border border-border bg-card">
          <table className="w-full text-sm font-sans">
            <thead>
              <tr className="text-left font-mono text-[10px] uppercase tracking-[0.14em] text-muted border-b border-border">
                <th className="px-3 py-2">job</th><th className="px-3 py-2">runs</th>
                <th className="px-3 py-2">median duration</th><th className="px-3 py-2">last run</th><th className="px-3 py-2">last result</th>
              </tr>
            </thead>
            <tbody>
              {stats.length === 0 && (
                <tr><td colSpan={5} className="px-3 py-4 text-muted">Nothing recorded in the last 28 days.</td></tr>
              )}
              {stats.map((j) => {
                const tone: Tone = j.last_rc == null ? "ok" : j.last_rc === 0 ? "ok" : j.last_rc === 75 ? "warn" : "bad";
                const label = j.last_rc == null ? "running" : j.last_rc === 0 ? "ok" : j.last_rc === 75 ? "blocked" : `rc ${j.last_rc}`;
                return (
                  <tr key={j.job} className="border-b border-border/60">
                    <td className="px-3 py-1.5 whitespace-nowrap">
                      <span className="inline-block w-2 h-2 mr-2 align-middle" style={{ background: jobColor(j.job) }} />
                      <span className="text-paper">{j.job}</span>
                    </td>
                    <td className="px-3 py-1.5 font-mono text-[12px]">{j.runs}</td>
                    <td className="px-3 py-1.5 font-mono text-[12px]">{j.median_s != null ? fmtDuration(j.median_s * 1000) : "—"}</td>
                    <td className="px-3 py-1.5 font-mono text-[12px] whitespace-nowrap">{fmtTime(j.last_started, true)}{j.last_s != null ? ` · ${fmtDuration(j.last_s * 1000)}` : ""}</td>
                    <td className="px-3 py-1.5"><Chip tone={tone}>{label}</Chip></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className="space-y-3">
        <Label>Runs · last 40</Label>
        <RunsTable events={events} now={now} />
      </section>

      <footer className="text-muted text-xs">
        Sampler: <code className="font-mono">scripts/ops_sampler.py</code> · events: <code className="font-mono">scripts/lib/ops_events.sh</code>, <code className="font-mono">pipeline/ops_events.py</code> · Issue #104. Alerts: <code className="font-mono">pipeline/ops_alerts.py</code>, thresholds <code className="font-mono">ops_alerts.yaml</code>.
      </footer>
    </main>
  );
}
