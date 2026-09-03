import { isPublicMode } from "./publicMode";
import { isStaticExport } from "./renderMode";

/**
 * Access guard for the owner dossier desk (/trends/dossiers, issue #95).
 *
 * Scouting dossiers are proprietary owner documents (owner decision
 * 2026-09-01): orders are placed only by the owner, results are read only by
 * the owner. Since #93 there are no accounts, so the rule has the same static
 * two-sided shape as the review queue guard (lib/review-access.ts):
 *
 *   - owner instance (PUBLIC_MODE unset): OPEN by default — the desk is part
 *     of the owner app like /trends/review and /trends/foresight. The single
 *     env flag is an emergency-off switch only: DOSSIERS_ENABLED=0 → 404.
 *   - PUBLIC_MODE=1 preview and the static export: CLOSED, always. The
 *     export does not even build the route (frontend/static-export.exclude),
 *     the preview 404s it via proxy.ts; this guard is the third lock on the
 *     Server Actions behind it (which also start the worker, i.e. GPU work).
 */
export function dossiersEnabled(): boolean {
  return process.env.DOSSIERS_ENABLED !== "0";
}

export function canManageDossiers(): boolean {
  return dossiersEnabled() && !isPublicMode() && !isStaticExport();
}
