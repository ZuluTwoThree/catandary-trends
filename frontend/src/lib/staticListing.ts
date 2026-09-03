/**
 * URL scheme and arithmetic of the STATIC listing routes (design Schritt 4,
 * docs/audits/2026-09-02_static_export_design.md):
 *
 *   /trends                       newest 24, page 1
 *   /trends/page/<n>              page n (n >= 2)
 *   /trends/v/<vertical>          one vertical, page 1   (vertical = lowercase id)
 *   /trends/v/<vertical>/page/<n>
 *
 * Every page is a real file in the export (generateStaticParams), sorted
 * `sort_date DESC, id DESC` (lib/db.ts buildOrderBy — the id tiebreaker is
 * what keeps page boundaries build-stable). The search-param feed of the
 * workstation instance (`/trends?v=…&page=…`) is untouched; these routes
 * exist there too, rendered per request, but nothing links to them outside
 * the export.
 *
 * Page 1 has exactly ONE URL (the base path): `/trends/page/1` is a 404, so
 * no page ever exists under two addresses.
 */
import { VERTICALS, type Vertical } from "./types";
import { isStaticExport } from "./renderMode";

export const STATIC_PAGE_SIZE = 24;

/** URL segment of a vertical: the lowercase id ("TECH" -> "tech"). Uppercase
 *  forms are Apache's job (301 in public-export/trends/.htaccess). */
export function verticalSlug(vertical: Vertical): string {
  return vertical.toLowerCase();
}

/** Exact lowercase match only — one canonical URL per vertical. */
export function verticalFromSlug(slug: string): Vertical | null {
  const hit = VERTICALS.find((v) => verticalSlug(v.id) === slug);
  return hit ? hit.id : null;
}

export function listingPath(vertical: Vertical | null, page: number): string {
  const base = vertical ? `/trends/v/${verticalSlug(vertical)}` : "/trends";
  return page <= 1 ? base : `${base}/page/${page}`;
}

/** Where a vertical badge (article breadcrumb, mega header) links to: the
 *  static vertical page in the export, the search-param feed elsewhere. */
export function verticalFeedHref(vertical: Vertical): string {
  return isStaticExport() ? listingPath(vertical, 1) : `/trends?v=${vertical}`;
}

export function pageCount(total: number, perPage: number = STATIC_PAGE_SIZE): number {
  return Math.max(1, Math.ceil(Math.max(0, total) / perPage));
}

/** The `[n]` route param: an integer >= 2, else null (page 1 lives at the
 *  base path; "01", "1.5", "-2", "" are all a 404). */
export function parsePageParam(raw: string): number | null {
  if (!/^[1-9][0-9]{0,5}$/.test(raw)) return null;
  const n = Number(raw);
  return n >= 2 ? n : null;
}

/** Page numbers to render in a pagination nav: first, last, ±2 around the
 *  current page; -1 marks a gap. Shared by the search-param and the static
 *  pagination so both look identical. */
export function pageWindow(page: number, totalPages: number): number[] {
  return Array.from({ length: totalPages }, (_, i) => i + 1)
    .filter((p) => p === 1 || p === totalPages || Math.abs(p - page) <= 2)
    .reduce<number[]>((acc, p) => {
      if (acc.length > 0 && p - acc[acc.length - 1] > 1) acc.push(-1);
      acc.push(p);
      return acc;
    }, []);
}
