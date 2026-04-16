"use client";

import Link from "next/link";
import type { Trend, VerticalInfo } from "@/lib/types";
import { getMegaTrendInfo } from "@/lib/types";
import TrendCard from "./TrendCard";

interface MegaTrendItem {
  mega_trend: string;
  count: number;
  verticals: string[];
  verticalInfos: VerticalInfo[];
}

export default function ClusterDashboard({
  megaTrends,
  crossVerticalTrends,
  topTrends,
}: {
  megaTrends: MegaTrendItem[];
  crossVerticalTrends: Trend[];
  topTrends: Trend[];
}) {
  return (
    <>
      <div className="mb-12">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-4">
          —— Signal Intelligence
        </div>
        <h1 className="font-display text-4xl md:text-[52px] leading-[1.05] tracking-tight text-paper mb-4">
          Trend <span className="italic">Clusters</span>
        </h1>
        <p className="font-sans text-text text-lg leading-relaxed max-w-2xl">
          Discover how trend signals connect across industries — mega trends,
          cross-vertical patterns, and top signals.
        </p>
      </div>

      {/* Mega-Trends Overview */}
      <section className="mb-16">
        <div className="flex items-end justify-between mb-6 pb-3 border-b border-border">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted mb-2">
              01 — Long-Horizon Shifts
            </div>
            <h2 className="font-display text-2xl text-paper">Mega Trends</h2>
          </div>
          <Link
            href="/trends/mega"
            className="font-mono text-[10px] uppercase tracking-[0.14em] text-accent hover:underline"
          >
            View All →
          </Link>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {megaTrends.map((mt) => {
            const info = getMegaTrendInfo(mt.mega_trend);
            const displayName = info ? info.name_en : mt.mega_trend;

            return (
              <Link
                key={mt.mega_trend}
                href={`/trends/mega/${encodeURIComponent(mt.mega_trend.toLowerCase().replace(/\s+/g, "-"))}`}
                className="group block border border-border bg-card/40 p-5 hover:bg-card hover:border-accent/40 transition-colors"
              >
                <div className="font-mono text-[9px] uppercase tracking-[0.18em] text-muted mb-3">
                  Mega / {mt.count} Signals
                </div>
                <h3 className="font-display text-[17px] leading-snug text-paper group-hover:text-accent transition-colors line-clamp-2 mb-4 min-h-[44px]">
                  {displayName}
                </h3>
                <div className="flex flex-wrap gap-1 pt-3 border-t border-dashed border-border">
                  {mt.verticalInfos.slice(0, 4).map((v) => (
                    <span
                      key={v.id}
                      className="font-mono text-[9px] uppercase tracking-[0.12em] px-1.5 py-0.5 border"
                      style={{
                        color: v.color,
                        borderColor: `${v.color}55`,
                        backgroundColor: `${v.color}10`,
                      }}
                      title={v.label}
                    >
                      {v.code}
                    </span>
                  ))}
                  {mt.verticalInfos.length > 4 && (
                    <span className="font-mono text-[9px] uppercase tracking-[0.12em] text-muted px-1.5 py-0.5">
                      +{mt.verticalInfos.length - 4}
                    </span>
                  )}
                </div>
              </Link>
            );
          })}
        </div>
      </section>

      {/* Cross-Vertical Trends */}
      {crossVerticalTrends.length > 0 && (
        <section className="mb-16">
          <div className="flex items-end justify-between mb-6 pb-3 border-b border-border">
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted mb-2">
                02 — Multi-Industry Impact
              </div>
              <h2 className="font-display text-2xl text-paper">
                Cross-Industry Trends
              </h2>
            </div>
            <Link
              href="/trends/cross-vertical"
              className="font-mono text-[10px] uppercase tracking-[0.14em] text-accent hover:underline"
            >
              View All →
            </Link>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {crossVerticalTrends.map((trend) => (
              <TrendCard key={trend.id} trend={trend} />
            ))}
          </div>
        </section>
      )}

      {/* Top Trends by Engagement */}
      {topTrends.length > 0 && (
        <section className="mb-16">
          <div className="mb-6 pb-3 border-b border-border">
            <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted mb-2">
              03 — Signal Strength
            </div>
            <h2 className="font-display text-2xl text-paper">Top Trends</h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {topTrends.map((trend) => (
              <TrendCard key={trend.id} trend={trend} />
            ))}
          </div>
        </section>
      )}
    </>
  );
}
