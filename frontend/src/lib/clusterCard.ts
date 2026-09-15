import type { ForesightCluster, ForesightRun } from "./foresight";

/**
 * Wording for the cluster cards — pure functions so the claims can be tested.
 *
 * Rewritten 2026-09-15 after the audit found the card asserting more than the
 * data supports: "confirmed by 419 independent sources" implied a verification
 * that never happens (it is simply how many feeds fed a 95k bucket), and the
 * momentum sentence was the only statement on the card, so a theme that lost
 * share while growing in volume read as dying.
 */

/** Percentage-point delta, signed, one decimal. */
export function deltaText(pp: number): string {
  return `${pp > 0 ? "+" : ""}${pp.toFixed(1)} pp`;
}

/** Share of panel signals, as a percentage with one decimal below 10 %. */
export function sharePct(share: number): string {
  const pct = share * 100;
  return `${pct < 10 ? pct.toFixed(1) : Math.round(pct)} %`;
}

/**
 * Attention first, then the two shares it is made of.
 *
 * The second number is deliberately NOT the raw item count: in the 2026-09
 * corpus every cluster's count grew between 20 % and 5,000 % because the
 * corpus itself did, so it measured our ingest, not the theme.
 */
export function clusterSummary(c: ForesightCluster): string {
  const attention =
    c.momentum === "rising"
      ? `Gaining share of attention, ${deltaText(c.sov_delta_pp)}.`
      : c.momentum === "declining"
        ? `Losing share of attention, ${deltaText(c.sov_delta_pp)}.`
        : c.momentum === "unknown"
          ? "Too short an observation window to call a direction."
          : "Holding its share of attention.";
  if (c.share_early == null || c.share_late == null) return attention;
  return `${attention} ${sharePct(c.share_early)} of panel signals in the early window, ${sharePct(c.share_late)} in the late one.`;
}

/**
 * Source concentration. A cluster carried to 60 % by one outlet is one
 * newsroom's agenda, however many other feeds touched it — say so instead of
 * letting the source count imply breadth.
 */
export function concentrationNote(c: ForesightCluster): { text: string; title: string } {
  if (!c.top_source || !c.top_source_share) return { text: "", title: "" };
  const pct = Math.round(c.top_source_share * 100);
  return {
    text: `largest ${pct} %`,
    title: `${c.top_source} supplies ${pct} % of this cluster's signals. Source count is breadth, not verification.`,
  };
}

/** Below this the dominant mega-trend is a plurality, not an attribution. */
export const MEGA_PURITY_MIN = 0.5;

export function megaAttribution(c: ForesightCluster): boolean {
  return Boolean(c.mega_trend) && c.mega_purity >= MEGA_PURITY_MIN;
}

/** Mean cosine to centre, in words. Thresholds from the 2026-09 runs (0.51–0.73). */
export function cohesionLabel(cohesion: number): string {
  if (cohesion >= 0.66) return "tight";
  if (cohesion >= 0.58) return "broad";
  return "loose";
}

/** One line stating what the run actually measured. */
export function runProvenance(run: ForesightRun): string {
  const span =
    run.window_months && run.window_months > 0
      ? `the last ${run.window_months} months`
      : "the full archive";
  const months =
    run.first_month && run.last_month ? ` (${run.first_month} to ${run.last_month})` : "";
  const panel = run.cohort_applied
    ? `Momentum is measured on ${run.cohort_sources} sources that delivered in both comparison windows` +
      (run.cohort_coverage != null
        ? `, ${Math.round(run.cohort_coverage * 100)} % of the signals in those windows.`
        : ".")
    : "Momentum counts every source: too few delivered in both comparison windows to hold a fixed panel.";
  return `${run.signals.toLocaleString("en-US")} signals from ${span}${months}. ${panel}`;
}

/**
 * Take `limit` rows but never let one source own the list.
 *
 * Both detail lists collapsed without this: "closest to the centre" was eight
 * of twelve from one journal family, and "most recent" was twelve rows from a
 * single bulk ingest, all on the same day (2026-09-15). Rows keep their
 * incoming order; a source's rows beyond `maxPerSource` are only used if the
 * list would otherwise be short.
 */
export function spreadBySource<T extends { source_name: string | null }>(
  rows: T[],
  limit: number,
  maxPerSource = 2
): T[] {
  const picked: T[] = [];
  const spare: T[] = [];
  const seen = new Map<string, number>();
  for (const r of rows) {
    const key = r.source_name ?? "";
    const n = seen.get(key) ?? 0;
    if (key && n >= maxPerSource) {
      spare.push(r);
      continue;
    }
    seen.set(key, n + 1);
    picked.push(r);
    if (picked.length >= limit) return picked;
  }
  for (const r of spare) {
    if (picked.length >= limit) break;
    picked.push(r);
  }
  return picked;
}
