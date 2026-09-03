import Link from "next/link";
import { linkPrefetch } from "@/lib/renderMode";
import type { Metadata } from "next";
import { PUBLIC_ARCHIVE_DAYS } from "@/lib/archiveWindow";
import { sitePath } from "@/lib/sitePaths";

export const metadata: Metadata = {
  title: "Signal expired — Catandary Trends",
  description: "This trend article has left the public window.",
  robots: { index: false, follow: true },
};

/**
 * Apache's `ErrorDocument 410` target on the static hosting
 * (frontend/public-export/.htaccess): every article URL that matches the
 * slug pattern but has no file any more — the ~590 articles a day that roll
 * out of the public window. A lead-CTA instead of a dead end (design 5.3).
 * Harmless on the workstation instance, where nothing links here.
 */
export default function ExpiredPage() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-24 text-center">
      <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted mb-4">
        —— 410 · Signal expired
      </div>
      <h1 className="font-display text-[40px] leading-[1.1] text-paper mb-4">
        This signal has left the <span className="italic text-accent">public window</span>.
      </h1>
      <p className="font-sans text-[15px] text-muted max-w-md mx-auto leading-[1.6] mb-10">
        The public site carries the most recent {PUBLIC_ARCHIVE_DAYS} days of
        trend articles. Older signals stay in the Catandary corpus — with their
        primary sources — and are part of every commissioned analysis.
      </p>
      <div className="flex flex-wrap justify-center gap-3">
        <Link
          prefetch={linkPrefetch()}
          href={sitePath("/enquiry")}
          className="font-mono text-[11px] uppercase tracking-[0.18em] bg-accent text-ink px-5 py-3 hover:bg-accent-deep transition-colors"
        >
          Ask about archive access →
        </Link>
        <Link
          prefetch={linkPrefetch()}
          href="/trends"
          className="font-mono text-[11px] uppercase tracking-[0.18em] border border-border text-muted px-5 py-3 hover:text-paper hover:border-accent/40 transition-colors"
        >
          Current signals
        </Link>
        <Link
          prefetch={linkPrefetch()}
          href="/trends/mega"
          className="font-mono text-[11px] uppercase tracking-[0.18em] border border-border text-muted px-5 py-3 hover:text-paper hover:border-accent/40 transition-colors"
        >
          Signal themes
        </Link>
      </div>
    </div>
  );
}
