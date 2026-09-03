/**
 * Root-level pages that the static export publishes under /trends/… instead.
 *
 * The publisher (scripts/publish_static_site.py) manages only trends/** and
 * _next/** (plus feed page 1); the webroot — index.html, robots.txt, the
 * newsletter PHP — is the owner's. /imprint, /privacy and /enquiry are root
 * routes, so on the live site they would be 404s. The export therefore has a
 * second route for each under app/trends/{imprint,privacy,enquiry} (same
 * content components, export-only), and every link goes through `sitePath`
 * so the workstation keeps the root URLs while the export links the /trends
 * copies. `isStaticExport()` reads the NEXT_PUBLIC_ mirror, so client
 * components (newsletter signup) can use this too.
 */
import { isStaticExport } from "./renderMode";

export const RELOCATED_ROOT_PAGES = ["/imprint", "/privacy", "/enquiry"] as const;
export type RelocatedRootPage = (typeof RELOCATED_ROOT_PAGES)[number];

export function sitePath(page: RelocatedRootPage): string {
  return isStaticExport() ? `/trends${page}` : page;
}
