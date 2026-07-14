import crypto from "crypto";
import type { Tier } from "./auth";

/**
 * Dependency-free Stripe helpers (Epic W2.3, issue #17). The official SDK is a
 * heavy dep; the two calls we need — create a Checkout Session and verify a
 * webhook signature — are a form-encoded POST and an HMAC check, so we do them
 * with fetch + Node crypto, matching the auth approach. Everything is env-gated:
 * with no STRIPE_SECRET_KEY the checkout route returns "coming soon".
 */

export const STRIPE_SECRET = process.env.STRIPE_SECRET_KEY || "";
export const STRIPE_WEBHOOK_SECRET = process.env.STRIPE_WEBHOOK_SECRET || "";
export const stripeConfigured = Boolean(STRIPE_SECRET);

const PRICE_ENV: Record<Exclude<Tier, "free">, string> = {
  starter: "STRIPE_PRICE_STARTER",
  pro: "STRIPE_PRICE_PRO",
  superpro: "STRIPE_PRICE_SUPERPRO",
};

export function priceIdFor(tier: Tier): string | null {
  if (tier === "free") return null;
  return process.env[PRICE_ENV[tier]] || null;
}

/** tier for a given Stripe price id (reverse lookup, for webhook handling). */
export function tierForPrice(priceId: string): Tier | null {
  for (const [tier, env] of Object.entries(PRICE_ENV)) {
    if (process.env[env] && process.env[env] === priceId) return tier as Tier;
  }
  return null;
}

async function stripePost(path: string, form: Record<string, string>): Promise<any> {
  const res = await fetch(`https://api.stripe.com/v1/${path}`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${STRIPE_SECRET}`,
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: new URLSearchParams(form).toString(),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data?.error?.message || `stripe ${path} ${res.status}`);
  return data;
}

/** Create a subscription Checkout Session, return its redirect URL. */
export async function createCheckoutSession(opts: {
  priceId: string;
  email: string;
  userId: number;
  successUrl: string;
  cancelUrl: string;
  customerId?: string | null;
}): Promise<string> {
  const form: Record<string, string> = {
    mode: "subscription",
    "line_items[0][price]": opts.priceId,
    "line_items[0][quantity]": "1",
    success_url: opts.successUrl,
    cancel_url: opts.cancelUrl,
    client_reference_id: String(opts.userId),
    "metadata[user_id]": String(opts.userId),
    // EU VAT — Stripe Tax; harmless if not enabled on the account
    "automatic_tax[enabled]": "true",
  };
  if (opts.customerId) form.customer = opts.customerId;
  else form.customer_email = opts.email;
  const session = await stripePost("checkout/sessions", form);
  return session.url as string;
}

/**
 * Verify a Stripe webhook signature (the `Stripe-Signature: t=…,v1=…` header)
 * against the raw body. Returns the parsed event or null on failure. Rejects
 * timestamps older than 5 minutes (replay protection).
 */
export function verifyWebhook(rawBody: string, sigHeader: string | null): any | null {
  if (!STRIPE_WEBHOOK_SECRET || !sigHeader) return null;
  const parts = Object.fromEntries(
    sigHeader.split(",").map((kv) => kv.split("=") as [string, string])
  );
  const t = parts["t"];
  const v1 = parts["v1"];
  if (!t || !v1) return null;
  if (Math.abs(Date.now() / 1000 - Number(t)) > 300) return null;
  const expected = crypto
    .createHmac("sha256", STRIPE_WEBHOOK_SECRET)
    .update(`${t}.${rawBody}`)
    .digest("hex");
  if (
    v1.length !== expected.length ||
    !crypto.timingSafeEqual(Buffer.from(v1), Buffer.from(expected))
  )
    return null;
  try {
    return JSON.parse(rawBody);
  } catch {
    return null;
  }
}
