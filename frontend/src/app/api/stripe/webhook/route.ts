import { NextResponse } from "next/server";
import { q, q1 } from "@/lib/pg";
import { verifyWebhook, tierForPrice } from "@/lib/stripe";

export const dynamic = "force-dynamic";

/**
 * POST /api/stripe/webhook — Stripe subscription lifecycle → app_users.tier.
 * Signature-verified against the raw body. Idempotent: every handler is an
 * UPDATE keyed by user/customer, safe to receive twice.
 *
 * Handled:
 *   checkout.session.completed         → attach customer + subscription, set tier
 *   customer.subscription.updated      → set tier from the active price
 *   customer.subscription.deleted      → downgrade to free
 */
export async function POST(request: Request) {
  const raw = await request.text();
  const event = verifyWebhook(raw, request.headers.get("stripe-signature"));
  if (!event) {
    return NextResponse.json({ error: "invalid signature" }, { status: 400 });
  }

  try {
    const obj = event.data?.object ?? {};
    switch (event.type) {
      case "checkout.session.completed": {
        const userId = Number(obj.client_reference_id || obj.metadata?.user_id);
        if (userId) {
          await q(
            "UPDATE app_users SET stripe_customer_id = $1, stripe_subscription_id = $2 " +
              "WHERE id = $3",
            [obj.customer ?? null, obj.subscription ?? null, userId]
          );
          // The subscription.updated event carries the price → tier; if this
          // session embeds it, set the tier now too.
          const priceId =
            obj.line_items?.data?.[0]?.price?.id ??
            obj.metadata?.price_id ??
            null;
          const tier = priceId ? tierForPrice(priceId) : null;
          if (tier) await q("UPDATE app_users SET tier = $1 WHERE id = $2", [tier, userId]);
        }
        break;
      }
      case "customer.subscription.updated": {
        const priceId = obj.items?.data?.[0]?.price?.id ?? null;
        const active = obj.status === "active" || obj.status === "trialing";
        const tier = active && priceId ? tierForPrice(priceId) : "free";
        if (tier) {
          await q(
            "UPDATE app_users SET tier = $1, stripe_subscription_id = $2 " +
              "WHERE stripe_customer_id = $3",
            [tier, obj.id ?? null, obj.customer]
          );
        }
        break;
      }
      case "customer.subscription.deleted": {
        await q(
          "UPDATE app_users SET tier = 'free', stripe_subscription_id = NULL " +
            "WHERE stripe_customer_id = $1",
          [obj.customer]
        );
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
