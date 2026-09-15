/**
 * Public-mode gate (issue #93, Etappe 1).
 *
 * Business model change (owner 2026-08-26): the public site becomes a free
 * lead-gen showcase for Catandary Foresight. The Foresight tool suite stays
 * in daily use on the workstation instance but must not ship on the public
 * deployment. (Accounts and Stripe checkout used to be on this list; they
 * were removed from the code base altogether on 2026-09-03.)
 *
 * A single env flag, off by default. PUBLIC_MODE=1 blocks the routes below
 * (404); unset/0 changes nothing — the workstation instance on :3001 runs
 * unset and stays as-is until a deployment deliberately sets it.
 */
export function isPublicMode(): boolean {
  return process.env.PUBLIC_MODE === "1";
}

/**
 * Path prefixes hidden entirely when PUBLIC_MODE=1 — the "Fällt weg" list
 * from issue #93: the Foresight tool suite (all nine /trends/foresight/*
 * routes and their /api/foresight/* backends), the two internal review
 * pages, the owner dossier desk (/trends/dossiers — proprietary documents,
 * see lib/dossier-access.ts) and the newsletter release desk
 * (/trends/newsletter/review — it releases mail to the list; owner mandate
 * 2026-09-06). The release desk sits UNDER a public prefix, which is why
 * isBlockedInPublicMode matches on path segments: /trends/newsletter itself
 * stays public.
 *
 * Keep in sync with the route tree under frontend/src/app — this list is a
 * manual mirror, not derived from the filesystem (src/lib/staticExport.test.ts
 * checks it against frontend/static-export.exclude and the tree on disk).
 */
export const BLOCKED_PREFIXES = [
  "/trends/foresight",
  "/trends/review",
  "/trends/dossiers",
  "/trends/newsletter/review",
  "/trends/ops",
  "/api/foresight",
] as const;

/**
 * Whether `pathname` falls under a blocked prefix. Matches the exact prefix
 * or the prefix followed by a `/` — a plain `startsWith` would also block an
 * unrelated sibling like `/trends/foresights` or `/trends/reviewer`.
 */
export function isBlockedInPublicMode(pathname: string): boolean {
  return BLOCKED_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`)
  );
}
