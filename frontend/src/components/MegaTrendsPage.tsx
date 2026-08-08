"use client";

import Link from "next/link";
import type { VerticalInfo, MegaTrendInfo, Vertical } from "@/lib/types";
import { getMegaTrendInfo, getVerticalInfo } from "@/lib/types";

interface MegaTrendItem {
  mega_trend: string;
  count: number;
  verticals: string[];
  verticalInfos: VerticalInfo[];
  slug: string;
  /** Measured (90d share vs prior 90d, lib/momentum.ts); null = no claim. */
  momentum?: "rising" | "stable" | "declining" | "emerging" | null;
  /** Earned Megatrend badge (measured axes, see measure_mega_axes.py). */
  megatrend?: boolean;
  measured?: {
    measured_at: string; reach: number; tiers: number;
    lead_months: number | null; lead_tier?: string | null;
    dom_vertical: string; dom_share: number;
    peak_year?: number | null; peak_market_n?: number;
    last12_market_n?: number; faded_hype?: boolean;
  } | null;
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
          —— The Signal Map
        </div>
        <h1 className="font-display text-4xl md:text-[52px] leading-[1.05] tracking-tight text-paper mb-4">
          Mega Signal <span className="italic">Themes</span>
        </h1>
        <p className="font-sans text-text text-lg leading-relaxed max-w-2xl">
          Every signal we track lands in one of these themes. The badges are
          earned from measurement, never hand-assigned — and the numbers behind
          each badge are printed on its card.
        </p>
      </div>

      {/* Legend: what the badges and the measured line mean, in plain words */}
      <div className="mb-10 border border-dashed border-border bg-card/30 p-5">
        <div className="font-mono text-[9px] uppercase tracking-[0.2em] text-muted mb-4">
          How to read these cards
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-3">
          <div className="flex items-baseline gap-3">
            <span className="shrink-0 inline-flex items-center font-mono text-[9px] uppercase tracking-[0.12em] px-2 py-0.5 bg-accent text-ink font-bold">
              Megatrend
            </span>
            <span className="font-sans text-[13px] text-text leading-snug">
              Spans several industries, has evidence all the way from research to
              market — and research got there first.
            </span>
          </div>
          <div className="flex items-baseline gap-3">
            <span className="shrink-0 inline-flex items-center font-mono text-[9px] uppercase tracking-[0.12em] px-2 py-0.5 border"
              style={{ color: "#a78bfa", borderColor: "#a78bfa55", backgroundColor: "#a78bfa10" }}>
              Domain
            </span>
            <span className="font-sans text-[13px] text-text leading-snug">
              A deep field, not a cross-industry shift: two thirds or more of its
              signals sit in a single industry.
            </span>
          </div>
          <div className="flex items-baseline gap-3">
            <span className="shrink-0 inline-flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-[0.12em] px-2 py-0.5 border"
              style={{ color: "#c9a227", borderColor: "#c9a22755", backgroundColor: "#c9a22710" }}>
              <span>◇</span><span>Faded Hype</span>
            </span>
            <span className="font-sans text-[13px] text-text leading-snug">
              Coverage peaked years ago and has collapsed since — much was
              written, little proved durable.
            </span>
          </div>
          <div className="flex items-baseline gap-3">
            <span className="shrink-0 inline-flex items-center gap-1 font-mono text-[9px] uppercase tracking-[0.12em] px-2 py-0.5 border"
              style={{ color: "#22c55e", borderColor: "#22c55e55", backgroundColor: "#22c55e10" }}>
              ↗ → ↘
            </span>
            <span className="font-sans text-[13px] text-text leading-snug">
              Momentum: the theme&apos;s share of new signals, last 90 days vs the
              90 before. Too little data — no badge, no guess.
            </span>
          </div>
          <div className="flex items-baseline gap-3 md:col-span-2">
            <span className="shrink-0 font-mono text-[9px] uppercase tracking-[0.12em] text-muted pt-0.5">
              Measured ·
            </span>
            <span className="font-sans text-[13px] text-text leading-snug">
              The numbers behind the badges: <span className="text-paper">reach</span> =
              how evenly signals spread across our eight industries (0–1) ·{" "}
              <span className="text-paper">tiers</span> = evidence in research,
              patents, funding, market ·{" "}
              <span className="text-paper">lead</span> = how many months research
              ran ahead of market coverage. Hover any number for detail.
            </span>
          </div>
        </div>
      </div>

      {megaTrends.length === 0 ? (
        <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted">
          No signal themes yet. Check back soon.
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
                    <span title="Total signals mapped to this theme"><span className="text-paper tabular-nums">{mt.count.toLocaleString("en-US")}</span> total</span>
                  </div>
                  <span className="inline-flex items-center gap-1.5">
                  {mt.megatrend && mt.measured && (
                    <span
                      className="inline-flex items-center font-mono text-[9px] uppercase tracking-[0.12em] px-2 py-0.5 bg-accent text-ink font-bold cursor-help"
                      title={`Earned: spans industries (reach ${mt.measured.reach.toFixed(2)}), evidenced across all 4 innovation tiers, ${mt.measured.lead_tier ?? "early"} tier led the market by ${mt.measured.lead_months ?? "—"} months. Measured ${mt.measured.measured_at}.`}
                    >
                      Megatrend
                    </span>
                  )}
                  {!mt.megatrend && mt.measured && mt.measured.dom_share >= 0.65 && (
                    <span
                      className="inline-flex items-center font-mono text-[9px] uppercase tracking-[0.12em] px-2 py-0.5 border cursor-help"
                      title={`${Math.round(mt.measured.dom_share * 100)}% of signals sit in one vertical — a deep field, not a cross-industry shift. Measured ${mt.measured.measured_at}.`}
                      style={{
                        color: getVerticalInfo(mt.measured.dom_vertical as Vertical).color,
                        borderColor: getVerticalInfo(mt.measured.dom_vertical as Vertical).color + "55",
                        backgroundColor: getVerticalInfo(mt.measured.dom_vertical as Vertical).color + "10",
                      }}
                    >
                      {mt.measured.dom_vertical} Domain
                    </span>
                  )}
                  {mt.measured?.faded_hype && (
                    <span
                      className="inline-flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-[0.12em] px-2 py-0.5 border cursor-help"
                      title={`Media coverage peaked in ${mt.measured.peak_year} (${(mt.measured.peak_market_n ?? 0).toLocaleString("en-US")} market signals) and has fallen to ${(mt.measured.last12_market_n ?? 0).toLocaleString("en-US")} in the last 12 months — much was written, little proved durable. Measured ${mt.measured.measured_at}.`}
                      style={{
                        color: "#c9a227",
                        borderColor: "#c9a22755",
                        backgroundColor: "#c9a22710",
                      }}
                    >
                      <span>◇</span>
                      <span>Faded Hype {mt.measured.peak_year}</span>
                    </span>
                  )}
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
                  </span>
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
                  {mt.measured && (
                    <div className="font-mono text-[9px] uppercase tracking-[0.12em] text-muted mb-3 tabular-nums">
                      Measured{" · "}
                      <span className="cursor-help" title={`Reach ${mt.measured.reach.toFixed(2)} of 1: how evenly this theme's signals spread across our eight industries. 0 = a single industry, 1 = all eight equally.`}>
                        reach <span className="text-paper">{mt.measured.reach.toFixed(2)}</span>
                      </span>
                      {" · "}
                      <span className="cursor-help" title={`Evidence in ${mt.measured.tiers} of 4 innovation tiers: research, patents, funding, market coverage.`}>
                        <span className="text-paper">{mt.measured.tiers}/4</span> tiers
                      </span>
                      {mt.megatrend && mt.measured.lead_months != null ? (
                        <>{" · "}
                        <span className="cursor-help" title={`${mt.measured.lead_tier ?? "Early"} signals appeared ${mt.measured.lead_months} months before market coverage picked the theme up.`}>
                          {mt.measured.lead_tier ?? "early"}→market{" "}
                          <span className="text-paper">+{mt.measured.lead_months} mo</span>
                        </span></>
                      ) : mt.measured.faded_hype ? (
                        <>{" · "}
                        <span className="cursor-help" title={`Market signals per year: ${mt.measured.peak_market_n} at the ${mt.measured.peak_year} peak vs ${mt.measured.last12_market_n} in the last 12 months.`}>
                          peak <span className="text-paper">{mt.measured.peak_market_n}</span>{" "}
                          ({mt.measured.peak_year}) → last 12 mo{" "}
                          <span className="text-paper">{mt.measured.last12_market_n}</span>
                        </span></>
                      ) : mt.measured.dom_share >= 0.65 ? (
                        <>{" · "}
                        <span className="cursor-help" title={`${Math.round(mt.measured.dom_share * 100)}% of this theme's signals sit in ${mt.measured.dom_vertical} — the reason it reads as a domain, not a cross-industry shift.`}>
                          {mt.measured.dom_vertical} holds{" "}
                          <span className="text-paper">{Math.round(mt.measured.dom_share * 100)}%</span>
                        </span></>
                      ) : null}
                    </div>
                  )}
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
                  Open theme →
                </p>
              </Link>
            );
          })}
        </div>
      )}
    </>
  );
}
