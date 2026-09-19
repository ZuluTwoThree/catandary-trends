import Link from "next/link";
import { notFound } from "next/navigation";
import { getPulseTheme, getPulseThemeWeeks, getPulseWeeks } from "@/lib/db";
import { canReview } from "@/lib/review-access";
import { MEGA_TRENDS } from "@/lib/mega-trends.generated";
import { isoWeekRangeLabel } from "@/lib/newsletterEditions";
import {
  growthLabel, parsePulseWeek, pulsePath, pulseWeekSlug, ratioLabel, ratioTone,
  sparkBars, type PulseCluster,
} from "@/lib/researchPulse";
import { pulseWorkerStatus } from "@/lib/researchPulseWorker";
import { megaTrendSlug } from "@/lib/types";
import { safeHref } from "@/lib/safeHref";
import { recomputePulseAction } from "../actions";
import { NOTICE, TONE_ARROW, TONE_CLASS, fmtStamp } from "../ui";

export const dynamic = "force-dynamic";

const fmtInt = (n: number) => n.toLocaleString("en-US");

const SOURCE_LABEL: Record<string, string> = {
  preprints: "preprints", openalex: "OpenAlex works", journals: "journal & press feeds",
};

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", { day: "numeric", month: "short", year: "numeric" });
}

export async function generateMetadata({ params }: { params: Promise<{ theme: string }> }) {
  const { theme } = await params;
  const info = MEGA_TRENDS.find((m) => m.key === theme);
  return {
    title: `${info?.name_en ?? theme} — Research Pulse`,
    robots: { index: false, follow: false },
  };
}

const BTN = "border px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.14em]";

function explorerHref(theme: string, concept?: string): string {
  const u = new URLSearchParams({ theme });
  if (concept) u.set("concept", concept);
  return `/trends/foresight/research?${u.toString()}`;
}

function Cluster({ c, theme }: { c: PulseCluster; theme: string }) {
  return (
    <li className="border border-border p-4">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 mb-2">
        <h3 className="font-display text-[19px] leading-snug text-paper">{c.label}</h3>
        <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
          {fmtInt(c.n)} papers · {Math.round(c.share * 100)}%
        </span>
        <span className={`font-mono text-[10px] uppercase tracking-[0.12em] ${c.emerging ? "text-accent" : "text-muted"}`}
              title={c.prior_weekly_mean !== null
                ? `Prior four weeks: ${c.prior_n} papers nearest this centroid (${c.prior_weekly_mean}/week)`
                : "No prior-week papers near this centroid"}>
          growth {growthLabel(c.growth)}{c.emerging ? " · emerging" : ""}
        </span>
      </div>
      {(c.terms.length > 0 || c.concepts.length > 0) && (
        <div className="flex flex-wrap gap-1.5 mb-3 font-mono text-[10px] uppercase tracking-[0.1em]">
          {c.terms.map((t) => (
            <span key={t} className="border border-border text-text px-1.5 py-0.5">{t}</span>
          ))}
          {c.concepts.map(([name, n]) => (
            <Link key={name} href={explorerHref(theme, name)}
                  className="border border-accent/40 text-accent px-1.5 py-0.5 hover:bg-accent/10"
                  title={`${n} of these papers carry the concept "${name}" — open in the Research Explorer`}>
              {name} · {n}
            </Link>
          ))}
        </div>
      )}
      <ol className="divide-y divide-border">
        {c.papers.map((p) => {
          const href = safeHref(p.url);
          return (
            <li key={p.trend_id} className="py-2">
              {href ? (
                <a href={href} target="_blank" rel="noopener noreferrer"
                   className="font-sans text-[14px] leading-snug text-paper hover:text-accent">
                  {p.title}
                </a>
              ) : (
                <span className="font-sans text-[14px] leading-snug text-paper">{p.title}</span>
              )}
              <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted mt-0.5 flex flex-wrap gap-x-3">
                <span className="text-text">{fmtDate(p.published)}</span>
                {p.source && <span>{p.source}</span>}
                {p.oa && (
                  <span className="border border-accent/50 text-accent px-1 leading-[14px]"
                        title="Open access — preprint server">OA</span>
                )}
                <span title="Cosine similarity to the cluster centroid">sim {p.sim.toFixed(2)}</span>
              </div>
            </li>
          );
        })}
      </ol>
    </li>
  );
}

export default async function ResearchPulseThemePage({
  params, searchParams,
}: {
  params: Promise<{ theme: string }>;
  searchParams: Promise<{ week?: string; worker?: string }>;
}) {
  const { theme } = await params;
  const sp = await searchParams;
  const info = MEGA_TRENDS.find((m) => m.key === theme);
  if (!info) notFound();

  const [themeWeeks, allWeeks] = await Promise.all([getPulseThemeWeeks(theme), getPulseWeeks()]);
  const requested = parsePulseWeek(sp.week);
  const week = requested ?? themeWeeks[0] ?? allWeeks[0] ?? null;
  const row = week ? await getPulseTheme(theme, week.year, week.week) : null;
  const worker = pulseWorkerStatus();
  const notice = sp.worker ? NOTICE[sp.worker] : undefined;
  const owner = canReview();
  const tone = row ? ratioTone(row.stats.ratio) : "none";

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <nav className="flex flex-wrap items-center gap-3 font-mono text-[10px] uppercase tracking-[0.14em] text-muted mb-8">
        <Link href="/trends/foresight" className="hover:text-paper transition-colors">Foresight</Link>
        <span className="text-border">/</span>
        <Link href="/trends/foresight/research" className="hover:text-paper transition-colors">Research Explorer</Link>
        <span className="text-border">/</span>
        <Link href={pulsePath(undefined, week)} className="hover:text-paper transition-colors">Pulse</Link>
        <span className="text-border">/</span>
        <span className="text-paper">{info.name_en}</span>
      </nav>

      <div className="mb-6">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-4">
          —— Research Pulse · {week ? isoWeekRangeLabel(week.year, week.week) : "no week"}
        </div>
        <h1 className="font-display text-4xl md:text-[44px] leading-[1.05] tracking-tight text-paper mb-3">
          {info.icon && <span className="mr-3" aria-hidden="true">{info.icon}</span>}
          {info.name_en}
        </h1>
        <p className="font-sans text-text text-base leading-relaxed max-w-2xl">{info.description_en}</p>
        <div className="mt-4 flex flex-wrap gap-x-5 gap-y-1 font-mono text-[10px] uppercase tracking-[0.14em]">
          <Link href={explorerHref(theme)} className="text-accent hover:underline">
            all signals of this theme in the Explorer →
          </Link>
          <Link href={`/trends/mega/${megaTrendSlug(theme)}`} className="text-accent/80 hover:text-accent hover:underline">
            theme page →
          </Link>
        </div>
      </div>

      {notice && (
        <p className={`mb-6 border px-4 py-3 font-sans text-[13px] ${notice.warn ? "border-warn/60 text-warn" : "border-accent/50 text-accent"}`}>
          {notice.text}
        </p>
      )}

      <div className="mb-6 flex flex-wrap items-baseline gap-x-3 gap-y-2 font-mono text-[10px] uppercase tracking-[0.12em]">
        <span className="text-muted">Week</span>
        {(themeWeeks.length > 0 ? themeWeeks : allWeeks).map((w) => {
          const active = week && w.year === week.year && w.week === week.week;
          return (
            <Link key={pulseWeekSlug(w.year, w.week)} href={pulsePath(theme, w)}
                  className={`border px-2 py-0.5 ${active ? "border-accent text-accent bg-accent/10" : "border-border text-muted hover:text-paper hover:border-paper"}`}
                  title={isoWeekRangeLabel(w.year, w.week)}>
              {w.year}-W{String(w.week).padStart(2, "0")}
            </Link>
          );
        })}
        {owner && week && (
          <form action={recomputePulseAction} className="ml-auto flex items-center gap-3">
            <input type="hidden" name="theme" value={theme} />
            <input type="hidden" name="week" value={pulseWeekSlug(week.year, week.week)} />
            {worker.running ? (
              <button disabled className={`${BTN} border-border text-muted/60 cursor-not-allowed`}
                      title={`a pulse run is in progress${worker.theme ? ` (${worker.theme})` : ""}`}>
                Recompute
              </button>
            ) : (
              <button className={`${BTN} border-accent text-accent hover:bg-accent hover:text-ink`}
                      title="Run scripts/research_pulse.py for this theme and week on the workstation (clusters in seconds, paragraph via Gemma-4-26B)">
                Recompute
              </button>
            )}
          </form>
        )}
      </div>

      {!row ? (
        <div className="border border-dashed border-border p-6 font-sans text-sm text-muted max-w-2xl">
          <p className="text-paper mb-2">
            No pulse for {info.name_en} in {week ? `${week.year}-W${String(week.week).padStart(2, "0")}` : "this week"}.
          </p>
          <p>
            {owner ? "Use Recompute above, or on the workstation: " : "On the workstation: "}
            <span className="font-mono text-[12px]">
              .venv/bin/python scripts/research_pulse.py --themes {theme}{week ? ` --week ${week.year}-W${String(week.week).padStart(2, "0")}` : ""}
            </span>
          </p>
        </div>
      ) : (
        <>
          {/* Provenance header — a dated document, not a live view */}
          <div className="mb-6 border border-border-strong px-4 py-3 flex flex-wrap gap-x-6 gap-y-1 font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
            <span>computed <span className="text-paper">{fmtStamp(row.computed_at)}</span></span>
            <span>window {row.stats.window.start} – {row.stats.window.end}</span>
            <span>model <span className="text-paper">{row.model ? row.model.split("/").pop() : "— (no paragraph)"}</span></span>
            {row.seconds !== null && <span>{Number(row.seconds).toFixed(1)} s</span>}
            <span>k = {row.stats.k} · {fmtInt(row.stats.embedded_n)} embedded</span>
            {row.stats.artifact_n !== undefined && (
              <span title="Repository deposits / non-paper works in this theme's week (research_signals.kind = artifact) — not counted as papers">
                {fmtInt(row.stats.artifact_n)} artifacts excluded
              </span>
            )}
            {row.note && <span className="text-warn normal-case tracking-normal">{row.note}</span>}
          </div>

          {/* Measurement block */}
          <section className="mb-8 grid grid-cols-2 md:grid-cols-4 border border-border divide-x divide-y md:divide-y-0 divide-border">
            <div className="p-4">
              <div className="font-display text-3xl text-paper">{fmtInt(row.stats.week_n)}</div>
              <div className="font-mono text-[9px] uppercase tracking-[0.12em] text-muted mt-1">papers this week</div>
            </div>
            <div className="p-4">
              <div className={`font-display text-3xl ${TONE_CLASS[tone]}`}>
                {TONE_ARROW[tone]} {ratioLabel(row.stats.ratio)}
              </div>
              <div className="font-mono text-[9px] uppercase tracking-[0.12em] text-muted mt-1"
                   title={`Prior weeks: ${row.stats.prior_weeks.map((p) => `W${p.week} ${p.n}`).join(", ")}`}>
                vs. prior four-week median {row.stats.prior_median !== null ? fmtInt(Math.round(row.stats.prior_median)) : "—"}
              </div>
            </div>
            <div className="p-4">
              <div className="flex items-end gap-[4px] h-9" role="img" aria-label="Weekly papers, prior four weeks and this week">
                {sparkBars(row.stats).map((b) => (
                  <div key={b.label} className="flex flex-col items-center gap-1" title={`${b.label}: ${fmtInt(b.n)}`}>
                    <div className={`w-[10px] ${b.current ? "bg-accent" : "bg-border-strong"}`}
                         style={{ height: `${Math.max(2, Math.round(b.h * 26))}px` }} />
                  </div>
                ))}
              </div>
              <div className="font-mono text-[9px] uppercase tracking-[0.12em] text-muted mt-1">
                {row.stats.prior_weeks.map((p) => `W${p.week} ${fmtInt(p.n)}`).join(" · ")}
              </div>
            </div>
            <div className="p-4">
              <div className="font-sans text-[13px] text-paper leading-snug">
                {Object.entries(row.stats.sources).map(([k, v]) => `${fmtInt(v)} ${SOURCE_LABEL[k] ?? k}`).join(" · ") || "—"}
              </div>
              <div className="font-mono text-[9px] uppercase tracking-[0.12em] text-muted mt-1">
                source mix · {fmtInt(row.stats.oa_n)} open-access preprints
              </div>
            </div>
          </section>

          {row.stats.top_concepts.length > 0 && (
            <div className="mb-8 flex flex-wrap items-baseline gap-2 font-mono text-[10px] uppercase tracking-[0.1em]">
              <span className="text-muted mr-1">Concepts</span>
              {row.stats.top_concepts.map(([name, n]) => (
                <Link key={name} href={explorerHref(theme, name)}
                      className="border border-accent/40 text-accent px-1.5 py-0.5 hover:bg-accent/10"
                      title="Open in the Research Explorer (theme + concept)">
                  {name} · {fmtInt(n)}
                </Link>
              ))}
            </div>
          )}

          {/* The paragraph */}
          <section className="mb-10">
            <h2 className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-3">—— Pulse</h2>
            {row.text ? (
              <p className="font-sans text-[16px] leading-relaxed text-paper max-w-3xl">{row.text}</p>
            ) : (
              <p className="font-sans text-[13px] text-muted max-w-3xl">
                {row.note?.startsWith("no-llm") ? "This run computed statistics and clusters only (--no-llm)."
                  : row.note ?? "No paragraph in this run."}
                {owner && " Recompute above to generate one."}
              </p>
            )}
          </section>

          {/* Clusters */}
          <section>
            <h2 className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-3">
              —— Clusters · {row.clusters.length} of {fmtInt(row.stats.embedded_n)} embedded papers
            </h2>
            {row.clusters.length === 0 ? (
              <p className="font-sans text-sm text-muted border border-dashed border-border p-6">
                No papers to cluster this week.
              </p>
            ) : (
              <ul className="grid gap-4 md:grid-cols-2">
                {row.clusters.map((c) => <Cluster key={c.idx} c={c} theme={theme} />)}
              </ul>
            )}
          </section>
        </>
      )}

      <p className="mt-10 font-sans text-[13px] text-muted max-w-3xl border-t border-dashed border-border pt-4">
        Growth compares this week&apos;s cluster size with the mean weekly count of
        prior-week papers nearest the same centroid; &ldquo;emerging&rdquo; means at
        least five papers at 1.5× that mean or more. A cluster with a very high
        growth figure is often a journal batch arriving in one week — check the
        source line of its papers before reading it as a trend. Labels are the
        highest-weighted terms of the cluster&apos;s titles and abstracts.
      </p>
    </div>
  );
}
