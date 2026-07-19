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

/**
 * POST /api/stripe/webhook — Stripe subscription lifecycle → app_users.tier.
 * Signature-verified against the raw body (multiple secrets during rotation).
 *
 * ORDER-INDEPENDENT + IDEMPOTENT: every event carries the user id in metadata, so a
 * subscription.* event that arrives BEFORE checkout.session.completed still resolves
 * the user and writes the customer id itself. All writes are UPDATEs keyed by the
 * user id (COALESCE so a re-delivery never clobbers already-stored ids), safe to
 * receive twice or out of order.
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

    switch (event.type) {
      case "checkout.session.completed": {
        if (!userId) break;
        const tier = tierFromObject(obj);
        await q(
          "UPDATE app_users SET " +
            "stripe_customer_id = COALESCE($1, stripe_customer_id), " +
            "stripe_subscription_id = COALESCE($2, stripe_subscription_id)" +
            (tier ? ", tier = $4" : "") +
            " WHERE id = $3",
          tier
            ? [obj.customer ?? null, obj.subscription ?? null, userId, tier]
            : [obj.customer ?? null, obj.subscription ?? null, userId]
        );
        break;
      }
      case "customer.subscription.updated": {
        const active = obj.status === "active" || obj.status === "trialing";
        // active → paid tier (skip the tier write when the price is unknown so we
        // never wrongly downgrade a valid-but-unmapped price); inactive → free.
        const tier: Tier | null = active ? tierFromObject(obj) : "free";
        const setTier = tier ? ", tier = $3" : "";
        if (userId) {
          // primary path: resolve by user id (works even before checkout.completed),
          // and store the customer id so the two events converge.
          await q(
            "UPDATE app_users SET stripe_customer_id = COALESCE($1, stripe_customer_id)" +
              setTier + " WHERE id = $2",
            tier ? [obj.customer ?? null, userId, tier] : [obj.customer ?? null, userId]
          );
        } else if (obj.customer) {
          // fallback: legacy subscriptions without metadata → key by customer id
          await q(
            "UPDATE app_users SET stripe_subscription_id = COALESCE($1, stripe_subscription_id)" +
              (tier ? ", tier = $3" : "") + " WHERE stripe_customer_id = $2",
            tier ? [obj.id ?? null, obj.customer, tier] : [obj.id ?? null, obj.customer]
          );
        }
        break;
      }
      case "customer.subscription.deleted": {
        if (userId) {
          await q(
            "UPDATE app_users SET tier = 'free', stripe_subscription_id = NULL WHERE id = $1",
            [userId]
          );
        } else if (obj.customer) {
          await q(
            "UPDATE app_users SET tier = 'free', stripe_subscription_id = NULL " +
              "WHERE stripe_customer_id = $1",
            [obj.customer]
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
