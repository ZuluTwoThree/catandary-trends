import type { CalendarSeries, EmergingNest, EmergingRun, TierName } from "./emerging";

/**
 * Wording and small judgements for the emerging-nest cards. Pure, so every
 * claim the page makes is testable.
 *
 * The rule is the same as for the cluster cards: state what was measured, name
 * the weakness in the same breath. A pocket carried by one source, or one that
 * no stage of the pipeline ever read, is shown — and labelled as such — rather
 * than silently dropped, because the judgement is the owner's.
 */

/**
 * What the card calls the pocket, and what it shows underneath.
 *
 * The model-written name reads like a topic; the tag label is the thing that
 * was actually measured. Showing both keeps the naming step from quietly
 * becoming the source of truth — if the name is wrong, the label next to it
 * says so immediately.
 */
export function nestTitle(nest: EmergingNest): { name: string; sub: string | null } {
  if (nest.llm_label && nest.llm_label !== nest.label) {
    return { name: nest.llm_label, sub: nest.label };
  }
  return { name: nest.label, sub: null };
}

/** Up to this age a pocket counts as genuinely young. */
export const YOUNG_MONTHS = 18;

/** Is the age a statement about the world, or about our own intake? */
export function ageIsMeaningful(nest: EmergingNest): boolean {
  if (calendarFirst(nest)) return true;
  return nest.established_share >= 0.5;
}

/* ------------------------- the research and patent calendar ----------------- */
/** Owner 01.10.: research and patents carry real dates. When a pocket has been dated
 *  against them (pipeline/calendar_dating.py), that date leads — the signal space only
 *  holds research and patents in breadth since 2026. */
export const CALENDAR_LABEL: Record<"science" | "patent", string> = {
  science: "Research",
  patent: "Patents",
};

export function calendarFirst(
  nest: EmergingNest
): { year: number; edge: boolean; corpus: "science" | "patent" } | null {
  const c = nest.calendar;
  if (!c) return null;
  let best: { year: number; edge: boolean; corpus: "science" | "patent" } | null = null;
  for (const k of ["science", "patent"] as const) {
    const s = c[k];
    if (s?.first == null) continue;
    if (!best || s.first < best.year) best = { year: s.first, edge: s.edge, corpus: k };
  }
  return best;
}

export function calendarLine(s: CalendarSeries, unit: string): string {
  const parts = [s.first == null ? "no matches" : `since ${s.first}${s.edge ? " or earlier" : ""}`];
  if (s.takeoff != null) parts.push(`take-off ${s.takeoff}`);
  if (s.growth != null) parts.push(`×${s.growth.toFixed(1)} over the last three years`);
  parts.push(`${s.total.toLocaleString("en-US")} ${unit}`);
  return parts.join(" · ");
}

/** The counted query in words: anchor AND (phrase OR phrase). */
export function calendarQuery(nest: EmergingNest): string | null {
  const c = nest.calendar;
  if (!c || !c.phrases.length) return null;
  const q = (xs: string[]) => xs.map((x) => `"${x}"`).join(" or ");
  return c.anchor.length ? `${q(c.anchor)} and (${q(c.phrases)})` : q(c.phrases);
}

/** Complete years of a series for a sparkline (the running year would read as a drop). */
export function calendarSpark(s: CalendarSeries, thisYear = new Date().getFullYear()) {
  const idx = s.years.map((y, i) => (y < thisYear ? i : -1)).filter((i) => i >= 0);
  return {
    years: idx.map((i) => String(s.years[i])),
    values: idx.map((i) => s.per_million[i]),
  };
}

export function ageText(nest: EmergingNest): string {
  const cal = calendarFirst(nest);
  if (cal) return `on record since ${cal.year}${cal.edge ? " or earlier" : ""}`;
  if (nest.age_months == null || !nest.first_month) return "no datable history";
  const m = nest.age_months;
  if (m < 24) return `first seen ${m} month${m === 1 ? "" : "s"} ago`;
  return `first seen ${nest.first_month}`;
}

export function isYoung(nest: EmergingNest, thisYear = new Date().getFullYear()): boolean {
  const cal = calendarFirst(nest);
  if (cal) return !cal.edge && cal.year >= thisYear - 1;
  return (
    nest.age_months != null && nest.age_months <= YOUNG_MONTHS && ageIsMeaningful(nest)
  );
}

/** Plain sentence for the novelty lift, which saturates and needs context. */
export function noveltyText(nest: EmergingNest): string {
  if (nest.novelty_lift == null) return "Not enough history to judge.";
  const x = nest.novelty_lift;
  if (x >= 4) return "Practically every trace of this is from the last six months.";
  if (x >= 2) return `Its evidence is ${x.toFixed(1)}x more concentrated in the last six months than the archive at large.`;
  if (x >= 1.2) return `Somewhat more recent than the archive at large, ${x.toFixed(1)}x.`;
  return "Spread through the archive like everything else.";
}

export function accelText(nest: EmergingNest): string | null {
  if (nest.accel == null) return "No earlier evidence to compare against.";
  if (nest.accel >= 2) return `Running ${nest.accel.toFixed(1)}x its own earlier rate.`;
  if (nest.accel <= 0.5) return `Running at ${nest.accel.toFixed(1)}x its earlier rate.`;
  return null;
}

export type Caveat = { key: string; text: string };

/**
 * What would make a reader wrong to trust this pocket. Ordered by severity.
 * "One source" is the big one: a pocket that only one outlet produces is that
 * outlet's output, not a trend — the first real run surfaced a 647-document
 * pocket of pseudo-science from one bulk research sweep at the very top.
 */
export function caveats(nest: EmergingNest): Caveat[] {
  const out: Caveat[] = [];
  // The most misleading case, and the least obvious: a pocket can only be
  // dated against sources that were already being read. The first FOOD run
  // (2026-09-15) filled its top ten with agronomy pockets "first seen three
  // months ago", every one of them from journal sweeps that started three
  // months ago. Their age measured our subscriptions, not the world.
  if (nest.established_share < 0.5) {
    out.push({
      key: "young-sources",
      text: `Only ${Math.round(nest.established_share * 100)} % of this comes from sources we were already reading two years ago, so its age says more about our intake than about the world.`,
    });
  }
  if (nest.n_sources <= 2) {
    out.push({
      key: "sources",
      text: `Only ${nest.n_sources} source${nest.n_sources === 1 ? "" : "s"} feed this. That is one newsroom's output, not corroboration.`,
    });
  } else if (nest.top_source_share >= 0.5 && nest.top_source) {
    out.push({
      key: "concentration",
      text: `${nest.top_source} supplies ${Math.round(nest.top_source_share * 100)} % of it.`,
    });
  }
  if (nest.tagged_share < 0.1) {
    out.push({
      key: "unclassified",
      text: "Almost none of this passed the classification stages. It is raw bulk-ingested material.",
    });
  }
  if (nest.size < 40) {
    out.push({ key: "small", text: `Only ${nest.size} documents.` });
  }
  return out;
}

/** One line stating what the run actually did. */
export function runProvenance(run: EmergingRun): string {
  const days = run.window_days ?? 0;
  const p = run.params;
  if (p?.mode === "live") {
    const share = p.in_pockets != null ? `, holding ${Math.round(p.in_pockets * 100)} % of them` : "";
    return (
      `Discovered live for "${p.term}"${p.also?.length ? ` (also ${p.also.join(", ")})` : ""}: ` +
      `${(p.members_window ?? run.signals).toLocaleString("en-US")} signals of the last ` +
      `${p.window_months ?? Math.round(days / 30)} months were selected by meaning; ` +
      `${run.nests} pockets are the densest ` +
      `${Math.round((1 - (p.cohesion_quantile ?? 0.6)) * 100)} % of their cells${share}. ` +
      `Each was dated against the domain's ${run.scanned.toLocaleString("en-US")} archived ` +
      `signals, back to ${run.first_month ?? "the start"}.`
    );
  }
  const past = p?.history_sample
    ? ` plus a sample of ${p.history_sample.toLocaleString("en-US")} past patents (from 1990) and ` +
      `research works (from 2010)`
    : "";
  return (
    `${run.nests} pockets found by cutting the last ${days} days into ${run.cells} cells ` +
    `and keeping only the tight ones. Each was then dated against all ` +
    `${run.scanned.toLocaleString("en-US")} archived signals${past}, back to ${run.first_month ?? "the start"}.`
  );
}

/** The tail of a nest's history that is worth drawing. */
export function historyTail(
  nest: EmergingNest,
  months = 60
): { months: string[]; values: number[] } {
  const m = nest.history_months.slice(-months);
  const v = nest.history_hits.slice(-months);
  return { months: m, values: v };
}


/* ------------------------------ lead-time tiers --------------------------- */
/**
 * Owner 2026-09-15: "ein science trend ist nicht das selbe wie ein markttrend,
 * selbst wenn thematisch deckungsgleich". Perovskite is researched, patented,
 * funded and only then argued about in the trade press. The card therefore
 * shows WHICH conversation this pocket is, and when the others started.
 */
export const TIER_LABEL: Record<TierName, string> = {
  science: "research",
  patent: "patents",
  funding: "funding",
  market: "market",
};

export interface TierStep {
  tier: TierName;
  label: string;
  first_month: string | null;
  share: number;
}

export function tierSteps(nest: EmergingNest): TierStep[] {
  return nest.tier_order
    .filter((t) => nest.tiers[t]?.first_month)
    .map((t) => ({
      tier: t,
      label: TIER_LABEL[t],
      first_month: nest.tiers[t]!.first_month,
      share: nest.tiers[t]!.share_of_nest,
    }));
}

/** Which conversation this pocket mostly IS. */
export function dominantTier(nest: EmergingNest): TierName | null {
  let best: TierName | null = null;
  let share = 0;
  for (const t of Object.keys(nest.tiers) as TierName[]) {
    const s = nest.tiers[t]?.share_of_nest ?? 0;
    if (s > share) {
      share = s;
      best = t;
    }
  }
  return share >= 0.5 ? best : null;
}

export function leadText(nest: EmergingNest): string | null {
  const m = nest.science_to_market_months;
  if (m == null) return null;
  if (m > 0) return `Research led the market by ${m} month${m === 1 ? "" : "s"}.`;
  if (m < 0) return `The market got there ${-m} month${m === -1 ? "" : "s"} before the research did.`;
  return "Research and market started the same month.";
}

/** Distinct companies named, with the coverage caveat that makes it a floor. */
export function actorText(nest: EmergingNest): string | null {
  if (!nest.actors_late) return null;
  const from = nest.actors_early
    ? `${nest.actors_early} two years ago, ${nest.actors_late} now`
    : `${nest.actors_late}`;
  return `Named companies: ${from}. Only 13 % of trade-press rows carry an extracted name, so this is a floor.`;
}


/* ------------------------------ sub-groups -------------------------------- */
export interface NestGroup {
  id: number;
  label: string | null;
  size: number;
  nests: EmergingNest[];
}

/**
 * Pockets of a grouped run (discovery service) in group order, biggest group first,
 * keeping the page's order inside each group. Null when the run is not grouped or
 * everything sits in one group — then the plain grid reads better.
 */
export function groupNests(nests: EmergingNest[]): NestGroup[] | null {
  if (!nests.some((n) => n.group_id != null)) return null;
  const by = new Map<number, NestGroup>();
  for (const n of nests) {
    const id = n.group_id ?? 0;
    const g = by.get(id) ?? { id, label: null, size: 0, nests: [] };
    g.label = g.label ?? n.group_label;
    g.size += n.size;
    g.nests.push(n);
    by.set(id, g);
  }
  if (by.size < 2) return null;
  return [...by.values()].sort((a, b) => (a.id || 1e9) - (b.id || 1e9));
}
