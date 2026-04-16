"use client";

import { useState } from "react";

export default function TrendScore({ score }: { score: number | null }) {
  const [showTooltip, setShowTooltip] = useState(false);

  if (score === null || score === undefined) return null;

  const crs = Math.round(score * 100);
  // Chartreuse accent for high, warm orange for low
  const color = crs >= 80 ? "var(--color-accent)" : crs >= 65 ? "#d4ff3a" : "var(--color-warn)";

  return (
    <div
      className="relative flex items-center gap-2 cursor-help"
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
    >
      <div className="h-[3px] w-12 bg-border overflow-hidden">
        <div
          className="h-full transition-all"
          style={{
            width: `${crs}%`,
            backgroundColor: color,
          }}
        />
      </div>
      <span
        className="font-mono text-[10px] font-medium tracking-wider"
        style={{ color }}
      >
        CRS {crs}
      </span>

      {showTooltip && (
        <div className="absolute bottom-full right-0 mb-2 w-64 p-3 bg-card border border-border shadow-lg text-xs z-50">
          <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-accent mb-1">
            Catandary Relevance Score
          </p>
          <p className="text-muted leading-relaxed font-sans">
            CRS quantifies the strategic relevance of a trend signal. Our
            algorithms evaluate cross-industry impact, societal breadth, and
            signal maturity — the higher the score, the more likely this
            trend will reshape your industry.
          </p>
        </div>
      )}
    </div>
  );
}
