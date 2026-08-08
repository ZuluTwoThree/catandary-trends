/**
 * Measured mega-trend momentum — replaces the hand-typed `momentum:` claim in
 * mega_trends.yaml (2026-08-08: 19 of 26 yaml claims contradicted the data).
 *
 * Measurement: the key's share of published signals in the last `windowDays`
 * (90) vs the `windowDays` before that. Shares, not raw counts — the corpus
 * grows through backfills, and raw counts would read growth of the corpus as
 * growth of every trend (same normalization the methodology page promises for
 * cluster momentum).
 *
 * Rules (MIRRORED in pipeline/mega_momentum.py — keep thresholds in sync):
 *   - fewer than MIN_N signals across both windows → null: too thin for a
 *     directional claim, the badge is simply not shown (no claim beats a
 *     wrong claim)
 *   - prior share 0, recent present → "emerging"
 *   - share change > +15 % → "rising" · < −15 % → "declining" · else "stable"
 */
export type MegaMomentum = "rising" | "stable" | "declining" | "emerging";

export const MOMENTUM_MIN_N = 10;
export const MOMENTUM_THRESHOLD = 0.15;

export function classifyMomentum(
  recent: number,
  prior: number,
  totalRecent: number,
  totalPrior: number
): MegaMomentum | null {
  if (recent + prior < MOMENTUM_MIN_N) return null;
  if (totalRecent <= 0 || totalPrior <= 0) return null;
  const shareRecent = recent / totalRecent;
  const sharePrior = prior / totalPrior;
  if (sharePrior === 0) return "emerging";
  const change = (shareRecent - sharePrior) / sharePrior;
  if (change > MOMENTUM_THRESHOLD) return "rising";
  if (change < -MOMENTUM_THRESHOLD) return "declining";
  return "stable";
}
