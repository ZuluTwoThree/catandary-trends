import Link from "next/link";
import type { Metadata } from "next";
import { linkPrefetch } from "@/lib/renderMode";

export const metadata: Metadata = {
  title: "Unsubscribed — Catandary Trends",
  description: "This address no longer receives the Catandary Trends briefing.",
  robots: { index: false, follow: false },
};

/**
 * /trends/newsletter/unsubscribed — the static confirmation page the PHP
 * unsubscribe backend redirects to after a confirmed opt-out
 * (docs/launch/newsletter-doi-php/unsubscribe.php, form path; the RFC 8058
 * one-click path answers plain text and never lands here). Pure static
 * content, noindex. Harmless on the workstation, where nothing links to it
 * (its own unsubscribe flow lives under /trends/newsletter/unsubscribe).
 */
export default function UnsubscribedPage() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-24 text-center">
      <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted mb-4">
        —— Newsletter
      </div>
      <h1 className="font-display text-[40px] leading-[1.1] text-paper mb-4">
        You&apos;re <span className="italic text-accent">unsubscribed</span>.
      </h1>
      <p className="font-sans text-[15px] text-muted max-w-md mx-auto leading-[1.6] mb-10">
        This address will no longer receive the weekly Catandary Trends briefing.
        Changed your mind? You can sign up again any time — a new confirmation
        link follows (double opt-in).
      </p>
      <div className="flex flex-wrap justify-center gap-3">
        <Link
          prefetch={linkPrefetch()}
          href="/trends/newsletter"
          className="font-mono text-[11px] uppercase tracking-[0.18em] bg-accent text-ink px-5 py-3 hover:bg-accent-deep transition-colors"
        >
          Back to the briefing →
        </Link>
        <Link
          prefetch={linkPrefetch()}
          href="/trends"
          className="font-mono text-[11px] uppercase tracking-[0.18em] border border-border text-muted px-5 py-3 hover:text-paper hover:border-accent/40 transition-colors"
        >
          Current signals
        </Link>
      </div>
    </div>
  );
}
