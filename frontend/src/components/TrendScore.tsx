"use client";

import { useState } from "react";
import { useLocale } from "@/lib/locale-context";

export default function TrendScore({ score }: { score: number | null }) {
  const [showTooltip, setShowTooltip] = useState(false);
  const { t } = useLocale();

  if (score === null || score === undefined) return null;

  // Score is stored as 0.0–1.0, display as 0–100
  const crs = Math.round(score * 100);

  // Color: green (high) → yellow (medium) → orange (lower)
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
            {t("crsLabel")}
          </p>
          <p className="text-muted leading-relaxed">
            {t("crsTooltip")}
          </p>
        </div>
      )}
    </div>
  );
}
