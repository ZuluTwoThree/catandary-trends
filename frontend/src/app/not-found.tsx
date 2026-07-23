import Link from "next/link";

/**
 * Branded 404 (ONB-07 / ARCH-16): the previous default was a blank body —
 * a dead end with no way back. Offers the three most useful re-entries.
 */
export default function NotFound() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-24 text-center">
      <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted mb-4">
        —— 404 · Page not found
      </div>
      <h1 className="font-display text-[40px] leading-[1.1] text-paper mb-4">
        This signal doesn&apos;t <span className="italic text-accent">exist</span>.
      </h1>
      <p className="font-sans text-[15px] text-muted max-w-md mx-auto leading-[1.6] mb-10">
        The page you followed may have been renamed or removed. The trend
        stream is still live — pick a way back in.
      </p>
      <div className="flex flex-wrap justify-center gap-3">
        <Link
          href="/trends"
          className="font-mono text-[11px] uppercase tracking-[0.18em] bg-accent text-ink px-5 py-3 hover:bg-accent-deep transition-colors"
        >
          Browse all trends →
        </Link>
        <Link
          href="/trends/mega"
          className="font-mono text-[11px] uppercase tracking-[0.18em] border border-border text-muted px-5 py-3 hover:text-paper hover:border-accent/40 transition-colors"
        >
          Mega trends
        </Link>
        <Link
          href="/"
          className="font-mono text-[11px] uppercase tracking-[0.18em] border border-border text-muted px-5 py-3 hover:text-paper hover:border-accent/40 transition-colors"
        >
          Start page
        </Link>
      </div>
    </div>
  );
}
