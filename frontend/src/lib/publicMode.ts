/**
 * Public-mode gate (issue #93, Etappe 1).
 *
 * Business model change (owner 2026-08-26): the public site becomes a free
 * lead-gen showcase for Catandary Foresight. The Foresight tool suite,
 * accounts and Stripe checkout stay in daily use on the workstation instance
 * but must not ship on the public deployment.
 *
 * Same shape as AUTH_ENABLED/PAYWALL_ENABLED/REVIEW_ENABLED (see lib/auth.ts,
 * lib/entitlement.ts, lib/review-access.ts): a single env flag, off by
 * default. PUBLIC_MODE=1 blocks the routes below (404); unset/0 changes
 * nothing — today's workstation instance on :3001 runs unset and stays as-is
 * until a deployment deliberately sets it.
 */
export function isPublicMode(): boolean {
  return process.env.PUBLIC_MODE === "1";
}

/**
 * Path prefixes hidden entirely when PUBLIC_MODE=1 — the "Fällt weg" list
 * from issue #93: the Foresight tool suite (all nine /trends/foresight/*
 * routes and their /api/foresight/* backends), accounts (magic-link auth +
 * Stripe checkout), the two internal review pages, and the owner-only
 * dossier desk (/trends/dossiers — additionally gated by DOSSIERS_ENABLED,
 * see lib/dossier-access.ts).
 *
 * Keep in sync with the route tree under frontend/src/app — this list is a
 * manual mirror, not derived from the filesystem.
 */
const BLOCKED_PREFIXES = [
  "/account",
  "/trends/foresight",
  "/trends/review",
  "/trends/quality-preview",
  "/trends/dossiers",
  "/trends/pricing",
  "/api/auth",
  "/api/stripe",
  "/api/foresight",
] as const;

/**
 * Whether `pathname` falls under a blocked prefix. Matches the exact prefix
 * or the prefix followed by a `/` — a plain `startsWith` would also block an
 * unrelated sibling like `/trends/pricingx` or `/accounting`.
 */
export function isBlockedInPublicMode(pathname: string): boolean {
  return BLOCKED_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`)
  );
}
