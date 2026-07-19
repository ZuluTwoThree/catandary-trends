"use client";

import { useState } from "react";
import type { Tier } from "@/lib/auth";

/** Starts a Stripe Checkout session for a tier and redirects to it. */
export default function CheckoutButton({ tier, label }: { tier: Tier; label: string }) {
  const [busy, setBusy] = useState(false);
  async function go() {
    setBusy(true);
    try {
      const res = await fetch("/api/stripe/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tier }),
      });
      const data = await res.json();
      if (data.url) window.location.href = data.url;
      else {
        setBusy(false);
        if (data.needSignin) window.location.href = "/account/signin";
      }
    } catch {
      setBusy(false);
    }
  }
  return (
    <button
      onClick={go}
      disabled={busy}
      className="block w-full rounded-lg bg-[#16a34a] py-2 text-center text-sm font-semibold text-white hover:opacity-90 disabled:opacity-60"
    >
      {busy ? "…" : label}
    </button>
  );
}
