import { NextResponse } from "next/server";
import { getSession, AUTH_ENABLED } from "@/lib/auth";
import { q1 } from "@/lib/pg";
import { stripeConfigured, priceIdFor, createCheckoutSession } from "@/lib/stripe";

export const dynamic = "force-dynamic";

/**
 * POST /api/stripe/checkout { tier } — create a Checkout Session for the signed-in
 * user and return its URL. Requires auth (needSignin:true otherwise) and a
 * configured Stripe (coming-soon otherwise).
 */
export async function POST(request: Request) {
  if (!stripeConfigured) {
    return NextResponse.json({ error: "billing not configured" }, { status: 503 });
  }
  if (!AUTH_ENABLED) {
    return NextResponse.json({ error: "auth disabled" }, { status: 404 });
  }
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ needSignin: true }, { status: 401 });
  }
  let tier: string;
  try {
    tier = (await request.json()).tier;
  } catch {
    return NextResponse.json({ error: "bad request" }, { status: 400 });
  }
  const priceId = priceIdFor(tier as never);
  if (!priceId) {
    return NextResponse.json({ error: "unknown tier / price not set" }, { status: 400 });
  }

  const base = process.env.PUBLIC_BASE_URL || new URL(request.url).origin;
  const row = await q1<{ stripe_customer_id: string | null }>(
    "SELECT stripe_customer_id FROM app_users WHERE id = $1",
    [session.id]
  );
  try {
    const url = await createCheckoutSession({
      priceId,
      email: session.email,
      userId: session.id,
      customerId: row?.stripe_customer_id ?? null,
      successUrl: `${base}/account?checkout=success`,
      cancelUrl: `${base}/trends/pricing?checkout=cancelled`,
    });
    return NextResponse.json({ url });
  } catch (e) {
    console.error("stripe checkout failed:", e);
    return NextResponse.json({ error: "checkout failed" }, { status: 502 });
  }
}
