import Link from "next/link";
import { canAccess, viewerTier, PAYWALL_ENABLED } from "@/lib/entitlement";
import { tierLabel } from "@/lib/tiers";
import { AUTH_ENABLED, getSession } from "@/lib/auth";
import type { Tier } from "@/lib/auth";

/**
 * Server-side feature gate (Epic W2.2). Renders `children` when the viewer's
 * tier allows `need`; otherwise renders an upgrade card (or `teaser` if given —
 * the free-tier preview shown in place of the gated feature). Never a hard wall
 * with no context: the card names the plan, states the concrete benefit and
 * links to pricing. Editorial styling (DS-04 — the old card ran on a second,
 * generic design system with a green pill).
 */
export default async function TierGate({
  need,
  children,
  teaser,
  feature = "This view",
  benefit = "Upgrade to see the full picture — momentum, lead-time and evidence across the whole signal space.",
}: {
  need: Tier;
  children: React.ReactNode;
  teaser?: React.ReactNode;
  feature?: string;
  benefit?: string;
}) {
  if (await canAccess(need)) return <>{children}</>;

  const session = AUTH_ENABLED ? await getSession() : null;
  const have = PAYWALL_ENABLED ? await viewerTier() : null;

  return (
    <div>
      {teaser}
      <div className="mt-4 border border-accent/30 bg-accent/5 px-6 py-8 text-center">
        <span className="inline-block font-mono text-[10px] uppercase tracking-[0.16em] text-accent border border-accent/40 px-2.5 py-1">
          {tierLabel(need)}
        </span>
        <p className="font-display text-[22px] leading-[1.2] text-paper mt-4">
          {feature} is part of {tierLabel(need)}
        </p>
        <p className="mx-auto mt-2 max-w-xl text-[14px] leading-[1.6] text-muted">
          {benefit}
        </p>
        {session && have && (
          <p className="mt-2 font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
            You&apos;re on {tierLabel(have)}
          </p>
        )}
        <Link
          href="/trends/pricing"
          className="mt-5 inline-block bg-accent text-ink px-5 py-2.5 font-mono text-[11px] uppercase tracking-[0.16em] font-semibold hover:bg-accent-deep transition-colors"
        >
          See plans →
        </Link>
      </div>
    </div>
  );
}
