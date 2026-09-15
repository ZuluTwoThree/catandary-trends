import type { EmergingNest, EmergingRun } from "./emerging";

/**
 * Wording and small judgements for the emerging-nest cards. Pure, so every
 * claim the page makes is testable.
 *
 * The rule is the same as for the cluster cards: state what was measured, name
 * the weakness in the same breath. A pocket carried by one source, or one that
 * no stage of the pipeline ever read, is shown — and labelled as such — rather
 * than silently dropped, because the judgement is the owner's.
 */

/** Up to this age a pocket counts as genuinely young. */
export const YOUNG_MONTHS = 18;

/** Is the age a statement about the world, or about our own intake? */
export function ageIsMeaningful(nest: EmergingNest): boolean {
  return nest.established_share >= 0.5;
}

export function ageText(nest: EmergingNest): string {
  if (nest.age_months == null || !nest.first_month) return "no datable history";
  const m = nest.age_months;
  if (m < 24) return `first seen ${m} month${m === 1 ? "" : "s"} ago`;
  return `first seen ${nest.first_month}`;
}

export function isYoung(nest: EmergingNest): boolean {
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
  return (
    `${run.nests} pockets found by cutting the last ${days} days into ${run.cells} cells ` +
    `and keeping only the tight ones. Each was then dated against all ` +
    `${run.scanned.toLocaleString("en-US")} archived signals, back to ${run.first_month ?? "the start"}.`
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
