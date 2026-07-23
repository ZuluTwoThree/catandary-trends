import Link from "next/link";
import { TIERS, HYPERCARE } from "@/lib/tiers";
import { PAYWALL_ENABLED } from "@/lib/entitlement";
import { AUTH_ENABLED, getSession } from "@/lib/auth";
import CheckoutButton from "@/components/CheckoutButton";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Plans — Catandary Trends",
  description:
    "From the free curated feed to on-demand foresight. Evidence-based trend intelligence with clickable primary sources.",
};

/**
 * Pricing page, Editorial-Intelligence styling (DS-04: this page used to run
 * on a second, generic design system — precisely where people pay). Logic
 * fixes: "Your current plan" only for signed-in viewers (COPY-09), checkout
 * buttons only when Stripe is configured, cancelled-checkout notice, billing
 * transparency line (COPY-25).
 */
export default async function PricingPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  const cancelled = sp.checkout === "cancelled";
  const session = AUTH_ENABLED ? await getSession() : null;
  const current = session?.tier ?? null;
  const stripeReady = PAYWALL_ENABLED && Boolean(process.env.STRIPE_SECRET_KEY);
  const contactEmail = process.env.CONTACT_EMAIL || "trends@catandary.de";
  const hypercareMailto = `mailto:${contactEmail}?subject=${encodeURIComponent(
    "Hypercare Trend & Foresight enquiry"
  )}`;

  return (
    <div className="mx-auto max-w-6xl px-6 py-12">
      <div className="mb-10">
        <span className="eyebrow">Access</span>
        <h1 className="font-display text-[44px] md:text-[56px] leading-[1.02] tracking-[-0.02em] text-paper mt-4">
          Start free. Grow into <span className="italic text-accent">the engine</span>.
        </h1>
        <p className="mt-4 max-w-2xl text-[15px] leading-[1.6] text-muted">
          The curated feed and weekly briefing are free — the paid tiers add the
          lead-time edge: see what&apos;s rising months before the market, with
          evidence you can cite.
          {!stripeReady && " Paid tiers open soon; the alpha runs in preview."}
        </p>
        <Link
          href="/trends/methodology"
          className="mt-3 inline-block font-mono text-[11px] uppercase tracking-[0.14em] text-accent hover:underline"
        >
          How we measure →
        </Link>
      </div>

      {cancelled && (
        <div
          role="status"
          className="mb-8 border border-border bg-card px-5 py-4 text-[14px] text-foreground"
        >
          Checkout cancelled — nothing was charged. Your plan is unchanged; you
          can pick one whenever you&apos;re ready.
        </div>
      )}

      <div className="grid gap-px bg-border border border-border md:grid-cols-2 lg:grid-cols-4">
        {TIERS.map((t) => {
          const isCurrent = session != null && current === t.id;
          const featured = t.id === "pro";
          return (
            <div
              key={t.id}
              className={`flex flex-col p-6 ${
                featured ? "bg-card-hover shadow-[inset_0_2px_0_var(--color-accent)]" : "bg-card"
              }`}
            >
              <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-accent">
                {t.label}
              </div>
              <div className="font-display text-[32px] text-paper mt-2">
                {t.priceHint.replace("/mo", "")}
                {t.priceHint.includes("/mo") && (
                  <span className="font-mono text-[11px] text-muted tracking-[0.04em]"> /mo</span>
                )}
              </div>
              <p className="mt-2 text-[13px] leading-[1.55] text-muted min-h-[3.2em]">{t.blurb}</p>
              <ul className="mt-4 flex-1 space-y-2">
                {t.features.map((f) => (
                  <li key={f} className="relative pl-4 text-[13px] leading-[1.5] text-foreground">
                    <span className="absolute left-0 text-accent-deep" aria-hidden="true">
                      +
                    </span>
                    {f}
                  </li>
                ))}
              </ul>
              <div className="mt-6">
                {isCurrent ? (
                  <div className="border border-border py-2.5 text-center font-mono text-[11px] uppercase tracking-[0.14em] text-muted">
                    Your current plan
                  </div>
                ) : t.id === "free" ? (
                  <Link
                    href={AUTH_ENABLED && !session ? "/account/signin" : "/trends"}
                    className="block border border-border-strong py-2.5 text-center font-mono text-[11px] uppercase tracking-[0.14em] text-paper hover:border-accent transition-colors"
                  >
                    {AUTH_ENABLED && !session ? "Sign up free" : "Browse free"}
                  </Link>
                ) : stripeReady ? (
                  <CheckoutButton tier={t.id} label={`Choose ${t.label}`} featured={featured} />
                ) : (
                  <div className="border border-dashed border-border py-2.5 text-center font-mono text-[11px] uppercase tracking-[0.14em] text-muted">
                    Coming soon
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {stripeReady && (
        <p className="mt-3 font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
          Monthly billing via Stripe · cancel anytime · prices excl. VAT
        </p>
      )}

      {/* Hypercare — sales-led, day-rate. Deliberately outside the subscription
          grid: a bespoke engagement with a contact CTA, never a Stripe checkout. */}
      <div className="mt-8 border border-border bg-card p-6 flex flex-col gap-5 md:flex-row md:items-center md:justify-between">
        <div className="md:max-w-3xl">
          <div className="flex items-baseline gap-3">
            <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-accent">
              {HYPERCARE.label}
            </span>
            <span className="font-display text-[24px] text-paper">{HYPERCARE.priceHint}</span>
          </div>
          <p className="mt-2 text-[13px] leading-[1.55] text-muted">{HYPERCARE.blurb}</p>
          <ul className="mt-3 grid gap-x-6 gap-y-1.5 sm:grid-cols-2">
            {HYPERCARE.features.map((f) => (
              <li key={f} className="relative pl-4 text-[13px] leading-[1.5] text-foreground">
                <span className="absolute left-0 text-accent-deep" aria-hidden="true">
                  +
                </span>
                {f}
              </li>
            ))}
          </ul>
        </div>
        <div className="shrink-0">
          <a
            href={hypercareMailto}
            className="block border border-border-strong px-5 py-2.5 text-center font-mono text-[11px] uppercase tracking-[0.14em] text-paper hover:border-accent transition-colors"
          >
            Email us about Hypercare
          </a>
        </div>
      </div>
    </div>
  );
}
