/**
 * Shared navigation model for Header, MobileNav and Footer. One source of
 * truth so desktop, mobile and footer never drift apart (issue register:
 * ONB-12 / ARCH-08 / COPY-22 — flat 11-item nav without hierarchy).
 */
export interface NavItem {
  href: string;
  label: string;
}

/** Top-level content sections. */
export const PRIMARY_NAV: NavItem[] = [
  { href: "/trends", label: "Trends" },
  { href: "/trends/mega", label: "Mega Trends" },
];

/** The Foresight tool suite — grouped under one "Foresight" entry. */
export const FORESIGHT_NAV: NavItem[] = [
  { href: "/trends/foresight", label: "Cockpit" },
  { href: "/trends/foresight/radar", label: "Radar" },
  { href: "/trends/foresight/clusters", label: "Clusters" },
  { href: "/trends/foresight/technology", label: "Technology" },
  { href: "/trends/foresight/lead-time", label: "Lead Time" },
  { href: "/trends/foresight/evolution", label: "Evolution" },
  { href: "/trends/foresight/dossier", label: "Dossier" },
];

export const PLANS_NAV: NavItem = { href: "/trends/pricing", label: "Plans" };

export function isForesightPath(pathname: string): boolean {
  return pathname.startsWith("/trends/foresight");
}
