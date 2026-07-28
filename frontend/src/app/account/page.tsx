import Link from "next/link";
import { redirect } from "next/navigation";
import { AUTH_ENABLED, getSession } from "@/lib/auth";
import { TIERS, tierLabel } from "@/lib/tiers";
import LogoutButton from "@/components/LogoutButton";
import CheckoutSuccessBanner from "@/components/CheckoutSuccessBanner";

export const dynamic = "force-dynamic";

export const metadata = { title: "Your account — Catandary Trends" };

export default async function AccountPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  if (!AUTH_ENABLED) redirect("/trends");
  const session = await getSession();
  if (!session) redirect("/account/signin");
  const sp = await searchParams;
  const checkoutSuccess = sp.checkout === "success";

  const tier = session.tier;
  const current = TIERS.find((t) => t.id === tier) ?? TIERS[0];

  return (
    <div className="mx-auto max-w-2xl px-6 py-12">
      <span className="eyebrow">Account</span>
      <h1 className="font-display text-[32px] leading-[1.1] text-paper mt-3">
        Your account
      </h1>
      <p className="mt-1 text-[14px] text-muted">{session.email}</p>

      {checkoutSuccess && <CheckoutSuccessBanner pending={tier === "free"} />}

      <div className="mt-8 border border-border bg-card p-6">
        <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-accent">
          Current plan
        </div>
        <div className="font-display text-[24px] text-paper mt-1.5">{tierLabel(tier)}</div>
        <p className="mt-1.5 text-[13px] leading-[1.55] text-muted">{current.blurb}</p>
        <div className="mt-4 flex flex-wrap items-center gap-4">
          <Link
            href="/trends/pricing"
            className="font-mono text-[11px] uppercase tracking-[0.14em] text-accent hover:underline"
          >
            {tier === "free" ? "See plans →" : "Compare plans →"}
          </Link>
          {tier !== "free" && (
            <span className="text-[12px] text-muted">
              To change or cancel your subscription, email{" "}
              <a href="mailto:trends@catandary.de" className="underline hover:text-paper">
                trends@catandary.de
              </a>{" "}
              — we handle it same-day.
            </span>
          )}
        </div>
      </div>

      <div className="mt-8 flex items-center gap-5">
        <LogoutButton />
        <Link
          href="/trends/foresight"
          className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted hover:text-paper transition-colors"
        >
          Go to Foresight →
        </Link>
      </div>
    </div>
  );
}
