"use client";

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";

/**
 * Confirmation banner after Stripe checkout (ARCH-04): the webhook usually
 * lands within seconds, so while the account still shows the old tier we
 * re-fetch the server component every few seconds until it flips (bounded —
 * no infinite polling).
 */
export default function CheckoutSuccessBanner({ pending }: { pending: boolean }) {
  const router = useRouter();
  const attempts = useRef(0);

  useEffect(() => {
    if (!pending) return;
    const id = setInterval(() => {
      attempts.current += 1;
      if (attempts.current > 10) {
        clearInterval(id);
        return;
      }
      router.refresh();
    }, 3000);
    return () => clearInterval(id);
  }, [pending, router]);

  return (
    <div
      role="status"
      className="mb-6 border border-accent/40 bg-accent/5 px-5 py-4"
    >
      <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-accent mb-1.5">
        Payment received
      </p>
      <p className="text-[14px] leading-[1.6] text-foreground">
        {pending
          ? "Thanks — your plan is being activated. This usually takes under a minute; the page updates automatically."
          : "Your plan is active. Enjoy the engine."}
      </p>
    </div>
  );
}
