import Link from "next/link";
import { isPublicMode } from "@/lib/publicMode";

/**
 * The recurring in-product pointer from the feed into the Foresight tools.
 * Links stay inside the product (ARCH-13 — it used to route to the external
 * company site, dropping the visitor out of the funnel).
 *
 * PUBLIC_MODE=1 (#93): the target (/trends/foresight) 404s under that flag
 * (proxy.ts) and this component is rendered on public, non-blocked pages
 * (/trends, /trends/mega, /trends/methodology, article pages via
 * TrendArticle) — so it renders nothing rather than a dead-end CTA. The
 * public lead-gen replacement is AnalysisCta / the enquiry page. On the
 * owner instance it is a plain link into the tools (no plans, no upsell —
 * no SaaS since #93).
 */
export default function ForesightCta({ compact }: { compact?: boolean }) {
  if (isPublicMode()) return null;

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
          href="/trends/foresight"
          className="inline-flex items-center gap-2 bg-accent text-ink px-4 py-2 font-mono text-[10px] uppercase tracking-[0.18em] hover:bg-accent-deep transition-colors"
        >
          Open Foresight →
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
      </div>
    </div>
  );
}
