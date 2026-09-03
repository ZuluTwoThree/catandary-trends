import { isPublicMode } from "./publicMode";
import { isStaticExport } from "./renderMode";

/**
 * Access guard for the review queue (issue #71).
 *
 * Publishing and rejecting are WRITES to live content, so this must never be
 * reachable on a public deployment. Since #93 (no accounts, no auth — the app
 * runs only on the owner's workstation) the rule is two-sided and static:
 *
 *   - owner instance (PUBLIC_MODE unset): open — the review queue is an
 *     owner tool like the rest of /trends/foresight;
 *   - PUBLIC_MODE=1 preview and the static export: closed, always. The
 *     export does not even build the route (frontend/static-export.exclude),
 *     the preview 404s it via proxy.ts; this guard is the third lock on the
 *     Server Actions behind it.
 *
 * Reachability of the owner instance itself (LAN/Tailnet) is an ops matter —
 * see Owner-Aktion 2 in docs/launch/09_launch_plan_2026-09-02.md.
 */
export function canReview(): boolean {
  return !isPublicMode() && !isStaticExport();
}
