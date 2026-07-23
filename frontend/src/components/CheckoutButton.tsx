"use client";

import { useState } from "react";
import type { Tier } from "@/lib/auth";

/**
 * Starts a Stripe Checkout session for a tier and redirects to it.
 * Failures are surfaced (ARCH-09 — errors used to be swallowed silently),
 * and the sign-in detour keeps the purchase context via ?next= so the user
 * lands back on plans after the magic link (COPY-13).
 */
export default function CheckoutButton({
  tier,
  label,
  featured = false,
}: {
  tier: Tier;
  label: string;
  featured?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function go() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/stripe/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tier }),
      });
      const data = await res.json();
      if (data.url) {
        window.location.href = data.url;
        return;
      }
      setBusy(false);
      if (data.needSignin) {
        window.location.href = `/account/signin?next=${encodeURIComponent(
          "/trends/pricing"
        )}&reason=checkout`;
      } else {
        setError("Checkout didn't start — please try again in a moment.");
      }
    } catch {
      setBusy(false);
      setError("Checkout didn't start — please check your connection and try again.");
    }
  }

  return (
    <div>
      <button
        onClick={go}
        disabled={busy}
        className={`block w-full py-2.5 text-center font-mono text-[11px] uppercase tracking-[0.14em] transition-colors disabled:opacity-60 disabled:cursor-wait ${
          featured
            ? "bg-accent text-ink hover:bg-accent-deep"
            : "border border-border-strong text-paper hover:border-accent"
        }`}
      >
        {busy ? "Opening checkout…" : label}
      </button>
      {error && (
        <p role="alert" className="mt-2 text-[12px] leading-[1.4] text-warn">
          {error}
        </p>
      )}
    </div>
  );
}
