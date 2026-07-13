import type { Tier } from "./auth";

/**
 * Subscription tiers (Epic W2.2, issue #17). Feature matrix per the owner's
 * 2026-07-05 note: Free = curated content (lead magnet), Starter = watch
 * (cluster explorer + alerts), Pro = the foresight differentiators (lead-time,
 * TIR, radar, export), Super Pro+ = ask the engine (on-demand, API).
 *
 * Prices are placeholders until the owner sets the $100–500 points; the UI
 * reads `priceHint` and the Stripe layer reads STRIPE_PRICE_<TIER> env ids.
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
    priceHint: "€—/mo",
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
    priceHint: "€—/mo",
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
    priceHint: "€—/mo",
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

const RANK: Record<Tier, number> = { free: 0, starter: 1, pro: 2, superpro: 3 };

export function tierLabel(tier: Tier): string {
  return TIERS.find((t) => t.id === tier)?.label ?? "Free";
}

/** Does `have` satisfy the `need` tier (or higher)? */
export function tierAllows(have: Tier, need: Tier): boolean {
  return RANK[have] >= RANK[need];
}
