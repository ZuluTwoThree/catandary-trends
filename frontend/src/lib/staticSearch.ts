/**
 * Client-side search of the static export (design Schritt 5 / follow-up D,
 * docs/audits/2026-09-02_static_export_design.md; hosting notes in
 * docs/launch/HOSTING_HETZNER.md, "Suche im Export").
 *
 * The webspace has no server, so the feed's `?q=` search (Postgres FTS) does
 * not exist there. Instead the build writes ONE JSON index of the public
 * window — /trends/index.json, `app/trends/index.json/route.ts` — and the
 * browser filters it (components/StaticSearch.tsx). This module is the pure
 * part: index rows -> entries (build side), entries -> hits (client side),
 * the URL-hash state, and the adapter that lets TrendCard render a hit.
 *
 * Everything here is deterministic: no clock, no randomness, a total order
 * (`sort_date DESC, id DESC` — the listing's order) — the export is diffed
 * build against build.
 */
import type { PublicIndexRow } from "./db";
import {
  MEGA_TRENDS,
  PESTEL,
  VERTICALS,
  type PestelDimension,
  type Trend,
  type Vertical,
} from "./types";

export const INDEX_PATH = "/trends/index.json";
/** Summary length in the index (characters, ellipsis included). */
export const SUMMARY_MAX = 160;
/** Hits rendered as cards; the counter still shows the full match count. */
export const MAX_RESULTS = 50;
/** Theme chips derived from the index: the most frequent keys. */
export const MEGA_CHIP_LIMIT = 28;

/** Source label the card shows. `research` folds the research signal type
 *  in (TrendCard labels those "Research" whatever the feed type). */
export type IndexSourceType = "trade_media" | "press_wire" | "brand" | "api" | "research";

export interface IndexEntry {
  slug: string;
  title: string;
  summary: string;
  /** Primary vertical FIRST, then the cross-industry ones. */
  verticals: Vertical[];
  pestel: PestelDimension[];
  mega_trend: string | null;
  /** ISO date (YYYY-MM-DD) of the listing's timeline date. */
  sort_date: string | null;
  trend_score: number | null;
  source_name: string | null;
  source_type: IndexSourceType | null;
}

export interface SearchFilters {
  q: string;
  verticals: Vertical[];
  pestel: PestelDimension[];
  mega: string[];
}

export const EMPTY_FILTERS: SearchFilters = { q: "", verticals: [], pestel: [], mega: [] };

/* ---------- build side: rows -> index ---------- */

const VERTICAL_IDS = new Set<string>(VERTICALS.map((v) => v.id));
const PESTEL_IDS = new Set<string>(PESTEL.map((p) => p.id));
const SOURCE_TYPES = new Set<string>(["trade_media", "press_wire", "brand", "api", "research"]);

/** Numeric id at the end of every article slug (`…-<id>`); 0 if absent. */
export function entryId(slug: string): number {
  const m = /-(\d+)$/.exec(slug);
  return m ? Number(m[1]) : 0;
}

/**
 * Whitespace-collapsed summary of at most `max` characters. A cut lands on a
 * word boundary (never mid-word, never after a dangling comma) and ends in a
 * single ellipsis that counts toward the limit.
 */
export function truncateSummary(text: string | null | undefined, max: number = SUMMARY_MAX): string {
  const clean = (text ?? "").replace(/\s+/g, " ").trim();
  if (clean.length <= max) return clean;
  const room = max - 1; // the ellipsis
  let cut = clean.slice(0, room + 1);
  const lastSpace = cut.lastIndexOf(" ");
  // Cut at the last word boundary unless that would throw away most of the
  // room (one very long token) — then a hard cut is the lesser evil.
  cut = lastSpace >= Math.floor(room / 2) ? cut.slice(0, lastSpace) : cut.slice(0, room);
  cut = cut.replace(/[\s,;:–—-]+$/u, "");
  return `${cut}…`;
}

function asStringArray(v: unknown): string[] {
  if (Array.isArray(v)) return v.filter((x): x is string => typeof x === "string");
  if (typeof v === "string" && v) {
    try {
      const parsed = JSON.parse(v);
      return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === "string") : [];
    } catch {
      return [];
    }
  }
  return [];
}

/** `YYYY-MM-DD` of a Postgres text timestamp (or ISO string); null if unusable. */
export function isoDate(value: string | null | undefined): string | null {
  if (!value) return null;
  const m = /^(\d{4}-\d{2}-\d{2})/.exec(value);
  return m ? m[1] : null;
}

function compareRows(a: PublicIndexRow, b: PublicIndexRow): number {
  // Postgres text timestamps ("2026-09-02 13:00:00[.ffffff]") order
  // lexicographically; nulls last, then the id tiebreaker — the listing's
  // `sort_date DESC NULLS LAST, id DESC`.
  const da = a.sort_date ?? "";
  const db = b.sort_date ?? "";
  if (da !== db) {
    if (!da) return 1;
    if (!db) return -1;
    return da < db ? 1 : -1;
  }
  return entryId(b.slug) - entryId(a.slug);
}

export function rowToEntry(row: PublicIndexRow): IndexEntry {
  const primary = VERTICAL_IDS.has(row.primary_vertical) ? (row.primary_vertical as Vertical) : null;
  const others = asStringArray(row.verticals).filter(
    (v, i, arr) => VERTICAL_IDS.has(v) && v !== primary && arr.indexOf(v) === i
  ) as Vertical[];
  const pestel = asStringArray(row.pestel).filter(
    (p, i, arr) => PESTEL_IDS.has(p) && arr.indexOf(p) === i
  ) as PestelDimension[];
  const rawType = row.trend_signal_type === "research" ? "research" : row.source_type;
  const source_type =
    rawType && SOURCE_TYPES.has(rawType) ? (rawType as IndexSourceType) : null;
  return {
    slug: row.slug,
    title: (row.title_en ?? "").replace(/\s+/g, " ").trim(),
    summary: truncateSummary(row.summary_en),
    verticals: primary ? [primary, ...others] : others,
    pestel,
    mega_trend: row.mega_trend || null,
    sort_date: isoDate(row.sort_date),
    trend_score: typeof row.trend_score === "number" ? row.trend_score : null,
    source_name: row.source_name || null,
    source_type,
  };
}

/** Rows (any order) -> entries in the listing's order. Duplicate slugs
 *  collapse to their first occurrence. */
export function buildIndexEntries(rows: PublicIndexRow[]): IndexEntry[] {
  const sorted = [...rows].sort(compareRows);
  const seen = new Set<string>();
  const out: IndexEntry[] = [];
  for (const row of sorted) {
    if (!row.slug || seen.has(row.slug)) continue;
    seen.add(row.slug);
    out.push(rowToEntry(row));
  }
  return out;
}

/**
 * One JSON array, one entry per line: `[{…},\n{…}]\n` — valid JSON whose
 * line count equals the entry count (`wc -l` = articles, the build's check).
 */
export function serializeIndex(entries: IndexEntry[]): string {
  return `[${entries.map((e) => JSON.stringify(e)).join(",\n")}]\n`;
}

/* ---------- client side: entries -> hits ---------- */

/** Lower-cased search terms, whitespace-split, de-duplicated, order kept. */
export function tokenize(q: string): string[] {
  const out: string[] = [];
  for (const t of q.toLowerCase().split(/\s+/)) {
    if (t && !out.includes(t)) out.push(t);
  }
  return out;
}

export interface PreparedEntry {
  entry: IndexEntry;
  title: string;
  text: string;
}

/** Lower-cased haystacks, computed once per index load instead of per keystroke. */
export function prepareIndex(entries: IndexEntry[]): PreparedEntry[] {
  return entries.map((entry) => {
    const title = entry.title.toLowerCase();
    return { entry, title, text: `${title} ${entry.summary.toLowerCase()}` };
  });
}

/** Every term must occur in title or summary (substring, AND). */
export function matchesText(p: PreparedEntry, tokens: string[]): boolean {
  return tokens.every((t) => p.text.includes(t));
}

/** Number of terms found in the title — the rank (title hits before summary hits). */
export function titleHits(p: PreparedEntry, tokens: string[]): number {
  let n = 0;
  for (const t of tokens) if (p.title.includes(t)) n++;
  return n;
}

/**
 * Chip filter: AND between dimensions, OR within one. The vertical chip
 * matches the PRIMARY vertical only — the same rule as the /trends/v/<v>
 * pages, so an empty query with one vertical chip equals that listing.
 */
export function matchesChips(entry: IndexEntry, filters: SearchFilters): boolean {
  if (filters.verticals.length > 0) {
    const primary = entry.verticals[0];
    if (!primary || !filters.verticals.includes(primary)) return false;
  }
  if (filters.pestel.length > 0 && !entry.pestel.some((p) => filters.pestel.includes(p))) {
    return false;
  }
  if (filters.mega.length > 0 && (!entry.mega_trend || !filters.mega.includes(entry.mega_trend))) {
    return false;
  }
  return true;
}

export interface SearchResult {
  total: number;
  hits: IndexEntry[];
}

/**
 * Filter + rank. Ranking: title hits (desc), then the index order — which is
 * `sort_date DESC, id DESC` — via a stable sort. At most `limit` hits are
 * returned; `total` counts them all.
 */
export function search(
  prepared: PreparedEntry[],
  filters: SearchFilters,
  limit: number = MAX_RESULTS
): SearchResult {
  const tokens = tokenize(filters.q);
  const matched: { p: PreparedEntry; rank: number }[] = [];
  for (const p of prepared) {
    if (!matchesChips(p.entry, filters)) continue;
    if (tokens.length > 0 && !matchesText(p, tokens)) continue;
    matched.push({ p, rank: tokens.length > 0 ? titleHits(p, tokens) : 0 });
  }
  if (tokens.length > 0) matched.sort((a, b) => b.rank - a.rank);
  return { total: matched.length, hits: matched.slice(0, limit).map((m) => m.p.entry) };
}

export interface MegaOption {
  key: string;
  name: string;
  count: number;
}

function humanizeKey(key: string): string {
  return key
    .split("_")
    .filter(Boolean)
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(" ");
}

/** The `limit` most frequent mega themes of the index (ties: key order). */
export function megaOptions(entries: IndexEntry[], limit: number = MEGA_CHIP_LIMIT): MegaOption[] {
  const counts = new Map<string, number>();
  for (const e of entries) {
    if (e.mega_trend) counts.set(e.mega_trend, (counts.get(e.mega_trend) ?? 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0))
    .slice(0, limit)
    .map(([key, count]) => ({
      key,
      name: MEGA_TRENDS.find((m) => m.key === key)?.name_en ?? humanizeKey(key),
      count,
    }));
}

/* ---------- state helpers ---------- */

function sameSet(a: readonly string[], b: readonly string[]): boolean {
  if (a.length !== b.length) return false;
  const s = new Set(a);
  return b.every((x) => s.has(x));
}

/** A search is "active" (results replace the listing) once anything differs
 *  from the page's defaults — on /trends/v/tech the TECH chip is the default. */
export function isActive(filters: SearchFilters, defaults: SearchFilters = EMPTY_FILTERS): boolean {
  return (
    filters.q.trim() !== "" ||
    filters.pestel.length > 0 ||
    filters.mega.length > 0 ||
    !sameSet(filters.verticals, defaults.verticals)
  );
}

export function toggleValue<T>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((x) => x !== value) : [...list, value];
}

/**
 * URL-hash form of the state (`#q=battery&v=TECH,ECO&pestel=T&mega=<key>`):
 * shareable and back-button-free (replaceState). Unknown ids are dropped on
 * parse; the empty state serializes to "".
 */
export function buildSearchHash(filters: SearchFilters): string {
  const params = new URLSearchParams();
  if (filters.q.trim()) params.set("q", filters.q.trim());
  if (filters.verticals.length) params.set("v", filters.verticals.join(","));
  if (filters.pestel.length) params.set("pestel", filters.pestel.join(","));
  if (filters.mega.length) params.set("mega", filters.mega.join(","));
  const s = params.toString();
  return s ? `#${s}` : "";
}

export function parseSearchHash(hash: string): SearchFilters | null {
  const raw = hash.startsWith("#") ? hash.slice(1) : hash;
  if (!raw) return null;
  const params = new URLSearchParams(raw);
  const list = (key: string) =>
    (params.get(key) ?? "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
  const filters: SearchFilters = {
    q: (params.get("q") ?? "").slice(0, 200),
    verticals: list("v").filter((v, i, a) => VERTICAL_IDS.has(v) && a.indexOf(v) === i) as Vertical[],
    pestel: list("pestel").filter((p, i, a) => PESTEL_IDS.has(p) && a.indexOf(p) === i) as PestelDimension[],
    mega: list("mega").filter((m, i, a) => /^[a-z0-9_]+$/.test(m) && a.indexOf(m) === i),
  };
  return isActive(filters) ? filters : null;
}

/* ---------- card adapter ---------- */

/**
 * The `Trend` shape TrendCard renders, from an index entry. Fields the index
 * does not carry get inert defaults; the date is set to local noon so the
 * card's `toLocaleDateString` shows the same calendar day in every zone.
 */
export function entryToTrend(entry: IndexEntry): Trend {
  const primary = entry.verticals[0] ?? "TECH";
  const date = entry.sort_date ? `${entry.sort_date}T12:00:00` : null;
  return {
    id: entryId(entry.slug),
    raw_entry_id: 0,
    title_en: entry.title,
    slug: entry.slug,
    summary_en: entry.summary,
    body_en: null,
    verticals: entry.verticals,
    primary_vertical: primary,
    pestel: entry.pestel,
    tags: [],
    trend_signal_type: entry.source_type === "research" ? "research" : "market_shift",
    mega_trend: entry.mega_trend,
    macro_trend: null,
    trend_level: null,
    brands: [],
    companies: [],
    regions: [],
    trend_score: entry.trend_score,
    confidence: null,
    source_url: "",
    source_name: entry.source_name,
    source_date: date,
    source_type: entry.source_type === "research" ? null : entry.source_type,
    status: "published",
    auto_published: false,
    published_at: date,
    created_at: date ?? "",
    sort_date: date,
  };
}
