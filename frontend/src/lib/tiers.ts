import type { Tier } from "./auth";

/**
 * Subscription tiers (Epic W2.2, issue #17). Free = curated content (lead
 * magnet), Starter = watch (cluster explorer + alerts), Pro = the foresight
 * differentiators (lead-time, TIR, export), Super Pro+ = ask the engine
 * (on-demand, API).
 *
 * ⚠️ This matrix predates the Explorer services and is being re-derived in #88 —
 * the `TierGate need=` values in the routes and the `features` lists below do
 * not currently agree. Do not treat this comment as the source of truth until
 * #88 closes.
 *
 * The trend radar was REMOVED from the product on 2026-08-25 (owner decision):
 * the shipped version failed both content audits — #90 (field labels anchored to
 * nothing, 32-35 % survive expert review) and #91 (20 of 28 checked placements
 * wrong, regulatory dimension has no H2 state). It returns as a Super Pro+ /
 * individual-analysis feature once it is defensible, see #89. Nothing here may
 * promise a radar in the meantime.
 *
 * Prices finalized by the owner 2026-07-19: Free €0, Starter €99/mo, Pro €499/mo,
 * Super Pro+ €799/mo. The UI reads `priceHint`; the actual charge amounts live in
 * Stripe Price objects referenced by STRIPE_PRICE_<TIER> env ids (not hardcoded).
 *
 * A fourth offering — Hypercare (individual Trend & Foresight) — is deliberately
 * NOT a subscription tier: it is a sales-led, day-rate consulting engagement
 * handled off-Stripe (invoice). It lives in HYPERCARE below, is kept out of the
 * `Tier` union and the checkout/webhook path, and is surfaced on the pricing page
 * as a "talk to us" card rather than a self-serve checkout.
 */
export interface TierInfo {
  id: Tier;
  label: string;
  blurb: string;
  priceHint: string;
  features: string[];
  rank: number;
}

export const TIERS: TierInfo[] = [
  {
    id: "free",
    label: "Free",
    rank: 0,
    priceHint: "€0",
    blurb: "Curated trend articles from the last 28 days, browsing, search and the weekly newsletter.",
    features: [
      // Window per FREE_ARCHIVE_DAYS in lib/entitlement.ts (issue #70) — keep in sync.
      "Trend articles from the last 28 days — each with its primary source",
      "Browse by industry & PESTEL dimension",
      "Full-text search",
      "Weekly newsletter",
      "Mega-trend overviews",
    ],
  },
  {
    id: "starter",
    label: "Starter",
    rank: 1,
    priceHint: "€99/mo",
    blurb: "Watch what's moving: the cluster explorer with momentum and evidence.",
    features: [
      "Everything in Free",
      "The full trend-article archive",
      "See what's rising: trend clusters ranked by momentum",
      "Every cluster backed by clickable evidence",
    ],
  },
  {
    id: "pro",
    label: "Pro",
    rank: 2,
    priceHint: "€499/mo",
    blurb: "The foresight edge: lead-time, technology trajectories and export.",
    features: [
      "Everything in Starter",
      "Know how early you are: research-to-market lead times per technology",
      "See how fast a technology improves — peer-reviewed improvement rates (TIR)",
      "Trend evolution: how today's clusters emerged",
      "Hand your team a cited dossier — CSV & print export",
    ],
  },
  {
    id: "superpro",
    label: "Super Pro+",
    rank: 3,
    priceHint: "€799/mo",
    blurb: "Ask the engine your own questions: on-demand analysis and API.",
    features: [
      "Everything in Pro",
      "Analyze any technology or topic you bring — on demand",
      "Raw evidence graph behind every answer",
      "Custom reports",
      "API access — coming soon",
    ],
  },
];

/**
 * Hypercare — a sales-led, day-rate consulting engagement, NOT a subscription
 * tier. Intentionally separate from `Tier`/`TIERS` so it never enters the Stripe
 * checkout or the subscription webhook. Surfaced on the pricing page with a
 * contact CTA; billing is handled off-Stripe (invoice). Prices per the owner
 * 2026-07-19: €1,499/day, €999/day from the 2nd engagement.
 */
export interface SalesOffer {
  label: string;
  blurb: string;
  priceHint: string;
  features: string[];
}

export const HYPERCARE: SalesOffer = {
  label: "Hypercare",
  priceHint: "€1,499/day",
  blurb:
    "Individual Trend & Foresight hypercare — dedicated, hands-on analyst support tailored to your questions. A bespoke engagement, not a subscription.",
  features: [
    "Everything in Super Pro+",
    "Dedicated analyst engagement (day-rate)",
    "Bespoke scopes, briefings & deliverables",
    "€999/day from the 2nd engagement",
  ],
};

const RANK: Record<Tier, number> = { free: 0, starter: 1, pro: 2, superpro: 3 };

export function tierLabel(tier: Tier): string {
  return TIERS.find((t) => t.id === tier)?.label ?? "Free";
}

/** Does `have` satisfy the `need` tier (or higher)? */
export function tierAllows(have: Tier, need: Tier): boolean {
  return RANK[have] >= RANK[need];
}
