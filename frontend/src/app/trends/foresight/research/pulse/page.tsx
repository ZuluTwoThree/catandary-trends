import Link from "next/link";
import { getPulseOverview, getPulseWeeks } from "@/lib/db";
import { MEGA_TRENDS } from "@/lib/mega-trends.generated";
import { isoWeekRangeLabel } from "@/lib/newsletterEditions";
import {
  firstSentence, parsePulseWeek, pulsePath, pulseWeekSlug, ratioLabel, ratioTone,
  sparkBars, type PulseRow,
} from "@/lib/researchPulse";
import { pulseWorkerStatus } from "@/lib/researchPulseWorker";
import { NOTICE, TONE_ARROW, TONE_CLASS, fmtStamp } from "./ui";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Research Pulse — Catandary Foresight",
  description:
    "Weekly synthesis per signal theme: fresh research volume against the prior month, emergent embedding clusters, top papers.",
  robots: { index: false, follow: false },
};

const fmtInt = (n: number) => n.toLocaleString("en-US");

function Spark({ row }: { row: PulseRow }) {
  const bars = sparkBars(row.stats);
  return (
    <div className="flex items-end gap-[3px] h-7" role="img"
         aria-label={`Weekly papers: ${bars.map((b) => `${b.label} ${b.n}`).join(", ")}`}>
      {bars.map((b) => (
        <div key={b.label} title={`${b.label}: ${fmtInt(b.n)} papers`}
             className={`w-[7px] ${b.current ? "bg-accent" : "bg-border-strong"}`}
             style={{ height: `${Math.max(2, Math.round(b.h * 28))}px` }} />
      ))}
    </div>
  );
}

function ThemeCard({ row, week }: { row: PulseRow; week: { year: number; week: number } }) {
  const info = MEGA_TRENDS.find((m) => m.key === row.theme);
  const tone = ratioTone(row.stats.ratio);
  const excerpt = firstSentence(row.text);
  const emerging = row.clusters.filter((c) => c.emerging).length;
  return (
    <li className="flex flex-col bg-ink p-4 gap-3">
      <div className="flex items-start justify-between gap-3">
        <Link href={pulsePath(row.theme, week)}
              className="font-display text-[18px] leading-[1.25] text-paper hover:text-accent">
          {info?.icon && <span className="mr-2" aria-hidden="true">{info.icon}</span>}
          {info?.name_en ?? row.theme}
        </Link>
        <Spark row={row} />
      </div>
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
        <span><span className="text-paper text-sm">{fmtInt(row.stats.week_n)}</span> papers</span>
        <span className={TONE_CLASS[tone]} title="This week against the median of the prior four weeks">
          {TONE_ARROW[tone]} {ratioLabel(row.stats.ratio)}
        </span>
        {emerging > 0 && (
          <span className="text-accent" title="Clusters at ≥1.5× their prior weekly mean (min. 5 papers)">
            {emerging} emerging
          </span>
        )}
      </div>
      {excerpt ? (
        <p className="font-sans text-[13px] leading-relaxed text-text">{excerpt}</p>
      ) : (
        <p className="font-sans text-[12px] text-muted">
          {row.note?.startsWith("no-llm") ? "Statistics and clusters only — no paragraph in this run."
            : row.stats.week_n === 0 ? "No fresh papers classified into this theme this week."
            : row.note ?? "No paragraph."}
        </p>
      )}
      <Link href={pulsePath(row.theme, week)}
            className="mt-auto font-mono text-[10px] uppercase tracking-[0.14em] text-accent hover:underline">
        clusters + papers →
      </Link>
    </li>
  );
}

export default async function ResearchPulsePage({
  searchParams,
}: {
  searchParams: Promise<{ week?: string; worker?: string }>;
}) {
  const sp = await searchParams;
  const weeks = await getPulseWeeks();
  const requested = parsePulseWeek(sp.week);
  const week = requested && weeks.some((w) => w.year === requested.year && w.week === requested.week)
    ? requested
    : weeks[0] ?? requested ?? null;
  const rows = week ? await getPulseOverview(week.year, week.week) : [];
  rows.sort((a, b) => b.stats.week_n - a.stats.week_n || a.theme.localeCompare(b.theme));
  const worker = pulseWorkerStatus();
  const notice = sp.worker ? NOTICE[sp.worker] : undefined;
  const models = Array.from(new Set(rows.map((r) => r.model).filter(Boolean))) as string[];
  const latest = rows.reduce<string | null>((m, r) => (!m || r.computed_at > m ? r.computed_at : m), null);
  const withText = rows.filter((r) => r.text).length;
  const covered = new Set(rows.map((r) => r.theme));
  const missing = MEGA_TRENDS.filter((m) => !covered.has(m.key));

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <nav className="flex items-center gap-3 font-mono text-[10px] uppercase tracking-[0.14em] text-muted mb-8">
        <Link href="/trends/foresight" className="hover:text-paper transition-colors">Foresight</Link>
        <span className="text-border">/</span>
        <Link href="/trends/foresight/research" className="hover:text-paper transition-colors">Research Explorer</Link>
        <span className="text-border">/</span>
        <span className="text-paper">Pulse</span>
      </nav>

      <div className="mb-8">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-4">
          —— What research moved this week
        </div>
        <h1 className="font-display text-4xl md:text-[44px] leading-[1.05] tracking-tight text-paper mb-4">
          Research <span className="italic">Pulse</span>
        </h1>
        <p className="font-sans text-text text-lg leading-relaxed max-w-2xl">
          One week of fresh papers per signal theme: volume against the prior
          four-week median, embedding clusters with their growth, the papers
          closest to each cluster, and a sober paragraph written from those
          numbers. A dated document — recomputed by the Saturday run or on your
          click, never silently.
        </p>
      </div>

      {notice && (
        <p className={`mb-6 border px-4 py-3 font-sans text-[13px] ${notice.warn ? "border-warn/60 text-warn" : "border-accent/50 text-accent"}`}>
          {notice.text}
        </p>
      )}
      {worker.running && (
        <p className="mb-6 font-mono text-[11px] text-muted">
          pulse run in progress{worker.theme ? ` · ${worker.theme}` : ""} · started {fmtStamp(worker.startedAt)}
        </p>
      )}

      {weeks.length === 0 ? (
        <div className="border border-dashed border-border p-6 font-sans text-sm text-muted max-w-2xl">
          <p className="text-paper mb-2">No pulse computed yet.</p>
          <p>
            Run it on the workstation:{" "}
            <span className="font-mono text-[12px]">.venv/bin/python scripts/research_pulse.py</span>{" "}
            (previous ISO week, all 28 themes; <span className="font-mono text-[12px]">--no-llm</span> for
            statistics and clusters only). The table <span className="font-mono text-[12px]">research_pulse</span>{" "}
            is created by <span className="font-mono text-[12px]">scripts/migrate_research_pulse.py</span>.
          </p>
        </div>
      ) : (
        <>
          <div className="mb-6 flex flex-wrap items-baseline gap-x-3 gap-y-2 font-mono text-[10px] uppercase tracking-[0.12em]">
            <span className="text-muted">Week</span>
            {weeks.map((w) => {
              const active = week && w.year === week.year && w.week === week.week;
              return (
                <Link key={pulseWeekSlug(w.year, w.week)} href={pulsePath(undefined, w)}
                      className={`border px-2 py-0.5 ${active ? "border-accent text-accent bg-accent/10" : "border-border text-muted hover:text-paper hover:border-paper"}`}
                      title={`${isoWeekRangeLabel(w.year, w.week)} · ${w.themes} themes`}>
                  {w.year}-W{String(w.week).padStart(2, "0")}
                </Link>
              );
            })}
          </div>

          {week && (
            <div className="mb-5 border border-border-strong px-4 py-3 flex flex-wrap gap-x-6 gap-y-1 font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
              <span><span className="text-paper">{isoWeekRangeLabel(week.year, week.week)}</span> · papers by publication date</span>
              <span>{rows.length} themes · {withText} with paragraph</span>
              <span>computed {fmtStamp(latest)}</span>
              {models.length > 0 && <span title="Paragraphs by">model {models.join(", ")}</span>}
              <span>clusters: k-means on 1024-d embeddings, fixed seed</span>
            </div>
          )}

          {rows.length === 0 ? (
            <p className="font-sans text-sm text-muted border border-dashed border-border p-6">
              No themes computed for this week.
            </p>
          ) : (
            <ul className="grid gap-px bg-border md:grid-cols-2">
              {rows.map((r) => <ThemeCard key={r.theme} row={r} week={week!} />)}
            </ul>
          )}

          {missing.length > 0 && rows.length > 0 && (
            <p className="mt-6 font-sans text-[12px] text-muted">
              Not computed for this week: {missing.map((m) => m.name_en).join(", ")}.
            </p>
          )}
        </>
      )}

      <p className="mt-10 font-sans text-[13px] text-muted max-w-3xl border-t border-dashed border-border pt-4">
        Data: the curated research signal layer (arXiv/bioRxiv/medRxiv preprints,
        the weekly OpenAlex fresh sweep, journal feeds), classified into the 28
        signal themes and embedded on ingest. Volume = papers published in the
        ISO week; baseline = median of the four prior weeks. Clusters = k-means
        (k ≤ 5, fixed seed) on the week&apos;s embeddings; growth = this week&apos;s
        cluster size over the mean weekly count of prior-week papers nearest to
        the same centroid. The paragraph is generated locally (Gemma-4-26B,
        temperature 0.2, fixed seed) from exactly these numbers — no
        forecasts. Method: docs/research_pulse.md.
      </p>
    </div>
  );
}
