import { AUTH_ENABLED, getSession } from "./auth";

/**
 * Access guard for the review queue (issue #71).
 *
 * Publishing and rejecting are WRITES to live content, so this must never be
 * usable anonymously from the internet. Two independent conditions:
 *
 *   1. REVIEW_ENABLED=1 must be set. Off by default, so a deployment that
 *      knows nothing about the review queue simply 404s — the safe direction.
 *   2. If AUTH_ENABLED=1, a signed-in session is additionally required.
 *
 * Today the app runs on localhost only (AUTH_ENABLED=0), so the flag alone is
 * the boundary. Before the app goes public, turn AUTH_ENABLED on — then this
 * guard tightens automatically and no code has to change.
 */
export const REVIEW_ENABLED = process.env.REVIEW_ENABLED === "1";

export async function canReview(): Promise<boolean> {
  if (!REVIEW_ENABLED) return false;
  if (!AUTH_ENABLED) return true;
  return (await getSession()) !== null;
}
