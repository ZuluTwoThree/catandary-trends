import Link from "next/link";

/**
 * The recurring in-product upsell. Links stay inside the product (ARCH-13 —
 * it used to route to the external company site, dropping the visitor out of
 * the funnel) and promise what the paid tiers actually show (COPY-19).
 */
export default function ForesightCta({ compact }: { compact?: boolean }) {
  if (compact) {
    return (
      <div className="mt-16 border border-accent/30 bg-accent/5 p-6">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-3">
          —— Catandary Foresight
        </div>
        <p className="font-sans text-text text-sm leading-relaxed mb-5 max-w-xl">
          See momentum, lead time and evidence for any topic — from 25-year
          mega-shifts down to the clusters rising this quarter.
        </p>
        <Link
          href="/trends/pricing"
          className="inline-flex items-center gap-2 bg-accent text-ink px-4 py-2 font-mono text-[10px] uppercase tracking-[0.18em] hover:bg-accent-deep transition-colors"
        >
          See plans →
        </Link>
      </div>
    );
  }

  return (
    <div className="mt-20 border border-accent/30 bg-accent/5 p-8">
      <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-4">
        —— Looking Deeper
      </div>
      <h2 className="font-display text-[30px] leading-tight text-paper mb-3">
        The <span className="italic">foresight</span> behind the feed
      </h2>
      <p className="font-sans text-text text-base leading-relaxed mb-6 max-w-xl">
        Catandary Foresight turns these signals into answers: which clusters are
        gaining ground, how early each technology still is, and the evidence
        behind every number — ready to hand to your team.
      </p>
      <div className="flex flex-wrap gap-3">
        <Link
          href="/trends/foresight"
          className="inline-flex items-center gap-2 bg-accent text-ink px-5 py-3 font-mono text-[10px] uppercase tracking-[0.18em] hover:bg-accent-deep transition-colors"
        >
          Open Foresight →
        </Link>
        <Link
          href="/trends/pricing"
          className="inline-flex items-center gap-2 border border-border-strong text-paper px-5 py-3 font-mono text-[10px] uppercase tracking-[0.18em] hover:border-accent transition-colors"
        >
          See plans
        </Link>
      </div>
    </div>
  );
}
