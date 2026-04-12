"use client";

import { useState } from "react";

export default function TrendScore({ score }: { score: number | null }) {
  const [showTooltip, setShowTooltip] = useState(false);

  if (score === null || score === undefined) return null;

  const crs = Math.round(score * 100);
  const hue = crs >= 80 ? 142 : crs >= 65 ? 47 : 25;

  return (
    <div
      className="relative flex items-center gap-1.5 cursor-help"
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
    >
      <div className="h-1.5 w-12 rounded-full bg-border overflow-hidden">
        <div
          className="h-full rounded-full transition-all"
          style={{
            width: `${crs}%`,
            backgroundColor: `hsl(${hue}, 70%, 50%)`,
          }}
        />
      </div>
      <span
        className="text-xs font-medium"
        style={{ color: `hsl(${hue}, 70%, 50%)` }}
      >
        CRS {crs}
      </span>

      {showTooltip && (
        <div className="absolute bottom-full left-0 mb-2 w-64 p-3 rounded-lg bg-card border border-border shadow-lg text-xs z-50">
          <p className="font-semibold text-foreground mb-1">
            Catandary Relevance Score
          </p>
          <p className="text-muted leading-relaxed">
            The CRS quantifies the strategic relevance of a trend signal. Our
            proprietary algorithms evaluate cross-industry impact, societal
            breadth, and signal maturity — the higher the score, the more likely
            this trend will reshape your industry.
          </p>
        </div>
      )}
    </div>
  );
}
