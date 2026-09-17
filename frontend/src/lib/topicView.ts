import type { TierName } from "./emerging";
import type { TopicReport, TopicTier } from "./topicReport";
import { TIERS } from "./tiers";

/** Pure helpers for the topic page — everything the view computes, testable. */

export const TIER_LABEL: Record<TierName, string> = {
  science: "Research",
  patent: "Patents",
  funding: "Funding",
  market: "Market",
};

export function monthsBetween(a: string, b: string): number {
  return (Number(b.slice(0, 4)) - Number(a.slice(0, 4))) * 12 + (Number(b.slice(5, 7)) - Number(a.slice(5, 7)));
}

/** `n` months ending at `last` (YYYY-MM), chronological. */
export function monthAxis(last: string, n: number): string[] {
  let y = Number(last.slice(0, 4));
  let m = Number(last.slice(5, 7));
  const out: string[] = [];
  for (let i = 0; i < n; i++) {
    out.unshift(`${y}-${String(m).padStart(2, "0")}`);
    m -= 1;
    if (m === 0) {
      m = 12;
      y -= 1;
    }
  }
  return out;
}

/** The tier's monthly hits on the last `n` months of the corpus axis. */
export function curveFor(report: TopicReport, tier: TierName, n = 60): { months: string[]; points: number[] } {
  const last = report.corpus.last_month;
  const t = report.tiers[tier];
  if (!last || !t) return { months: [], points: [] };
  const months = monthAxis(last, n);
  const have = new Map(t.series);
  return { months, points: months.map((m) => have.get(m) ?? 0) };
}

export interface StripeStep {
  tier: TierName;
  first_hit: string | null;
  sustained: string | null;
  /** months after the previous step's date (sustained, else first hit) */
  gap: number | null;
}

/**
 * When each conversation began, in order. The sustained month (three hits in
 * one month) is the date that counts; a tier with hits but no sustained month
 * is placed by its first hit, and the view shows both dates.
 */
export function tierStripe(report: TopicReport): StripeStep[] {
  const steps = TIERS.filter((t) => report.tiers[t] && report.tiers[t]!.status !== "none").map((t) => {
    const d = report.tiers[t]!;
    return { tier: t, first_hit: d.first_hit ?? null, sustained: d.first_month ?? null, gap: null as number | null };
  });
  const key = (s: StripeStep) => s.sustained ?? s.first_hit ?? "9999-99";
  steps.sort((a, b) => key(a).localeCompare(key(b)));
  for (let i = 1; i < steps.length; i++) {
    const prev = key(steps[i - 1]);
    const cur = key(steps[i]);
    steps[i].gap = prev.startsWith("9999") || cur.startsWith("9999") ? null : monthsBetween(prev, cur);
  }
  return steps;
}

export function ageText(months: number | null | undefined): string {
  if (months == null) return "—";
  const y = Math.floor(months / 12);
  const m = months % 12;
  return y ? `${y} y ${m} m` : `${m} m`;
}

export function pct(v: number | null | undefined): string {
  return v == null ? "—" : `${Math.round(v * 100)} %`;
}

export type Weakness = { key: string; text: string };

/**
 * Printed on every tier block, never hidden: what would make the numbers
 * mean less than they look.
 */
export function weaknesses(t: TopicTier, established: number | null | undefined): Weakness[] {
  const out: Weakness[] = [];
  if (t.status === "thin") out.push({ key: "thin", text: `only ${t.hits} rows above the cut — too few for a curve` });
  if (t.capped)
    out.push({ key: "capped", text: `the ${t.found}-neighbour window is full — counts are a floor, not a total` });
  if (t.sources <= 2 && t.hits > 0) out.push({ key: "sources", text: `${t.sources} source${t.sources === 1 ? "" : "s"} only` });
  if (t.top_source && t.top_source_share != null && t.top_source_share >= 0.5)
    out.push({ key: "concentration", text: `${Math.round(t.top_source_share * 100)} % from ${t.top_source}` });
  if (t.hits > 0 && t.hits_damped < t.hits * 0.8)
    out.push({ key: "damped", text: `${t.hits - t.hits_damped} rows are one source's spike months (damped: ${t.hits_damped})` });
  if (t.tagged_share != null && t.tagged_share < 0.3 && t.hits >= 5)
    out.push({ key: "untagged", text: `${Math.round(t.tagged_share * 100)} % of rows ever passed classification` });
  if (t.index === "scan") out.push({ key: "index", text: "no index for this tier — answered by a scan" });
  if (established != null && established < 0.5 && t.hits > 0)
    out.push({ key: "new-sources", text: `${Math.round(established * 100)} % from sources read two years ago — the age may be ours, not the topic's` });
  return out;
}

export function cutText(report: TopicReport): string {
  return `cut = max(head − ${report.params.drop}, ${report.params.floor}) per tier, ${report.params.neighbours} neighbours each`;
}
