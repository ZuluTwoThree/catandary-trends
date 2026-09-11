import { isPublicMode } from "./publicMode";
import { isStaticExport } from "./renderMode";

/**
 * Access guard for the ops dashboard (#104), same shape as `canReview()`:
 * open on the owner instance, closed under PUBLIC_MODE and in the static
 * export. The route is also in BLOCKED_PREFIXES (proxy 404) and in
 * static-export.exclude (never built) — this is the third lock, on the page.
 */
export function canOps(): boolean {
  return !isPublicMode() && !isStaticExport();
}
