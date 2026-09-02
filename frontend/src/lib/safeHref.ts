/**
 * Allow-list for hrefs built from data we did not write (security review
 * 2026-09-02, F-3): RSS source links, GLEIF/Companies-House/Wikidata
 * websites, OpenAlex homepages, markdown links inside generated newsletter
 * text and owner-authored analyses. Only `http(s)://` absolute URLs, site-
 * relative paths (`/…`, not `//host`) and fragments pass; anything else —
 * `javascript:`, `data:`, `vbscript:`, protocol-relative, garbage — yields
 * null and the caller renders plain text instead of a link. React only warns
 * about `javascript:` URLs, and a static export has no runtime at all.
 */
const ABSOLUTE_RE = /^https?:\/\/[^\s/?#]+/i;
// Control characters (incl. tab/newline) let "java\nscript:" slip past naive
// scheme checks in some parsers — reject outright.
const CONTROL_RE = /[\x00-\x1f\x7f]/;

export function safeHref(url: string | null | undefined): string | null {
  if (typeof url !== "string") return null;
  const v = url.trim();
  if (!v) return null;
  if (CONTROL_RE.test(v)) return null;
  if (v.startsWith("#")) return v;
  if (v.startsWith("/")) return v.startsWith("//") ? null : v;
  return ABSOLUTE_RE.test(v) ? v : null;
}
