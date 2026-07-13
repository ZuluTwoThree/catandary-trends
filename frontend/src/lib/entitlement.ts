import { getSession, type Tier } from "./auth";
import { tierAllows } from "./tiers";

/**
 * Entitlement layer (Epic W2.2, issue #17). Gating is itself behind
 * PAYWALL_ENABLED: while it's off (prod today) every viewer is treated as fully
 * entitled, so the deployed site is unchanged until we flip the paywall on.
 *
 * Owner UX rule: gate at the value drill-down, not at the door — pages stay
 * browsable; only the deep feature shows an upgrade prompt.
 */
export const PAYWALL_ENABLED = process.env.PAYWALL_ENABLED === "1";

/** The current viewer's tier: their account tier, or 'free' if not signed in. */
export async function viewerTier(): Promise<Tier> {
  const session = await getSession();
  return session?.tier ?? "free";
}

/**
 * Whether the current viewer may access a feature requiring `need`. Returns
 * true unconditionally when the paywall is disabled.
 */
export async function canAccess(need: Tier): Promise<boolean> {
  if (!PAYWALL_ENABLED) return true;
  return tierAllows(await viewerTier(), need);
}
