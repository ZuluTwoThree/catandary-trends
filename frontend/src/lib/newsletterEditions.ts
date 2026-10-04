/**
 * Weekly briefing editions (`newsletter_editions`, written Mondays 09:00 by
 * scripts/weekly_newsletter_publish.sh) as the static export renders them
 * (design Schritt E — docs/launch/HOSTING_HETZNER.md "Newsletter im Export").
 *
 *   /trends/newsletter                     signup + latest edition + archive list
 *   /trends/newsletter/<year>-w<week>      one edition (e.g. 2026-w35, zero-padded week)
 *   /trends/newsletter/unsubscribed        static confirmation page (unsubscribe.php redirect)
 *
 * Pure helpers only (no DB, no clock) so the URL scheme and the link rule
 * are unit-testable and byte-stable between two builds. The archive size
 * lives in lib/archiveWindow.ts next to the article window.
 *
 * Link rule (the one that matters for a static host): an edition's markdown
 * text and its `trend_refs` link `/trends/<slug>`. Articles outside the
 * public article window do not exist as files in the export — Apache answers
 * 410 — so at build time every such link is re-pointed to the article's
 * primary source (`source_url`, the newsletter's own citation promise) or,
 * without a usable source, rendered as plain text. Links inside the window
 * stay internal; `/trends/mega` and absolute http(s) links are untouched.
 */
import { safeHref } from "./safeHref";
import { truncateSummary } from "./staticSearch";

export interface MegaTrendRadarEntry {
  key: string;
  name_en: string;
  icon: string;
  /** Measured; null/absent = too thin for a directional claim. */
  momentum?: string | null;
  signal_count: number;
}

export interface TrendRef {
  title: string;
  slug: string;
  source_name: string;
  /** Present in editions since W32/2026 (the generator's citation promise). */
  source_url?: string;
  /**
   * Resolved link target. `undefined` = the caller's default (`/trends/<slug>`,
   * the workstation instance); a string = use it; `null` = render as text.
   */
  href?: string | null;
}

/* ---------- Deep Dive of the Week (#96) ---------- */

export type DeepDiveKind = "article" | "signal" | "paper" | "patent" | "web";

export interface DeepDiveCitation {
  url: string;
  title: string;
  kind: DeepDiveKind;
  outlet?: string | null;
  date?: string | null;
}

/**
 * `newsletter_editions.deep_dive` as scripts/newsletter_deep_dive.py writes
 * it. Everything the owner needs to audit the run travels with the record;
 * the public render uses only body_md, citations and the provenance fields.
 */
export interface NewsletterDeepDive {
  theme?: string | null;
  theme_name?: string | null;
  body_md?: string | null;
  citations?: DeepDiveCitation[];
  /** Historical: the scouting-dossier behind older runs (feature removed
   *  2026-09-19 — the desk no longer exists, these are display-only). */
  dossier_slug?: string | null;
  dossier_version?: number | null;
  corpus_asof?: string | null;
  audit?: Record<string, unknown> | null;
  gates?: Record<string, boolean> | null;
  gate_reasons?: string[];
  gate_passed?: boolean;
  dry_run?: boolean;
  generated_at?: string | null;
  models?: { research?: string | null; condense?: string | null } | null;
  words?: number;
  seconds?: number;
  status?: string | null;
  error?: string | null;
  condensate_check?: {
    checks?: Record<string, boolean>;
    reasons?: string[];
    attempts?: { attempt: number; words: number; ok: boolean; reasons: string[] }[];
  } | null;
}

export interface NewsletterEdition {
  id: number;
  year: number;
  week: number;
  editorial: string;
  vertical_summaries: Record<string, string>;
  mega_trend_radar: MegaTrendRadarEntry[];
  trend_refs: Record<string, TrendRef[]>;
  total_signals: number;
  created_at: string;
  /** #96 — null/absent for editions without a deep-dive run. */
  deep_dive?: NewsletterDeepDive | null;
}

/**
 * The single public-render rule for a deep dive (#96): only a record whose
 * honesty gate passed AND that was written by a live (--apply) run is ever
 * shown to readers. A dry-run record — the Phase-1 default — exists for the
 * owner alone. Applied by the API route under PUBLIC_MODE and by
 * rewriteEditionForExport for the static export, so neither surface can
 * leak a dry run even if a component forgot to check.
 */
export function isPublicDeepDive(dd: NewsletterDeepDive | null | undefined): dd is NewsletterDeepDive {
  return !!dd && dd.gate_passed === true && dd.dry_run !== true && typeof dd.body_md === "string" && dd.body_md.trim() !== "";
}

export function publicDeepDive(dd: NewsletterDeepDive | null | undefined): NewsletterDeepDive | null {
  return isPublicDeepDive(dd) ? dd : null;
}

export interface EditionSummary {
  id: number;
  year: number;
  week: number;
  total_signals: number;
  created_at: string;
}

/* ---------- URL scheme ---------- */

const EDITION_SLUG_RE = /^(\d{4})-w(\d{2})$/;

/** "2026-w35" — zero-padded so the archive sorts as text. */
export function editionSlug(year: number, week: number): string {
  return `${year}-w${String(week).padStart(2, "0")}`;
}

export function editionPath(year: number, week: number): string {
  return `/trends/newsletter/${editionSlug(year, week)}`;
}

/** Exact form only (one URL per edition): "2026-w5" or "2026-W35" is a 404. */
export function parseEditionSlug(slug: string): { year: number; week: number } | null {
  const m = EDITION_SLUG_RE.exec(slug);
  if (!m) return null;
  const year = Number(m[1]);
  const week = Number(m[2]);
  if (year < 2000 || year > 2999 || week < 1 || week > 53) return null;
  return { year, week };
}

/* ---------- ISO week dates (pure UTC arithmetic, no clock) ---------- */

/** Monday of ISO week `week` in ISO year `year`, as a UTC Date. */
export function isoWeekMonday(year: number, week: number): Date {
  // 4 January is always inside ISO week 1.
  const jan4 = Date.UTC(year, 0, 4);
  const jan4Weekday = new Date(jan4).getUTCDay() || 7; // Mon=1 … Sun=7
  const week1Monday = jan4 - (jan4Weekday - 1) * 86_400_000;
  return new Date(week1Monday + (week - 1) * 7 * 86_400_000);
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "24–30 Aug 2026" / "28 Sep – 4 Oct 2026" / "29 Dec 2025 – 4 Jan 2026". */
export function isoWeekRangeLabel(year: number, week: number): string {
  const mon = isoWeekMonday(year, week);
  const sun = new Date(mon.getTime() + 6 * 86_400_000);
  const d = (t: Date) => t.getUTCDate();
  const m = (t: Date) => MONTHS[t.getUTCMonth()];
  const y = (t: Date) => t.getUTCFullYear();
  if (y(mon) !== y(sun)) return `${d(mon)} ${m(mon)} ${y(mon)} – ${d(sun)} ${m(sun)} ${y(sun)}`;
  if (m(mon) !== m(sun)) return `${d(mon)} ${m(mon)} – ${d(sun)} ${m(sun)} ${y(sun)}`;
  return `${d(mon)}–${d(sun)} ${m(sun)} ${y(sun)}`;
}

/** ISO date (YYYY-MM-DD) of the edition's Monday, for <time dateTime>. */
export function isoWeekMondayIso(year: number, week: number): string {
  return isoWeekMonday(year, week).toISOString().slice(0, 10);
}

/* ---------- Link rule ---------- */

export interface LinkContext {
  /** Slugs that exist as pages in this build (published AND inside the article window). */
  inWindow: ReadonlySet<string>;
  /** Primary source per slug, for articles that are not in the window. */
  sourceBySlug: ReadonlyMap<string, string>;
}

const TREND_HREF_RE = /^\/trends\/([^/?#]+)$/;

/** The slug of a `/trends/<slug>` article href, else null (`/trends/mega`, `/trends`, absolute). */
export function articleSlugOf(href: string): string | null {
  const m = TREND_HREF_RE.exec(href.trim());
  if (!m) return null;
  const slug = m[1];
  // Article slugs end in "-<id>" (the 410 pattern in trends/.htaccess);
  // "mega", "methodology", "newsletter" are hubs and stay as they are.
  return /-[0-9]+$/.test(slug) ? slug : null;
}

/**
 * Resolve one href for the export. Returns the href to use, or null when the
 * label must be rendered without a link. Non-article hrefs pass through
 * unchanged (safeHref is applied at render time as before).
 */
export function resolveEditionHref(href: string, ctx: LinkContext): string | null {
  const slug = articleSlugOf(href);
  if (!slug) return href;
  if (ctx.inWindow.has(slug)) return `/trends/${slug}`;
  const source = ctx.sourceBySlug.get(slug);
  return source ? safeHref(source) : null;
}

const MD_LINK_RE = /\[([^\]]+)\]\(([^)]+)\)/g;

/** Rewrite the markdown links of an edition text; unlinkable ones become their label. */
export function rewriteMarkdownLinks(text: string, ctx: LinkContext): string {
  return text.replace(MD_LINK_RE, (_m, label: string, href: string) => {
    const target = resolveEditionHref(href, ctx);
    return target ? `[${label}](${target})` : label;
  });
}

/** Every `/trends/<slug>` article slug an edition refers to (text + trend_refs). */
export function collectEditionSlugs(edition: NewsletterEdition): string[] {
  const slugs = new Set<string>();
  const scan = (text: string | undefined) => {
    if (!text) return;
    for (const m of text.matchAll(MD_LINK_RE)) {
      const slug = articleSlugOf(m[2]);
      if (slug) slugs.add(slug);
    }
  };
  scan(edition.editorial);
  for (const v of Object.values(edition.vertical_summaries ?? {})) scan(v);
  for (const refs of Object.values(edition.trend_refs ?? {})) {
    for (const r of refs) if (r.slug) slugs.add(r.slug);
  }
  return [...slugs].sort();
}

/** Sources the edition itself carries (trend_refs.source_url, W32+). */
export function editionSources(edition: NewsletterEdition): Map<string, string> {
  const out = new Map<string, string>();
  for (const refs of Object.values(edition.trend_refs ?? {})) {
    for (const r of refs) if (r.slug && r.source_url) out.set(r.slug, r.source_url);
  }
  return out;
}

/**
 * The edition as the export renders it: article links re-pointed by the
 * rule above, `trend_refs[].href` resolved (string | null). Pure — the
 * caller supplies the window membership and the sources.
 */
export function rewriteEditionForExport(edition: NewsletterEdition, ctx: LinkContext): NewsletterEdition {
  const vertical_summaries: Record<string, string> = {};
  for (const [v, text] of Object.entries(edition.vertical_summaries ?? {})) {
    vertical_summaries[v] = rewriteMarkdownLinks(text, ctx);
  }
  const trend_refs: Record<string, TrendRef[]> = {};
  for (const [v, refs] of Object.entries(edition.trend_refs ?? {})) {
    trend_refs[v] = refs.map((r) => ({
      ...r,
      href: resolveEditionHref(`/trends/${r.slug}`, ctx),
    }));
  }
  return {
    ...edition,
    editorial: rewriteMarkdownLinks(edition.editorial ?? "", ctx),
    vertical_summaries,
    trend_refs,
    // #96: the export never carries a dry-run or gate-failed deep dive.
    deep_dive: publicDeepDive(edition.deep_dive),
  };
}

/** Neighbours of an edition inside the (newest-first) archive list. */
export function editionNeighbours<T extends { year: number; week: number }>(
  archive: readonly T[],
  year: number,
  week: number
): { previous: T | null; next: T | null } {
  const idx = archive.findIndex((a) => a.year === year && a.week === week);
  if (idx < 0) return { previous: null, next: null };
  return {
    previous: idx < archive.length - 1 ? archive[idx + 1] : null, // older
    next: idx > 0 ? archive[idx - 1] : null, // newer
  };
}

/** Meta description of an edition: first editorial paragraph, links stripped, ≤ 160 chars. */
export function editionExcerpt(editorial: string | null | undefined, max?: number): string {
  const first = (editorial ?? "").split("\n\n")[0] ?? "";
  const plain = first.replace(MD_LINK_RE, (_m, label: string) => label);
  return truncateSummary(plain, max);
}
