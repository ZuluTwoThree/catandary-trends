import { q, q1 } from "./pg";
import { ungroundedSpecifics, ungroundedNames, sourceFromParts } from "./grounding";
import { garbageReasons } from "./content-guard";

/**
 * Review queue for articles the publish gates held back (issue #71, #11).
 *
 * The nightly auto-publisher refuses to publish a high-confidence draft whose
 * body states a figure or date absent from its source (pipeline/auto_publisher
 * .py). Those drafts used to just accumulate — nobody was told, and there was
 * no way to judge them. This module backs the review UI and its actions.
 *
 * Since 2026-09-05 (#11) the gates also hold a body that names a PERSON the
 * source does not name word for word ("Henkel CEO Markus Knobel" for
 * "Henkel-Chef Knobel") and a body the garbage detector rejects (token soup,
 * leaked foreign-script characters). Both are shown here with their reasons.
 *
 * Two queues:
 *  - held drafts: status 'draft' at or above the auto-publish confidence
 *    threshold that a gate objects to (the classic morning queue);
 *  - the re-check queue: status 'review' — rows the corpus re-check
 *    (scripts/recheck_published_grounding.py) or the draft judge moved out of
 *    'published'/'draft', each with a `review_reason` such as
 *    "recheck_2026-09-05:name:Markus Knobel". Nothing in 'review' is public.
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
  /** 'draft' (held by a gate) or 'review' (moved there by the re-check / judge). */
  status: string;
  /** Why the re-check or judge parked it — NULL for gate holds and owner-set rows. */
  reviewReason: string | null;
  /** The material the content model saw — what the body is judged against. */
  sourceText: string;
  /** Tokens in the body that the source does not support. */
  flagged: string[];
  /** Person names the source does not give word for word (#11). */
  names: string[];
  /** Garbage-detector reasons (#11, 2026-09-05): token soup, script leak … */
  garbled: string[];
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
  status: string;
  review_reason: string | null;
  re_title: string | null;
  raw_content: string | null;
  excerpt: string | null;
  extraction_json: string | null;
}

export function toItem(r: Row): ReviewItem {
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
    status: r.status,
    reviewReason: r.review_reason,
    sourceText,
    flagged: ungroundedSpecifics(body, sourceText),
    names: ungroundedNames(body, sourceText),
    garbled: garbageReasons(body, sourceText),
    truncated: body.trim().length > 0 && !TERMINAL.test(body.trim()),
  };
}

/** A gate objects to this row — the only rows worth a reviewer's morning. */
export const hasObjection = (i: ReviewItem): boolean =>
  i.flagged.length > 0 || i.names.length > 0 || i.garbled.length > 0 || i.truncated;

const SELECT_BASE = `
  SELECT t.id, t.slug, t.title_en, t.body_en, t.summary_en, t.primary_vertical,
         t.source_name, t.source_url, t.confidence, t.created_at::text AS created_at,
         t.status, t.review_reason,
         re.title AS re_title, re.raw_content, re.excerpt, re.extraction_json
    FROM trends t
    LEFT JOIN raw_entries re ON re.id = t.raw_entry_id`;

const SELECT_HELD = `${SELECT_BASE}
   WHERE t.status = 'draft' AND t.confidence >= $1`;

const SELECT_RECHECK = `${SELECT_BASE}
   WHERE t.status = 'review'`;

/**
 * Held drafts, newest first. `sinceHours` narrows to the current morning's
 * batch; omit it for the whole backlog.
 */
export async function getHeldDrafts(
  opts: { sinceHours?: number; limit?: number } = {}
): Promise<ReviewItem[]> {
  const params: unknown[] = [REVIEW_CONFIDENCE_MIN];
  let sql = SELECT_HELD;
  if (opts.sinceHours) {
    params.push(`${opts.sinceHours} hours`);
    sql += ` AND t.created_at >= NOW() - $${params.length}::interval`;
  }
  params.push(opts.limit ?? 100);
  sql += ` ORDER BY t.created_at DESC LIMIT $${params.length}`;

  const rows = await q<Row>(sql, params);
  // Only rows a gate actually objects to — a draft can sit here for unrelated
  // reasons, and showing those would waste the reviewer's morning.
  return rows.map(toItem).filter(hasObjection);
}

/**
 * The re-check queue: everything in status 'review', newest first. Rows carry
 * their `review_reason` (e.g. "recheck_2026-09-05:name:Markus Knobel"); the
 * live flags are recomputed so the reviewer sees the current verdict too.
 * `reasonPrefix` narrows to one sweep ("recheck_2026-09-05").
 */
export async function getRecheckQueue(
  opts: { reasonPrefix?: string; limit?: number } = {}
): Promise<ReviewItem[]> {
  const params: unknown[] = [];
  let sql = SELECT_RECHECK;
  if (opts.reasonPrefix) {
    params.push(`${opts.reasonPrefix}%`);
    sql += ` AND t.review_reason LIKE $${params.length}`;
  }
  params.push(opts.limit ?? 100);
  sql += ` ORDER BY t.created_at DESC LIMIT $${params.length}`;
  const rows = await q<Row>(sql, params);
  return rows.map(toItem);
}

export interface ReviewCounts {
  total: number;
  today: number;
  oldest: string | null;
  /** Rows in status 'review' (re-check / judge diversions). Exact SQL count. */
  recheck: number;
}

/**
 * Counts must match what the queue actually LISTS, so they are derived from the
 * same filtered rows rather than from a COUNT(*) over all drafts.
 *
 * A plain SQL count is wrong here: a high-confidence draft can sit in the table
 * with no objection at all (it simply hasn't reached the nightly auto-publisher
 * yet). On 2026-08-04 that made the header claim 101 items against 29 the page
 * could show — a number the reviewer would have to distrust every morning.
 * Grounding runs in JS, so there is no SQL predicate for it. The re-check
 * queue IS a status, so its count is a plain SQL count.
 */
export async function getReviewCounts(): Promise<ReviewCounts> {
  const [rows, rc] = await Promise.all([
    q<Row>(`${SELECT_HELD} ORDER BY t.created_at DESC LIMIT 500`, [REVIEW_CONFIDENCE_MIN]),
    q1<{ n: number }>(`SELECT COUNT(*)::int AS n FROM trends WHERE status = 'review'`, []),
  ]);
  const held = rows.map(toItem).filter(hasObjection);
  const startOfDay = new Date();
  startOfDay.setHours(0, 0, 0, 0);
  const dates = held.map((i) => i.createdAt).sort();
  return {
    total: held.length,
    today: held.filter((i) => new Date(i.createdAt) >= startOfDay).length,
    oldest: dates.length ? dates[0].slice(0, 10) : null,
    recheck: rc?.n ?? 0,
  };
}

/**
 * Publish a reviewed row. `auto_published` stays false — a human decided,
 * and the distinction matters when auditing how content reached the site.
 * Guarded on status so a double click can't republish something already
 * rejected. Accepts both queues: a held draft and a re-check row.
 */
export async function publishReviewed(id: number): Promise<boolean> {
  const rows = await q<{ id: number }>(
    `UPDATE trends
        SET status = 'published', auto_published = false,
            published_at = COALESCE(published_at, NOW()),
            reviewed_at = NOW(), review_reason = NULL
      WHERE id = $1 AND status IN ('draft', 'review')
      RETURNING id`,
    [id]
  );
  return rows.length > 0;
}

/**
 * Reject a row: it leaves the pool, so the nightly gate stops re-checking it.
 * reviewed_at records WHEN — without it a rejection left no trace at all and
 * review progress was unmeasurable (#71). review_reason is kept as the audit
 * trail of why it came here.
 */
export async function rejectReviewed(id: number): Promise<boolean> {
  const rows = await q<{ id: number }>(
    `UPDATE trends SET status = 'rejected', reviewed_at = NOW()
      WHERE id = $1 AND status IN ('draft', 'review')
      RETURNING id`,
    [id]
  );
  return rows.length > 0;
}

/** How often one signal may be sent back before we stop trying. */
export const MAX_REGENERATION_ATTEMPTS = 2;

export type RequeueResult =
  | { ok: true }
  | { ok: false; reason: "not_draft" | "no_source" | "attempts_exhausted" };

/**
 * Send a defective article back to be written again (issue #71).
 *
 * A body that breaks off mid-sentence — or is token soup (#11) — is a failed
 * generation, not a bad story; rejecting it threw the signal away for good.
 * This resets the underlying raw_entry so the next nightly cycle runs it
 * through the whole pipeline again and the current Stage-6 model writes a
 * fresh article.
 *
 * The old row is marked rejected rather than left as a draft, for two reasons:
 * it keeps an audit trail of the failed attempt, and — decisively — its
 * embedding would otherwise still sit in the 30-day dedup window and kill the
 * regenerated article as a duplicate of itself. get_recent_embeddings() skips
 * hand-rejected rows (reviewed_at IS NOT NULL), which is exactly this case.
 *
 * Order matters: the trend is retired FIRST. If the second statement then
 * fails, the outcome is a plain rejection — never an unprocessed entry whose
 * old draft is still live, which would yield two articles for one signal.
 */
export async function requeueForRegeneration(id: number): Promise<RequeueResult> {
  const row = await q1<{ raw_entry_id: number | null; attempts: number }>(
    `SELECT t.raw_entry_id,
            (SELECT COUNT(*)::int FROM trends p
              WHERE p.raw_entry_id = t.raw_entry_id
                AND p.status = 'rejected' AND p.reviewed_at IS NOT NULL) AS attempts
       FROM trends t
      WHERE t.id = $1 AND t.status IN ('draft', 'review')`,
    [id]
  );
  if (!row) return { ok: false, reason: "not_draft" };
  if (row.raw_entry_id == null) return { ok: false, reason: "no_source" };
  // Counts earlier failed attempts on this signal, so a source that truncates
  // every time cannot bounce through the pipeline forever.
  if (row.attempts >= MAX_REGENERATION_ATTEMPTS)
    return { ok: false, reason: "attempts_exhausted" };

  const retired = await q<{ id: number }>(
    `UPDATE trends SET status = 'rejected', reviewed_at = NOW()
      WHERE id = $1 AND status IN ('draft', 'review')
      RETURNING id`,
    [id]
  );
  if (!retired.length) return { ok: false, reason: "not_draft" };

  await q(
    `UPDATE raw_entries
        SET processed = FALSE, filtered_out = FALSE, filter_reason = NULL
      WHERE id = $1`,
    [row.raw_entry_id]
  );
  return { ok: true };
}
