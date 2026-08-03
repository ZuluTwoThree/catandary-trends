import { q, q1 } from "./pg";
import { ungroundedSpecifics, sourceFromParts } from "./grounding";

/**
 * Review queue for articles the grounding gate held back (issue #71).
 *
 * The nightly auto-publisher refuses to publish a high-confidence draft whose
 * body states a figure or date absent from its source (pipeline/auto_publisher
 * .py). Those drafts used to just accumulate — nobody was told, and there was
 * no way to judge them. This module backs the review UI and its two actions.
 *
 * Scope: ONLY grounding holds, i.e. drafts at or above the auto-publish
 * confidence threshold. Low-confidence drafts (the ~6k "skipped") are a
 * classification matter and deliberately out of scope.
 */

/** Mirrors AUTO_PUBLISH_CONFIDENCE in pipeline/config.py. */
export const REVIEW_CONFIDENCE_MIN = 0.85;

export interface ReviewItem {
  id: number;
  slug: string;
  title: string;
  body: string;
  summary: string | null;
  vertical: string | null;
  sourceName: string | null;
  sourceUrl: string | null;
  confidence: number | null;
  createdAt: string;
  /** The material the content model saw — what the body is judged against. */
  sourceText: string;
  /** Tokens in the body that the source does not support. */
  flagged: string[];
  /** True when the body is cut off mid-sentence (the other publish gate). */
  truncated: boolean;
}

const TERMINAL = /[.!?"”]$/;

interface Row {
  id: number;
  slug: string;
  title_en: string;
  body_en: string | null;
  summary_en: string | null;
  primary_vertical: string | null;
  source_name: string | null;
  source_url: string | null;
  confidence: number | null;
  created_at: string;
  re_title: string | null;
  raw_content: string | null;
  excerpt: string | null;
  extraction_json: string | null;
}

function toItem(r: Row): ReviewItem {
  let ext: Record<string, unknown> = {};
  if (r.extraction_json) {
    try {
      ext = JSON.parse(r.extraction_json) ?? {};
    } catch {
      ext = {};
    }
  }
  const asList = (v: unknown): string[] =>
    Array.isArray(v) ? v.map(String) : [];

  // Same assembly the publish gate uses, so the UI judges by that standard.
  const sourceText = sourceFromParts(
    r.re_title,
    r.raw_content || r.excerpt,
    asList(ext.key_claims),
    asList(ext.key_figures),
    asList(ext.dates),
    asList(ext.quotes),
    asList(ext.geography)
  );
  const body = r.body_en ?? "";
  return {
    id: r.id,
    slug: r.slug,
    title: r.title_en,
    body,
    summary: r.summary_en,
    vertical: r.primary_vertical,
    sourceName: r.source_name,
    sourceUrl: r.source_url,
    confidence: r.confidence,
    createdAt: r.created_at,
    sourceText,
    flagged: ungroundedSpecifics(body, sourceText),
    truncated: body.trim().length > 0 && !TERMINAL.test(body.trim()),
  };
}

const SELECT = `
  SELECT t.id, t.slug, t.title_en, t.body_en, t.summary_en, t.primary_vertical,
         t.source_name, t.source_url, t.confidence, t.created_at::text AS created_at,
         re.title AS re_title, re.raw_content, re.excerpt, re.extraction_json
    FROM trends t
    LEFT JOIN raw_entries re ON re.id = t.raw_entry_id
   WHERE t.status = 'draft' AND t.confidence >= $1`;

/**
 * Held drafts, newest first. `sinceHours` narrows to the current morning's
 * batch; omit it for the whole backlog.
 */
export async function getHeldDrafts(
  opts: { sinceHours?: number; limit?: number } = {}
): Promise<ReviewItem[]> {
  const params: unknown[] = [REVIEW_CONFIDENCE_MIN];
  let sql = SELECT;
  if (opts.sinceHours) {
    params.push(`${opts.sinceHours} hours`);
    sql += ` AND t.created_at >= NOW() - $${params.length}::interval`;
  }
  params.push(opts.limit ?? 100);
  sql += ` ORDER BY t.created_at DESC LIMIT $${params.length}`;

  const rows = await q<Row>(sql, params);
  // Only rows a gate actually objects to — a draft can sit here for unrelated
  // reasons, and showing those would waste the reviewer's morning.
  return rows.map(toItem).filter((i) => i.flagged.length > 0 || i.truncated);
}

export interface ReviewCounts {
  total: number;
  today: number;
  oldest: string | null;
}

export async function getReviewCounts(): Promise<ReviewCounts> {
  const r = await q1<{ total: number; today: number; oldest: string | null }>(
    `SELECT COUNT(*)::int AS total,
            COUNT(*) FILTER (WHERE created_at >= CURRENT_DATE)::int AS today,
            MIN(created_at)::date::text AS oldest
       FROM trends WHERE status = 'draft' AND confidence >= $1`,
    [REVIEW_CONFIDENCE_MIN]
  );
  return { total: r?.total ?? 0, today: r?.today ?? 0, oldest: r?.oldest ?? null };
}

/**
 * Publish a reviewed draft. `auto_published` stays false — a human decided,
 * and the distinction matters when auditing how content reached the site.
 * Guarded on status so a double click can't republish something already
 * rejected.
 */
export async function publishReviewed(id: number): Promise<boolean> {
  const rows = await q<{ id: number }>(
    `UPDATE trends
        SET status = 'published', auto_published = false,
            published_at = COALESCE(published_at, NOW())
      WHERE id = $1 AND status = 'draft'
      RETURNING id`,
    [id]
  );
  return rows.length > 0;
}

/** Reject a draft: it leaves the pool, so the nightly gate stops re-checking it. */
export async function rejectReviewed(id: number): Promise<boolean> {
  const rows = await q<{ id: number }>(
    `UPDATE trends SET status = 'rejected'
      WHERE id = $1 AND status = 'draft'
      RETURNING id`,
    [id]
  );
  return rows.length > 0;
}
