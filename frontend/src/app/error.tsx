"use client";

import Link from "next/link";

/**
 * Route-level error boundary (ARCH-07): friendly, branded, with a retry.
 * The technical error stays in the console/log — users get plain language
 * and a next step, not a stack trace.
 */
export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="mx-auto max-w-3xl px-6 py-24 text-center">
      <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-warn mb-4">
        —— Temporary glitch
      </div>
      <h1 className="font-display text-[36px] leading-[1.1] text-paper mb-4">
        Something went wrong on <span className="italic">our side</span>.
      </h1>
      <p className="font-sans text-[15px] text-muted max-w-md mx-auto leading-[1.6] mb-3">
        The page hit an unexpected error. Nothing you did — and no data was
        lost. Trying again usually fixes it.
      </p>
      {error.digest && (
        <p className="font-mono text-[10px] text-muted/80 mb-8">
          Reference: {error.digest}
        </p>
      )}
      <div className="flex flex-wrap justify-center gap-3 mt-6">
        <button
          onClick={reset}
          className="font-mono text-[11px] uppercase tracking-[0.18em] bg-accent text-ink px-5 py-3 hover:bg-accent-deep transition-colors"
        >
          Try again
        </button>
        <Link
          href="/trends"
          className="font-mono text-[11px] uppercase tracking-[0.18em] border border-border text-muted px-5 py-3 hover:text-paper hover:border-accent/40 transition-colors"
        >
          Back to trends
        </Link>
      </div>
    </div>
  );
}
