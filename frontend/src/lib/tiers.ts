import type { Tier } from "./auth";

/**
 * Subscription tiers (Epic W2.2, issue #17). Feature matrix per the owner's
 * 2026-07-05 note: Free = curated content (lead magnet), Starter = watch
 * (cluster explorer + alerts), Pro = the foresight differentiators (lead-time,
 * TIR, radar, export), Super Pro+ = ask the engine (on-demand, API).
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
    blurb: "Curated trend articles, browsing, search and the weekly newsletter.",
    features: [
      "Published trend articles",
      "Vertical & PESTEL browsing",
      "Search",
      "Weekly newsletter",
      "Corpus counter & mega-trend teasers",
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
      "Cluster explorer (momentum, corroboration, evidence links)",
      "Trend radar",
      "Saved searches & alerts",
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
      "Technology explorer: CPC lead-time axes",
      "TIR metrics (cycle time, immediate importance)",
      "Trend evolution & lineage",
      "CSV / dossier export",
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
      "On-demand analysis of your own scopes (lazy-embed)",
      "API access",
      "Raw evidence graph",
      "Custom reports",
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
