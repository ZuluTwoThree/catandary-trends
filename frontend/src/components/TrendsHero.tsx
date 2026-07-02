import { VERTICALS } from "@/lib/types";

interface TrendsHeroProps {
  /** Curated, published articles (the free reading layer). */
  totalSignals?: number;
  /** All analyzed signals across the pipeline (the real corpus — a trust signal). */
  analyzedTotal?: number;
  /** Published-signal counts per vertical id. */
  verticalCounts?: Record<string, number>;
}

function formatStamp(date: Date): string {
  const yyyy = date.getFullYear();
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  const dd = String(date.getDate()).padStart(2, "0");
  const hh = String(date.getHours()).padStart(2, "0");
  const mi = String(date.getMinutes()).padStart(2, "0");
  return `${yyyy}.${mm}.${dd} · ${hh}:${mi}`;
}

export default function TrendsHero({
  totalSignals,
  analyzedTotal,
  verticalCounts,
}: TrendsHeroProps = {}) {
  // Server-rendered stamp. Deterministic per render, not live-ticking — that's fine:
  // conveys "as-of" authority without introducing hydration churn.
  const stamp = formatStamp(new Date());
  const totalFmt =
    totalSignals !== undefined ? totalSignals.toLocaleString("en-US") : null;
  const analyzedFmt =
    analyzedTotal !== undefined ? analyzedTotal.toLocaleString("en-US") : null;

  return (
    <section className="relative pt-10 pb-12 mb-12 overflow-hidden">
      {/* ── Terminal status bar ──────────────────────────────────────── */}
      <div
        className="reveal flex items-center justify-between gap-4 font-mono text-[10px] uppercase tracking-[0.18em] text-muted pb-3 border-b border-border"
        style={{ animationDelay: "0ms" }}
      >
        <div className="flex items-center gap-3 min-w-0">
          <span className="live-dot" aria-hidden="true" />
          <span className="text-accent shrink-0">Live</span>
          <span className="text-border shrink-0">——</span>
          <span className="truncate">{stamp} CET</span>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <span className="hidden sm:inline text-muted/70">
            Catandary / Signal Intelligence
          </span>
          {analyzedFmt && (
            <>
              <span className="hidden sm:inline text-border">——</span>
              <span title="Signals analyzed across research, patents, funding and market sources">
                <span className="text-accent">{analyzedFmt}</span>
                <span className="text-muted/70"> analyzed</span>
              </span>
            </>
          )}
          {totalFmt && (
            <>
              <span className="text-border">·</span>
              <span title="Curated articles published in the free reading layer">
                <span className="text-paper">{totalFmt}</span>
                <span className="text-muted/70"> curated</span>
              </span>
            </>
          )}
        </div>
      </div>

      {/* ── Crosshair mark (top-right signature motif) ───────────────── */}
      <div
        className="absolute top-12 right-0 hidden md:block"
        aria-hidden="true"
      >
        <div className="crosshair" />
      </div>

      {/* ── Eyebrow row ──────────────────────────────────────────────── */}
      <div
        className="reveal mt-10 flex items-baseline gap-6"
        style={{ animationDelay: "80ms" }}
      >
        <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-accent">
          ——&nbsp;&nbsp;01
        </span>
        <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted">
          Cross-Industry Foresight
        </span>
      </div>

      {/* ── Massive display headline (asymmetric two-column grid) ────── */}
      <div className="mt-6 grid grid-cols-1 lg:grid-cols-12 gap-x-10 gap-y-6 items-end">
        <h1
          className="reveal col-span-1 lg:col-span-9 font-display font-medium text-paper
                     text-[44px] sm:text-[64px] md:text-[76px] lg:text-[84px]
                     leading-[0.95] tracking-[-0.035em]"
          style={{ animationDelay: "180ms" }}
        >
          Cross-Industry
          <br />
          <span className="italic font-normal">Trend Intelligence</span>
          <span className="text-accent">.</span>
        </h1>

        <div
          className="reveal col-span-1 lg:col-span-3 lg:pb-4"
          style={{ animationDelay: "280ms" }}
        >
          <div className="font-mono text-[9px] uppercase tracking-[0.22em] text-muted mb-3">
            Abstract
          </div>
          <p className="font-sans text-[15px] leading-[1.55] text-text max-w-[34ch]">
            See where industries are heading — before it&apos;s mainstream. We
            track research, patents, funding and market signals across eight
            verticals to surface trends early.
          </p>
        </div>
      </div>

      {/* ── Reveal rule ──────────────────────────────────────────────── */}
      <div
        className="reveal-rule mt-12 h-px bg-border origin-left"
        aria-hidden="true"
      />

      {/* ── Vertical breakdown strip ─────────────────────────────────── */}
      {verticalCounts && (
        <div
          className="reveal mt-6 flex items-start justify-between gap-6"
          style={{ animationDelay: "420ms" }}
        >
          <div className="flex flex-wrap gap-x-6 gap-y-3">
            {VERTICALS.map((v) => {
              const count = verticalCounts[v.id] ?? 0;
              if (count === 0) return null;
              return (
                <div
                  key={v.id}
                  className="inline-flex items-baseline gap-2 font-mono text-[10px] uppercase tracking-[0.14em]"
                >
                  <span
                    className="inline-block w-2 h-[3px] translate-y-[-2px]"
                    style={{ backgroundColor: v.color }}
                    aria-hidden="true"
                  />
                  <span style={{ color: v.color }}>{v.code}</span>
                  <span className="text-paper tabular-nums">
                    {count.toLocaleString("en-US")}
                  </span>
                </div>
              );
            })}
          </div>
          <div className="hidden md:block font-mono text-[9px] uppercase tracking-[0.22em] text-muted shrink-0 pt-0.5">
            02 →
          </div>
        </div>
      )}
    </section>
  );
}
