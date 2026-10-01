/**
 * Shared navigation model for Header, MobileNav and Footer. One source of
 * truth so desktop, mobile and footer never drift apart (issue register:
 * ONB-12 / ARCH-08 / COPY-22 — flat 11-item nav without hierarchy).
 */
export interface NavItem {
  href: string;
  label: string;
}

/** Top-level content sections. `/analysis` (#93 Etappe 2) is visible in both
 *  PUBLIC_MODE states — it isn't in the `isBlockedInPublicMode` prefix list,
 *  so gating the link here would just hide a working route. */
export const PRIMARY_NAV: NavItem[] = [
  { href: "/trends", label: "Trends" },
  { href: "/trends/mega", label: "Mega Trends" },
  { href: "/analysis", label: "Analyses" },
];

/** The Foresight tool suite — grouped under one "Foresight" entry.
 *  Header/MobileNav hide the whole group under PUBLIC_MODE, and the routes are
 *  blocked there anyway (lib/publicMode.ts). (The scouting desk
 *  /trends/dossiers was removed 2026-09-19.) */
export const FORESIGHT_NAV: NavItem[] = [
  { href: "/trends/foresight", label: "Cockpit" },
  { href: "/trends/foresight/clusters", label: "Clusters" },
  { href: "/trends/foresight/emerging", label: "Emerging" },
  { href: "/trends/foresight/discover", label: "Discover" },
  { href: "/trends/foresight/map", label: "Signal Space" },
  { href: "/trends/foresight/technology", label: "Technology" },
  { href: "/trends/foresight/lead-time", label: "Lead Time" },
  { href: "/trends/foresight/evolution", label: "Evolution" },
];

export function isForesightPath(pathname: string): boolean {
  return pathname.startsWith("/trends/foresight");
}
