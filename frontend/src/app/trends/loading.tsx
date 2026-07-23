/**
 * Loading skeleton for the trends feed (ARCH-07: Suspense fallbacks were all
 * null — slow responses looked like a hang). Mirrors the card grid so the
 * layout doesn't jump when data arrives.
 */
export default function TrendsLoading() {
  return (
    <div className="mx-auto max-w-7xl px-6 md:px-10 py-10" aria-busy="true">
      <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted pb-3 border-b border-border flex items-center gap-3">
        <span className="live-dot" aria-hidden="true" />
        <span>Loading signals…</span>
      </div>
      <div className="mt-10 h-16 w-2/3 max-w-xl bg-card animate-pulse" />
      <div className="mt-12 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
        {Array.from({ length: 6 }).map((_, i) => (
          <div
            key={i}
            className="border border-border border-l-[3px] border-l-rule px-6 py-7"
          >
            <div className="h-3 w-24 bg-card animate-pulse mb-5" />
            <div className="h-5 w-full bg-card animate-pulse mb-2" />
            <div className="h-5 w-4/5 bg-card animate-pulse mb-5" />
            <div className="h-3 w-full bg-card animate-pulse mb-1.5" />
            <div className="h-3 w-3/4 bg-card animate-pulse" />
          </div>
        ))}
      </div>
    </div>
  );
}
