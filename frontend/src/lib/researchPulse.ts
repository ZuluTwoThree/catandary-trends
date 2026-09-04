/**
 * Research Pulse (#73 Teil 1) — pure helpers for the weekly per-theme
 * synthesis in `research_pulse` (written by scripts/research_pulse.py).
 *
 *   /trends/foresight/research/pulse                 all themes of one week
 *   /trends/foresight/research/pulse/<theme>?week=…  one theme, week switcher
 *
 * No DB, no clock in here (db.ts holds the queries) so the week scheme, the
 * volume ratio and the card excerpt are unit-testable. Week slugs share the
 * newsletter's `2026-w35` form (lib/newsletterEditions.ts) — one URL grammar
 * for "a week" across the app.
 */
import { editionSlug, parseEditionSlug, isoWeekMonday } from "./newsletterEditions";

export interface PulseWeekRef {
  year: number;
  week: number;
}

export interface PulseStats {
  window: { start: string; end: string };
  week_n: number;
  embedded_n: number;
  prior_weeks: { year: number; week: number; n: number }[];
  prior_median: number | null;
  ratio: number | null;
  sources: Record<string, number>;
  top_sources: [string, number][];
  top_concepts: [string, number][];
  oa_n: number;
  k: number;
}

export interface PulsePaper {
  trend_id: number;
  title: string;
  source: string | null;
  published: string | null;
  url: string;
  oa: boolean;
  sim: number;
}

export interface PulseCluster {
  idx: number;
  n: number;
  share: number;
  terms: string[];
  concepts: [string, number][];
  label: string;
  prior_n: number | null;
  prior_weekly_mean: number | null;
  growth: number | null;
  emerging: boolean;
  papers: PulsePaper[];
}

export interface PulseRow {
  id: number;
  theme: string;
  year: number;
  week: number;
  week_start: string;
  computed_at: string;
  stats: PulseStats;
  clusters: PulseCluster[];
  text: string | null;
  model: string | null;
  seconds: number | null;
  note: string | null;
}

/* ---------- Week scheme ---------- */

export function pulseWeekSlug(year: number, week: number): string {
  return editionSlug(year, week);
}

export function parsePulseWeek(slug: string | undefined | null): PulseWeekRef | null {
  if (!slug) return null;
  // accept the CLI form too (2026-W35) — the page normalises to 2026-w35
  return parseEditionSlug(slug.toLowerCase());
}

/** ISO year/week of a date (UTC), e.g. 2026-08-27 → 2026-W35. */
export function isoWeekOf(d: Date): PulseWeekRef {
  const t = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
  const day = t.getUTCDay() || 7; // Mon=1 … Sun=7
  t.setUTCDate(t.getUTCDate() + 4 - day); // Thursday of this ISO week
  const year = t.getUTCFullYear();
  const jan1 = Date.UTC(year, 0, 1);
  const week = Math.ceil(((t.getTime() - jan1) / 86_400_000 + 1) / 7);
  return { year, week };
}

/** The pulse's default week: the last completed ISO week (today − 7 days),
 *  the same rule as scripts/research_pulse.py and the newsletter cron. */
export function lastCompletedWeek(today: Date): PulseWeekRef {
  return isoWeekOf(new Date(today.getTime() - 7 * 86_400_000));
}

export function pulsePath(theme?: string, week?: PulseWeekRef | null): string {
  const base = theme
    ? `/trends/foresight/research/pulse/${encodeURIComponent(theme)}`
    : "/trends/foresight/research/pulse";
  return week ? `${base}?week=${pulseWeekSlug(week.year, week.week)}` : base;
}

/** "2026-W35" as the CLI expects it (scripts/research_pulse.py --week). */
export function cliWeek(week: PulseWeekRef): string {
  return `${week.year}-W${String(week.week).padStart(2, "0")}`;
}

export function weekMondayIso(week: PulseWeekRef): string {
  return isoWeekMonday(week.year, week.week).toISOString().slice(0, 10);
}

/* ---------- Volume ---------- */

function median(values: number[]): number {
  const s = [...values].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

/** Week volume over the median of the prior weeks; null without a baseline.
 *  Mirrors pipeline/research_pulse.py volume_ratio (rounded to 3 places). */
export function volumeRatio(current: number, prior: number[]): number | null {
  if (prior.length === 0) return null;
  const m = median(prior);
  if (m <= 0) return null;
  return Math.round((current / m) * 1000) / 1000;
}

export type RatioTone = "up" | "down" | "flat" | "none";

/** Below ±5 % is noise at weekly granularity — call it level. */
export function ratioTone(ratio: number | null): RatioTone {
  if (ratio === null || !Number.isFinite(ratio)) return "none";
  const pct = (ratio - 1) * 100;
  if (pct >= 5) return "up";
  if (pct <= -5) return "down";
  return "flat";
}

/** "+9 %", "−35 %", "≈ level", "no baseline". */
export function ratioLabel(ratio: number | null): string {
  const tone = ratioTone(ratio);
  if (tone === "none") return "no baseline";
  if (tone === "flat") return "≈ level";
  const pct = Math.round(((ratio as number) - 1) * 100);
  return `${pct > 0 ? "+" : "−"}${Math.abs(pct)} %`;
}

/** Growth of a cluster against its prior weekly mean: "×2.4" / "no baseline". */
export function growthLabel(growth: number | null): string {
  if (growth === null || !Number.isFinite(growth)) return "no baseline";
  return `×${growth.toFixed(growth >= 10 ? 0 : 1)}`;
}

/* ---------- Text ---------- */

/** First sentence of the pulse paragraph for the overview card; falls back
 *  to a trimmed prefix when the model wrote one long sentence. */
export function firstSentence(text: string | null | undefined, max = 220): string {
  const t = (text ?? "").replace(/\s+/g, " ").trim();
  if (!t) return "";
  // sentence end = . ! ? followed by a space and a capital/quote/digit;
  // decimals (4663.5) and abbreviations (e.g.) do not end a sentence
  const m = t.match(/^.*?[.!?](?=\s+[A-Z"“(0-9])/);
  const s = m ? m[0] : t;
  if (s.length <= max) return s;
  return `${s.slice(0, max - 1).replace(/\s+\S*$/, "")}…`;
}

/** Bars for the tiny 5-week sparkline: prior weeks + current, scaled 0..1. */
export function sparkBars(stats: PulseStats): { label: string; n: number; h: number; current: boolean }[] {
  const items = [
    ...stats.prior_weeks.map((p) => ({ label: `W${p.week}`, n: p.n, current: false })),
    { label: "now", n: stats.week_n, current: true },
  ];
  const max = Math.max(1, ...items.map((i) => i.n));
  return items.map((i) => ({ ...i, h: i.n / max }));
}
