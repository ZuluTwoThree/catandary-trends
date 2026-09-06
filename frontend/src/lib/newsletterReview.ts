import { q, q1 } from "./pg";

/**
 * The release desk's data layer (owner mandate 2026-09-06).
 *
 * `newsletter_editions.approved_at` is the human-in-the-loop gate in front of
 * pipeline/newsletter_sender.py: no edition is mailed before a person has read
 * it and released it. This module lists the editions with that state, and
 * writes / withdraws the release.
 *
 * Withdrawal is possible only while `sent_at` is empty — once an issue has
 * gone out, un-releasing it would claim something untrue about a mail that is
 * already in inboxes. The SQL enforces that, not just the button.
 *
 * Every caller is a Server Action guarded by canReview() + same-origin
 * (app/trends/newsletter/review/actions.ts); the route itself never ships in
 * the public export (lib/publicMode.ts BLOCKED_PREFIXES).
 */

export type EditionState = "draft" | "released" | "sent";

export interface EditionApproval {
  id: number;
  year: number;
  week: number;
  total_signals: number;
  created_at: string;
  approved_at: string | null;
  approved_by: string | null;
  approval_note: string | null;
  sent_at: string | null;
  recipients_count: number | null;
  /** True when the edition carries a deep dive record of any kind (#96). */
  has_deep_dive: boolean;
}

/** Sent beats released beats draft — the state a reader cares about. */
export function editionState(e: Pick<EditionApproval, "approved_at" | "sent_at">): EditionState {
  if (e.sent_at) return "sent";
  return e.approved_at ? "released" : "draft";
}

const COLUMNS = `id, year, week, total_signals,
       created_at::text AS created_at,
       approved_at::text AS approved_at, approved_by, approval_note,
       sent_at::text AS sent_at, recipients_count,
       (deep_dive IS NOT NULL) AS has_deep_dive`;

/** Newest first. A missing table (fresh DB) yields [] instead of a crash. */
export async function listEditionApprovals(limit = 30): Promise<EditionApproval[]> {
  const exists = await q1<{ ok: string | null }>(
    "SELECT to_regclass('newsletter_editions')::text AS ok"
  );
  if (!exists?.ok) return [];
  return q<EditionApproval>(
    `SELECT ${COLUMNS} FROM newsletter_editions ORDER BY year DESC, week DESC LIMIT $1`,
    [limit]
  );
}

export async function getEditionApproval(year: number, week: number): Promise<EditionApproval | null> {
  return q1<EditionApproval>(
    `SELECT ${COLUMNS} FROM newsletter_editions WHERE year = $1 AND week = $2 LIMIT 1`,
    [year, week]
  );
}

/**
 * Release an edition for sending. Idempotent on an already released one
 * (the note is refreshed), refused on a sent one — there is nothing left to
 * release once it is out.
 */
export async function releaseEdition(
  year: number,
  week: number,
  by: string,
  note: string | null
): Promise<boolean> {
  const rows = await q<{ id: number }>(
    `UPDATE newsletter_editions
        SET approved_at = NOW(), approved_by = $3, approval_note = $4
      WHERE year = $1 AND week = $2 AND sent_at IS NULL
      RETURNING id`,
    [year, week, by, note]
  );
  return rows.length > 0;
}

/** Withdraw a release — only while the edition has not been sent. */
export async function withdrawRelease(year: number, week: number): Promise<boolean> {
  const rows = await q<{ id: number }>(
    `UPDATE newsletter_editions
        SET approved_at = NULL, approved_by = NULL, approval_note = NULL
      WHERE year = $1 AND week = $2 AND sent_at IS NULL
      RETURNING id`,
    [year, week]
  );
  return rows.length > 0;
}
