import Link from "next/link";
import { TIERS, HYPERCARE } from "@/lib/tiers";
import { viewerTier, PAYWALL_ENABLED } from "@/lib/entitlement";
import { AUTH_ENABLED } from "@/lib/auth";
import CheckoutButton from "@/components/CheckoutButton";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Plans — Catandary Trends",
  description:
    "From the free curated feed to on-demand foresight. Evidence-based trend intelligence with clickable primary sources.",
};

/**
 * Pricing page. Shows the four tiers with the owner's feature matrix. Checkout
 * buttons appear only when Stripe is configured (PAYWALL_ENABLED + keys);
 * otherwise a "coming soon" note so the page is honest during the alpha.
 */
export default async function PricingPage() {
  const current = AUTH_ENABLED ? await viewerTier() : null;
  const stripeReady = PAYWALL_ENABLED && Boolean(process.env.STRIPE_SECRET_KEY);
  // Sales-led offering: no self-serve checkout, just a contact route. Address is
  // overridable via env; defaults to the existing catandary.de inbox.
  const contactEmail = process.env.CONTACT_EMAIL || "trends@catandary.de";
  const hypercareMailto = `mailto:${contactEmail}?subject=${encodeURIComponent(
    "Hypercare Trend & Foresight enquiry"
  )}`;

  return (
    <div className="mx-auto max-w-6xl px-4 py-10">
      <div className="mb-2 text-center">
        <h1 className="text-3xl font-bold tracking-tight">Plans</h1>
        <p className="mx-auto mt-2 max-w-2xl text-sm opacity-70">
          Evidence-based foresight with clickable primary sources — the free feed
          is the lead magnet, the paid tiers are where the lead-time edge lives.
          {!stripeReady && " Paid tiers open soon; the alpha runs in preview."}
        </p>
        <Link href="/trends/methodology" className="mt-2 inline-block text-sm underline opacity-80">
          How we measure →
        </Link>
      </div>

      <div className="mt-8 grid gap-5 md:grid-cols-2 lg:grid-cols-4">
        {TIERS.map((t) => {
          const isCurrent = current === t.id;
          return (
            <div
              key={t.id}
              className={`flex flex-col rounded-2xl border p-5 ${
                t.id === "pro" ? "border-current/40" : "border-current/12"
              }`}
            >
              <div className="text-xs font-semibold uppercase tracking-wide opacity-60">
                {t.label}
              </div>
              <div className="mt-1 text-2xl font-bold">{t.priceHint}</div>
              <p className="mt-2 text-sm opacity-75">{t.blurb}</p>
              <ul className="mt-4 flex-1 space-y-1.5 text-sm">
                {t.features.map((f) => (
                  <li key={f} className="flex gap-2">
                    <span className="opacity-50">·</span>
                    <span>{f}</span>
                  </li>
                ))}
              </ul>
              <div className="mt-5">
                {isCurrent ? (
                  <div className="rounded-lg border border-current/20 py-2 text-center text-sm opacity-70">
                    Your current plan
                  </div>
                ) : t.id === "free" ? (
                  <Link
                    href={AUTH_ENABLED ? "/account/signin" : "/trends"}
                    className="block rounded-lg border border-current/20 py-2 text-center text-sm font-semibold hover:bg-current/5"
                  >
                    {AUTH_ENABLED ? "Sign up free" : "Browse free"}
                  </Link>
                ) : stripeReady ? (
                  <CheckoutButton tier={t.id} label={`Choose ${t.label}`} />
                ) : (
                  <div className="rounded-lg border border-dashed border-current/20 py-2 text-center text-sm opacity-60">
                    Coming soon
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Hypercare — sales-led, day-rate. Deliberately outside the subscription
          grid: a bespoke engagement with a contact CTA, never a Stripe checkout. */}
      <div className="mt-6 flex flex-col gap-4 rounded-2xl border border-current/25 bg-current/[0.03] p-6 md:flex-row md:items-center md:justify-between">
        <div className="md:max-w-3xl">
          <div className="flex items-baseline gap-3">
            <span className="text-xs font-semibold uppercase tracking-wide opacity-60">
              {HYPERCARE.label}
            </span>
            <span className="text-2xl font-bold">{HYPERCARE.priceHint}</span>
          </div>
          <p className="mt-2 text-sm opacity-75">{HYPERCARE.blurb}</p>
          <ul className="mt-3 grid gap-x-6 gap-y-1.5 text-sm sm:grid-cols-2">
            {HYPERCARE.features.map((f) => (
              <li key={f} className="flex gap-2">
                <span className="opacity-50">·</span>
                <span>{f}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="shrink-0">
          <a
            href={hypercareMailto}
            className="block rounded-lg border border-current/30 px-5 py-2 text-center text-sm font-semibold hover:bg-current/5"
          >
            Talk to us
          </a>
        </div>
      </div>
    </div>
  );
}
