import { getSession, type Tier } from "./auth";
import { tierAllows } from "./tiers";
import { isPublicMode } from "./publicMode";
import { withinWindow, publicWindowDays } from "./archiveWindow";

/**
 * Entitlement layer (Epic W2.2, issue #17). Gating is itself behind
 * PAYWALL_ENABLED: while it's off (prod today) every viewer is treated as fully
 * entitled, so the deployed site is unchanged until we flip the paywall on.
 *
 * Owner UX rule: gate at the value drill-down, not at the door — pages stay
 * browsable; only the deep feature shows an upgrade prompt.
 */
export const PAYWALL_ENABLED = process.env.PAYWALL_ENABLED === "1";

/** The current viewer's tier: their account tier, or 'free' if not signed in. */
export async function viewerTier(): Promise<Tier> {
  const session = await getSession();
  return session?.tier ?? "free";
}

/**
 * Whether the current viewer may access a feature requiring `need`. Returns
 * true unconditionally when the paywall is disabled.
 */
export async function canAccess(need: Tier): Promise<boolean> {
  if (!PAYWALL_ENABLED) return true;
  return tierAllows(await viewerTier(), need);
}

/* ---------- Free archive window (issue #70) ---------- */

/**
 * Free viewers see only the most recent slice of the published feed; the full
 * article archive is a Starter+ feature (owner decision 2026-07-27 — the
 * landing page promises exactly this split). The window applies to the
 * article's visible timeline date (`sort_date`, the date shown on cards) and
 * is enforced server-side: feed queries, both public APIs and the article
 * page. Keep the tier copy in lib/tiers.ts in sync when changing this.
 */
export const FREE_ARCHIVE_DAYS = 28;

/**
 * The public lead-gen deployment (#93) ships only the last 30 days of the
 * feed — "30 Tage Trends" is the whole public data promise (~83 MB). On the
 * real deployment the export itself is windowed (same value, same env var
 * PUBLIC_WINDOW_DAYS — see lib/archiveWindow.ts); this flag-enforced window
 * makes the workstation preview (PUBLIC_MODE=1) match it and is the safety
 * net if a fuller dataset ever reaches a public instance.
 */
export const PUBLIC_ARCHIVE_DAYS = publicWindowDays();

/**
 * The archive window for the current viewer, in days — or null for unlimited
 * (paywall off, or Starter and above). Callers thread the value into query
 * options (`max_age_days`) or `withinArchiveWindow`. PUBLIC_MODE wins over
 * everything — the public showcase has no accounts, so no tier can widen it.
 */
export async function archiveWindowDays(): Promise<number | null> {
  if (isPublicMode()) return PUBLIC_ARCHIVE_DAYS;
  if (!PAYWALL_ENABLED) return null;
  return tierAllows(await viewerTier(), "starter") ? null : FREE_ARCHIVE_DAYS;
}

/**
 * Pure date check for a single article. Fails OPEN on missing or unparseable
 * dates: the window is a monetization boundary, not a security one — bad data
 * must never hide content. The bound is the day boundary from
 * lib/archiveWindow.ts — the same one the SQL side (`max_age_days`) and the
 * static export use, so page and query can never disagree about an article.
 */
export function withinArchiveWindow(
  date: string | Date | null | undefined,
  windowDays: number | null
): boolean {
  return withinWindow(date, windowDays);
}
