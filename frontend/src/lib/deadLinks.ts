/**
 * Source-link-rot helpers (#48).
 *
 * Pure, DB-free — the actual dead_links lookup lives in db.ts (needs the
 * pool + a defensive table-exists check). This module only holds what a
 * server component needs to render the fallback: the archived-copy URL and
 * the badge copy.
 */

/** Wayback Machine "closest snapshot" shortcut — /web/2/<url> redirects
 *  straight to nearest available capture instead of a bare calendar page.
 *  The target URL is percent-encoded so a `#`/`?`/space in source_url can
 *  never be mis-parsed as part of the archive.org URL itself. */
export function archiveUrl(sourceUrl: string): string {
  return `https://web.archive.org/web/2/${encodeURIComponent(sourceUrl)}`;
}

/** Dezenter Hinweis auf der Artikelseite, wenn der Backlink als tot markiert ist. */
export const DEAD_SOURCE_NOTICE =
  "Original may no longer be available at the publisher";
