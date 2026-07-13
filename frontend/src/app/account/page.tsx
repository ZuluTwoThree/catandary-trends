import Link from "next/link";
import { redirect } from "next/navigation";
import { AUTH_ENABLED, getSession } from "@/lib/auth";
import { TIERS, tierLabel } from "@/lib/tiers";
import LogoutButton from "@/components/LogoutButton";

export const dynamic = "force-dynamic";

export const metadata = { title: "Your account — Catandary Trends" };

export default async function AccountPage() {
  if (!AUTH_ENABLED) redirect("/trends");
  const session = await getSession();
  if (!session) redirect("/account/signin");

  const tier = session.tier;
  const current = TIERS.find((t) => t.id === tier) ?? TIERS[0];

  return (
    <div className="mx-auto max-w-2xl px-4 py-10">
      <h1 className="text-2xl font-bold">Your account</h1>
      <p className="mt-1 text-sm opacity-70">{session.email}</p>

      <div className="mt-6 rounded-xl border border-current/10 p-5">
        <div className="text-xs font-semibold uppercase tracking-wide opacity-60">
          Current plan
        </div>
        <div className="mt-1 text-lg font-bold">{tierLabel(tier)}</div>
        <p className="mt-1 text-sm opacity-70">{current.blurb}</p>
        {tier === "free" && (
          <Link href="/trends/pricing" className="mt-3 inline-block text-sm font-semibold underline">
            See plans →
          </Link>
        )}
      </div>

      <div className="mt-6 flex items-center gap-4">
        <LogoutButton />
        <Link href="/trends/foresight" className="text-sm underline opacity-80">
          Go to Foresight
        </Link>
      </div>
    </div>
  );
}
