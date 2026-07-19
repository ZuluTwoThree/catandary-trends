import { NextResponse } from "next/server";
import { q } from "@/lib/pg";
import { verifyWebhook, tierForPrice } from "@/lib/stripe";
import type { Tier } from "@/lib/auth";

export const dynamic = "force-dynamic";

// Stripe event objects are dynamic JSON; a precise type buys nothing here.
type StripeObj = Record<string, any>; // eslint-config-next does not flag `any`

/** Resolve our app user id from an event object (subscription events carry it via
 *  subscription_data metadata; checkout via client_reference_id/metadata). */
function resolveUserId(obj: StripeObj): number | null {
  const raw = obj?.metadata?.user_id ?? obj?.client_reference_id;
  const n = Number(raw);
  return Number.isInteger(n) && n > 0 ? n : null;
}

const TIERS: Tier[] = ["starter", "pro", "superpro"];

/** Determine the paid tier from an event object: price id (subscription item or
 *  metadata) → tierForPrice, else the metadata tier. null = indeterminate. */
function tierFromObject(obj: StripeObj): Tier | null {
  const priceId =
    obj?.items?.data?.[0]?.price?.id ??
    obj?.metadata?.price_id ??
    obj?.line_items?.data?.[0]?.price?.id ??
    null;
  const byPrice = priceId ? tierForPrice(priceId) : null;
  if (byPrice) return byPrice;
  const metaTier = obj?.metadata?.tier;
  return TIERS.includes(metaTier) ? (metaTier as Tier) : null;
}

/** Unix seconds when Stripe emitted the event; used to order tier transitions.
 *  Falls back to now() only if a malformed event omits it (never regresses tier). */
function eventTime(event: StripeObj): number {
  const t = Number(event?.created);
  return Number.isFinite(t) && t > 0 ? t : Math.floor(Date.now() / 1000);
}

/**
 * Persist Stripe ids (customer/subscription) for a user. Always safe to run: it
 * only COALESCE-fills nulls, so re-delivery and out-of-order arrival never clobber
 * an id we already stored. Keyed by user id when known, else by customer id.
 */
async function persistIds(
  key: { userId: number } | { customerId: string },
  customerId: string | null,
  subscriptionId: string | null
): Promise<void> {
  if ("userId" in key) {
    await q(
      "UPDATE app_users SET stripe_customer_id = COALESCE($1, stripe_customer_id), " +
        "stripe_subscription_id = COALESCE($2, stripe_subscription_id) WHERE id = $3",
      [customerId, subscriptionId, key.userId]
    );
  } else {
    await q(
      "UPDATE app_users SET stripe_subscription_id = COALESCE($1, stripe_subscription_id) " +
        "WHERE stripe_customer_id = $2",
      [subscriptionId, key.customerId]
    );
  }
}

/**
 * Write `tier` ONLY if this event is at least as new as the last tier-affecting
 * event we applied (sub_event_at). This is what makes ordering irrelevant: a
 * stale subscription.updated(active) redelivered AFTER a subscription.deleted
 * finds sub_event_at already ahead of it and is a no-op, so it cannot resurrect a
 * cancelled paid tier. Equal timestamps re-apply (idempotent, same value).
 */
async function applyTier(
  key: { userId: number } | { customerId: string },
  tier: Tier,
  createdAt: number
): Promise<void> {
  const guard = "(sub_event_at IS NULL OR sub_event_at <= to_timestamp($2))";
  if ("userId" in key) {
    await q(
      `UPDATE app_users SET tier = $1, sub_event_at = to_timestamp($2) ` +
        `WHERE id = $3 AND ${guard}`,
      [tier, createdAt, key.userId]
    );
  } else {
    await q(
      `UPDATE app_users SET tier = $1, sub_event_at = to_timestamp($2) ` +
        `WHERE stripe_customer_id = $3 AND ${guard}`,
      [tier, createdAt, key.customerId]
    );
  }
}

/**
 * POST /api/stripe/webhook — Stripe subscription lifecycle → app_users.tier.
 * Signature-verified against the raw body (multiple secrets during rotation).
 *
 * ORDER-INDEPENDENT + IDEMPOTENT on two levels:
 *  - id writes are COALESCE-only, so any event can arrive first/twice harmlessly;
 *  - tier writes are guarded by event.created vs the stored sub_event_at, so a
 *    delayed or reordered event never overwrites a newer contract state (e.g. an
 *    old `updated(active)` arriving after `deleted` cannot re-grant a paid tier).
 */
export async function POST(request: Request) {
  const raw = await request.text();
  const event = verifyWebhook(raw, request.headers.get("stripe-signature"));
  if (!event) {
    return NextResponse.json({ error: "invalid signature" }, { status: 400 });
  }

  try {
    const obj: StripeObj = event.data?.object ?? {};
    const userId = resolveUserId(obj);
    const createdAt = eventTime(event);

    switch (event.type) {
      case "checkout.session.completed": {
        if (!userId) break;
        await persistIds({ userId }, obj.customer ?? null, obj.subscription ?? null);
        const tier = tierFromObject(obj);
        if (tier) await applyTier({ userId }, tier, createdAt);
        break;
      }
      case "customer.subscription.updated": {
        const active = obj.status === "active" || obj.status === "trialing";
        // active → paid tier (skip the tier write when the price is unknown so we
        // never wrongly downgrade a valid-but-unmapped price); inactive → free.
        const tier: Tier | null = active ? tierFromObject(obj) : "free";
        // obj.id is the subscription id on subscription.* events.
        const key = userId ? { userId } : obj.customer ? { customerId: obj.customer } : null;
        if (!key) break;
        // store the subscription id on the primary (user-id) path too, so both
        // events converge on the same row.
        await persistIds(key, obj.customer ?? null, obj.id ?? null);
        if (tier) await applyTier(key, tier, createdAt);
        break;
      }
      case "customer.subscription.deleted": {
        const key = userId ? { userId } : obj.customer ? { customerId: obj.customer } : null;
        if (!key) break;
        // Downgrade guarded by event time, like every tier write: a later-arriving
        // older event cannot undo it. Clear the subscription id in the same write.
        if ("userId" in key) {
          await q(
            "UPDATE app_users SET tier = 'free', stripe_subscription_id = NULL, " +
              "sub_event_at = to_timestamp($1) WHERE id = $2 " +
              "AND (sub_event_at IS NULL OR sub_event_at <= to_timestamp($1))",
            [createdAt, key.userId]
          );
        } else {
          await q(
            "UPDATE app_users SET tier = 'free', stripe_subscription_id = NULL, " +
              "sub_event_at = to_timestamp($1) WHERE stripe_customer_id = $2 " +
              "AND (sub_event_at IS NULL OR sub_event_at <= to_timestamp($1))",
            [createdAt, key.customerId]
          );
        }
        break;
      }
      default:
        break;
    }
  } catch (e) {
    console.error("stripe webhook handler error:", e);
    return NextResponse.json({ error: "handler error" }, { status: 500 });
  }
  return NextResponse.json({ received: true });
}
