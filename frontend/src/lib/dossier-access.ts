import { AUTH_ENABLED, getSession } from "./auth";

/**
 * Access guard for the owner-only dossier desk (/trends/dossiers).
 *
 * Scouting dossiers are proprietary owner documents (owner decision
 * 2026-09-01): orders are placed only by the owner, results are read only by
 * the owner. Same two-condition shape as the review queue guard
 * (lib/review-access.ts, issue #71):
 *
 *   1. DOSSIERS_ENABLED=1 must be set. Off by default, so any deployment that
 *      knows nothing about dossiers simply 404s — the safe direction. The
 *      public deployment additionally blocks the route outright via
 *      PUBLIC_MODE (lib/publicMode.ts).
 *   2. If AUTH_ENABLED=1, a signed-in session is additionally required.
 *
 * Today the app runs on localhost only (AUTH_ENABLED=0), so the flag alone is
 * the boundary; turning auth on tightens this automatically.
 */
export const DOSSIERS_ENABLED = process.env.DOSSIERS_ENABLED === "1";

export async function canManageDossiers(): Promise<boolean> {
  if (!DOSSIERS_ENABLED) return false;
  if (!AUTH_ENABLED) return true;
  return (await getSession()) !== null;
}
