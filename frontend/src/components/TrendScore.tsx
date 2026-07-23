"use client";

import { useId, useState } from "react";

/**
 * CRS badge with bar. Three real color steps (DS-07: the middle step was a
 * hardcoded duplicate of the top one, so the tiering never showed). The
 * explanation is reachable without a mouse (A11Y-12): the badge is focusable
 * (valid inside the card link — no nested interactive element), the tooltip
 * shows on hover AND focus, and the text is always in the accessibility tree
 * via aria-describedby.
 */
export default function TrendScore({ score }: { score: number | null }) {
  const [showTooltip, setShowTooltip] = useState(false);
  const tooltipId = useId();

  if (score === null || score === undefined) return null;

  const crs = Math.round(score * 100);
  const color =
    crs >= 80
      ? "var(--color-accent)"
      : crs >= 65
        ? "var(--color-accent-deep)"
        : "var(--color-warn)";

  const description =
    "Catandary Relevance Score, 0 to 100: cross-industry impact, societal breadth and signal maturity. Higher means more likely to reshape your industry. Full explanation under How we measure.";

  return (
    <span
      className="relative flex items-center gap-2"
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
    >
      <span className="h-[3px] w-12 bg-border overflow-hidden" aria-hidden="true">
        <span
          className="block h-full transition-all"
          style={{ width: `${crs}%`, backgroundColor: color }}
        />
      </span>
      <span
        tabIndex={0}
        aria-describedby={tooltipId}
        onFocus={() => setShowTooltip(true)}
        onBlur={() => setShowTooltip(false)}
        onKeyDown={(e) => e.key === "Escape" && setShowTooltip(false)}
        className="font-mono text-[10px] font-medium tracking-wider cursor-help"
        style={{ color }}
      >
        CRS {crs}
      </span>
      <span id={tooltipId} className="sr-only">
        {description}
      </span>

      {showTooltip && (
        <span
          role="tooltip"
          aria-hidden="true"
          className="absolute bottom-full right-0 mb-2 w-64 p-3 bg-card border border-border shadow-lg text-xs z-50 block text-left"
        >
          <span className="block font-mono text-[10px] uppercase tracking-[0.14em] text-accent mb-1">
            Catandary Relevance Score
          </span>
          <span className="block text-muted leading-relaxed font-sans normal-case tracking-normal">
            CRS rates a signal&apos;s strategic relevance from 0–100 —
            cross-industry impact, societal breadth and signal maturity. Higher
            means more likely to reshape your industry. Full explanation under
            &ldquo;How we measure&rdquo; in the footer.
          </span>
        </span>
      )}
    </span>
  );
}
