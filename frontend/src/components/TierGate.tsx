import Link from "next/link";
import { canAccess } from "@/lib/entitlement";
import { tierLabel } from "@/lib/tiers";
import type { Tier } from "@/lib/auth";

/**
 * Server-side feature gate (Epic W2.2). Renders `children` when the viewer's
 * tier allows `need`; otherwise renders an upgrade card (or `teaser` if given —
 * the free-tier preview shown in place of the gated feature). Never a hard wall
 * with no context: the card names the plan and links to pricing.
 */
export default async function TierGate({
  need,
  children,
  teaser,
  feature = "This view",
}: {
  need: Tier;
  children: React.ReactNode;
  teaser?: React.ReactNode;
  feature?: string;
}) {
  if (await canAccess(need)) return <>{children}</>;
  return (
    <div>
      {teaser}
      <div className="tier-gate">
        <div className="tier-gate-badge">{tierLabel(need)}</div>
        <p className="tier-gate-title">{feature} is part of {tierLabel(need)}</p>
        <p className="tier-gate-line">
          Upgrade to see the full picture — momentum, lead-time and evidence
          across the whole signal space.
        </p>
        <Link href="/trends/pricing" className="tier-gate-cta">
          See plans →
        </Link>
      </div>
      <style>{`
        .tier-gate { margin-top: 1rem; border: 1px solid color-mix(in srgb, currentColor 16%, transparent); border-radius: 14px; padding: 1.5rem; text-align: center; background: color-mix(in srgb, currentColor 4%, transparent); }
        .tier-gate-badge { display: inline-block; font-size: 0.68rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; padding: 0.15rem 0.55rem; border-radius: 999px; background: #16a34a22; color: #16a34a; margin-bottom: 0.6rem; }
        .tier-gate-title { font-weight: 700; font-size: 1.05rem; }
        .tier-gate-line { font-size: 0.88rem; opacity: 0.72; margin: 0.4rem auto 0.9rem; max-width: 32rem; }
        .tier-gate-cta { font-weight: 600; text-decoration: none; border: 1px solid currentColor; border-radius: 10px; padding: 0.5rem 1rem; font-size: 0.9rem; }
        .tier-gate-cta:hover { background: currentColor; color: canvas; }
      `}</style>
    </div>
  );
}
