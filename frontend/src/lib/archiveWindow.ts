import { isPublicMode } from "./publicMode";

/**
 * Archive-window arithmetic shared by the public-mode preview (#93), the
 * windowed feed queries in lib/db.ts and the static export
 * (generateStaticParams, sitemap). One rule for every caller, so a slug the
 * export lists can never fall outside the window the page render applies.
 *
 * History: until 2026-09-03 this sat behind a tier/paywall layer
 * (lib/entitlement.ts, FREE_ARCHIVE_DAYS = 28 for free accounts, #70). With
 * the SaaS model gone (#93) the only window left is the public one below;
 * the owner instance always sees the whole archive.
 *
 * The lower bound is a DAY boundary, not "now minus N days": the start of the
 * current UTC day minus N days. Two builds minutes apart therefore see the
 * same slug set (the deterministic-export gate, spike 2026-09-02), the daily
 * 06:30 export moves the window exactly once per day, and the public "30
 * days" promise reads as "today plus the 30 previous full days" everywhere.
 */
export function windowStart(days: number, now: Date = new Date()): Date {
  const dayStart = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  return new Date(dayStart - days * 86_400_000);
}

/** ISO form of `windowStart`, for `$n::timestamptz` query parameters. */
export function windowStartIso(days: number, now?: Date): string {
  return windowStart(days, now).toISOString();
}

/**
 * Pure date check for a single article. Fails OPEN on missing or unparseable
 * dates: the window is a product boundary, not a security one — bad data
 * must never hide content. `days === null` means unlimited.
 */
export function withinWindow(
  date: string | Date | null | undefined,
  days: number | null,
  now?: Date
): boolean {
  if (days === null) return true;
  if (!date) return true;
  const t = date instanceof Date ? date.getTime() : Date.parse(date);
  if (Number.isNaN(t)) return true;
  return t >= windowStart(days, now).getTime();
}

/**
 * `PUBLIC_WINDOW_DAYS` (default 30): how far back the public showcase reaches.
 * Read by the PUBLIC_MODE preview (archiveWindowDays below) and by the static
 * export (slug list, sitemap) — the same env var on both, so a preview on
 * :3999 shows exactly what an export with the same setting would publish.
 * Anything that is not a positive integer falls back to the default.
 */
export const DEFAULT_PUBLIC_WINDOW_DAYS = 30;

export function parsePublicWindowDays(raw: string | undefined): number {
  if (raw === undefined || raw === "") return DEFAULT_PUBLIC_WINDOW_DAYS;
  const n = Number(raw);
  if (!Number.isInteger(n) || n < 1 || n > 3650) return DEFAULT_PUBLIC_WINDOW_DAYS;
  return n;
}

export function publicWindowDays(): number {
  return parsePublicWindowDays(process.env.PUBLIC_WINDOW_DAYS);
}

/**
 * The public lead-gen deployment (#93) ships only the last N days of the
 * feed — "30 Tage Trends" is the whole public data promise (~83 MB). On the
 * real deployment the export itself is windowed; this constant makes the
 * workstation preview (PUBLIC_MODE=1) match it and is the safety net if a
 * fuller dataset ever reaches a public instance. Module-level on purpose:
 * one value per process, read once.
 */
export const PUBLIC_ARCHIVE_DAYS = publicWindowDays();

/**
 * The archive window for the current render, in days — or null for the
 * whole archive. PUBLIC_MODE (the :3999 preview and the export build) gets
 * the public window; the owner instance is unlimited. Callers thread the
 * value into query options (`max_age_days`) or `withinWindow`.
 */
export function archiveWindowDays(): number | null {
  return isPublicMode() ? PUBLIC_ARCHIVE_DAYS : null;
}

/* ---------- Newsletter archive (static export, Schritt E) ---------- */

/**
 * `PUBLIC_NEWSLETTER_EDITIONS` (default 12): how many past weekly briefings
 * the public site carries under /trends/newsletter/<year>-w<week>. The
 * briefing archive is the second public window next to the article window
 * above — counted in editions, not days, because an edition is a weekly
 * document whose value does not expire with its articles (the article links
 * inside it are re-checked against the article window at build time,
 * lib/newsletterEditions.ts). Same parsing contract as PUBLIC_WINDOW_DAYS.
 */
export const DEFAULT_PUBLIC_NEWSLETTER_EDITIONS = 12;

export function parsePublicNewsletterEditions(raw: string | undefined): number {
  if (raw === undefined || raw === "") return DEFAULT_PUBLIC_NEWSLETTER_EDITIONS;
  const n = Number(raw);
  if (!Number.isInteger(n) || n < 1 || n > 520) return DEFAULT_PUBLIC_NEWSLETTER_EDITIONS;
  return n;
}

export function publicNewsletterEditions(): number {
  return parsePublicNewsletterEditions(process.env.PUBLIC_NEWSLETTER_EDITIONS);
}
