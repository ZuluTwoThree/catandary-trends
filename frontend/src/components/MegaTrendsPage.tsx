"use client";

import Link from "next/link";
import type { VerticalInfo, MegaTrendInfo } from "@/lib/types";
import { getMegaTrendInfo } from "@/lib/types";

interface MegaTrendItem {
  mega_trend: string;
  count: number;
  verticals: string[];
  verticalInfos: VerticalInfo[];
  slug: string;
  /** Measured (90d share vs prior 90d, lib/momentum.ts); null = no claim. */
  momentum?: "rising" | "stable" | "declining" | "emerging" | null;
  cluster_strength?: "strong" | "moderate" | "fragmented";
  horizon?: string;
  description?: string;
  first_seen?: string | null;
  signals_30d?: number;
}

function formatFirstSeen(iso: string | null | undefined): string | null {
  if (!iso) return null;
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("en-US", { month: "short", year: "numeric" });
  } catch {
    return null;
  }
}

// Measured, not asserted: the key's share of published signals in the last
// 90 days vs the 90 days before (lib/momentum.ts). Keys with too few signals
// for a directional claim carry no badge at all — no claim beats a wrong one.
const MOMENTUM_CONFIG = {
  rising: {
    label: "Rising", color: "#22c55e", glyph: "↗",
    tooltip: "Share of published signals in the last 90 days is at least 15% above the 90 days before.",
  },
  stable: {
    label: "Stable", color: "#a3a3a3", glyph: "→",
    tooltip: "Share of published signals in the last 90 days is within ±15% of the 90 days before.",
  },
  declining: {
    label: "Declining", color: "#ef4444", glyph: "↘",
    tooltip: "Share of published signals in the last 90 days is at least 15% below the 90 days before.",
  },
  emerging: {
    label: "Emerging", color: "#a855f7", glyph: "◆",
    tooltip: "No published signals in the prior 90-day window — this theme only just started appearing.",
  },
} as const;

export default function MegaTrendsPage({
  megaTrends,
}: {
  megaTrends: MegaTrendItem[];
}) {
  return (
    <>
      <div className="mb-12">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-4">
          —— Structural Shifts
        </div>
        <h1 className="font-display text-4xl md:text-[52px] leading-[1.05] tracking-tight text-paper mb-4">
          Mega <span className="italic">Trends</span>
        </h1>
        <p className="font-sans text-text text-lg leading-relaxed max-w-2xl">
          Long-term structural shifts reshaping industries over the next
          10–25 years.
        </p>
      </div>

      {megaTrends.length === 0 ? (
        <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted">
          No mega trends discovered yet. Check back soon.
        </p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {megaTrends.map((mt) => {
            const info = getMegaTrendInfo(mt.mega_trend);
            const displayName = info ? info.name_en : mt.mega_trend;
            const description = info ? info.description_en : null;

            return (
              <Link
                key={mt.mega_trend}
                href={`/trends/mega/${mt.slug}`}
                className="group block border border-border bg-card/40 p-6 hover:bg-card hover:border-accent/40 transition-colors"
              >
                <div className="flex items-start justify-between gap-3 mb-3">
                  <div className="font-mono text-[9px] uppercase tracking-[0.18em] text-muted flex items-center gap-3">
                    {formatFirstSeen(mt.first_seen) ? (
                      <span>Since <span className="text-paper">{formatFirstSeen(mt.first_seen)}</span></span>
                    ) : (
                      <span>Mega</span>
                    )}
                    <span className="text-border">·</span>
                    <span title="New signals in the last 30 days"><span className="text-accent tabular-nums">{(mt.signals_30d ?? 0).toLocaleString("en-US")}</span> in last 30 days</span>
                    <span className="text-border">·</span>
                    <span title="Total signals mapped to this mega-trend"><span className="text-paper tabular-nums">{mt.count.toLocaleString("en-US")}</span> total</span>
                  </div>
                  {mt.momentum && (
                    <span
                      className="inline-flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-[0.12em] px-2 py-0.5 border cursor-help"
                      title={MOMENTUM_CONFIG[mt.momentum].tooltip}
                      style={{
                        color: MOMENTUM_CONFIG[mt.momentum].color,
                        borderColor: MOMENTUM_CONFIG[mt.momentum].color + "55",
                        backgroundColor: MOMENTUM_CONFIG[mt.momentum].color + "10",
                      }}
                    >
                      <span>{MOMENTUM_CONFIG[mt.momentum].glyph}</span>
                      <span>{MOMENTUM_CONFIG[mt.momentum].label}</span>
                    </span>
                  )}
                </div>

                <h2 className="font-display text-[22px] leading-tight text-paper group-hover:text-accent transition-colors mb-2">
                  {displayName}
                </h2>
                {description && (
                  <p className="font-sans text-sm text-text leading-relaxed line-clamp-2 mb-5">
                    {description}
                  </p>
                )}

                <div className="pt-4 border-t border-dashed border-border">
                  <div className="font-mono text-[9px] uppercase tracking-[0.18em] text-muted mb-3">
                    Affected Verticals
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {mt.verticalInfos.map((v) => (
                      <span
                        key={v.id}
                        className="inline-flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-[0.12em] px-1.5 py-0.5 border"
                        style={{
                          color: v.color,
                          borderColor: `${v.color}55`,
                          backgroundColor: `${v.color}10`,
                        }}
                      >
                        <span
                          className="inline-block w-1.5 h-[2px]"
                          style={{ backgroundColor: v.color }}
                          aria-hidden="true"
                        />
                        <span>{v.code}</span>
                      </span>
                    ))}
                  </div>
                </div>

                <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-accent/70 mt-5">
                  Open mega-trend →
                </p>
              </Link>
            );
          })}
        </div>
      )}
    </>
  );
}
