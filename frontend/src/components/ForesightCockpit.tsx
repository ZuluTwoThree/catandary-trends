"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { useLocale } from "@/lib/locale-context";
import {
  getVerticalInfo,
  getPestelInfo,
  getMegaTrendInfo,
  VERTICALS,
  type Vertical,
  type PestelDimension,
} from "@/lib/types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
interface SearchResult {
  id: number;
  slug: string;
  title_de: string;
  title_en: string;
  summary_de: string;
  summary_en: string;
  primary_vertical: string;
  source_name: string;
  mega_trend: string | null;
  pestel: string[];
  tags: string[];
  trend_signal_type: string;
  lead_time_tier: string;
  source_date: string | null;
  rrf_score: number;
  fts_rank: number | null;
  emb_score: number | null;
}

interface Analytics {
  total_matches: number;
  has_enough_data: boolean;
  timeline: Array<{ month: string; count: number }>;
  lead_time: Record<string, number>;
  pestel: Record<string, number>;
  mega_trends: Array<{ mega_trend: string; count: number }>;
  co_occurrence: Array<{ tag: string; count: number; tfidf: number }>;
  verticals: Record<string, number>;
}

interface SearchResponse {
  query: string;
  vertical: string | null;
  took_ms: number;
  meta: {
    fts_hits: number;
    emb_hits: number;
    total_unique: number;
    embedding_available: boolean;
    embedding_only: boolean;
  };
  analytics: Analytics;
  results: SearchResult[];
}

// ---------------------------------------------------------------------------
// Lead-time tier config
// ---------------------------------------------------------------------------
const TIER_CONFIG = {
  future: { label_de: "Future", label_en: "Future", color: "#8b5cf6", desc_de: "Science / Forschung (5-10 J.)", desc_en: "Science / Research (5-10y)" },
  market: { label_de: "Market", label_en: "Market", color: "#3b82f6", desc_de: "Fachpresse / Trade (1-2 J.)", desc_en: "Trade Press (1-2y)" },
  now: { label_de: "Now", label_en: "Now", color: "#22c55e", desc_de: "Consumer / Lifestyle (Echtzeit)", desc_en: "Consumer / Lifestyle (real-time)" },
  unknown: { label_de: "Andere", label_en: "Other", color: "#737373", desc_de: "", desc_en: "" },
} as const;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
export default function ForesightCockpit() {
  const { t, locale, mounted } = useLocale();
  const de = locale === "de";

  const [query, setQuery] = useState("");
  const [vertical, setVertical] = useState<string | null>(null);
  const [data, setData] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  const doSearch = useCallback(
    async (q: string, v: string | null) => {
      if (!q.trim()) {
        setData(null);
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const params = new URLSearchParams({ q: q.trim(), limit: "20" });
        if (v) params.set("vertical", v);
        const resp = await fetch(`/api/search?${params}`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const json: SearchResponse = await resp.json();
        setData(json);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Search failed");
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const onQueryChange = useCallback(
    (val: string) => {
      setQuery(val);
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => doSearch(val, vertical), 400);
    },
    [doSearch, vertical]
  );

  const onVerticalChange = useCallback(
    (v: string | null) => {
      setVertical(v);
      if (query.trim()) doSearch(query, v);
    },
    [doSearch, query]
  );

  // Cleanup debounce on unmount
  useEffect(() => () => { if (debounceRef.current) clearTimeout(debounceRef.current); }, []);

  if (!mounted) return null;

  const a = data?.analytics;
  const hasAnalytics = a?.has_enough_data ?? false;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">
          {de ? "Foresight Cockpit" : "Foresight Cockpit"}
        </h1>
        <p className="mt-1 text-muted text-sm">
          {de
            ? "Semantische Trend-Suche mit Signal-Analyse, Lead-Time-Tracking und Cross-Vertical-Insights."
            : "Semantic trend search with signal analysis, lead-time tracking, and cross-vertical insights."}
        </p>
      </div>

      {/* Search bar + vertical filter */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <input
            type="text"
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            placeholder={de ? "Suchbegriff eingeben..." : "Enter search term..."}
            className="w-full rounded-lg border border-border bg-card px-4 py-3 text-foreground
                       placeholder:text-muted focus:outline-none focus:border-accent
                       transition-colors"
            autoFocus
          />
          {loading && (
            <div className="absolute right-3 top-1/2 -translate-y-1/2">
              <div className="h-5 w-5 animate-spin rounded-full border-2 border-muted border-t-accent" />
            </div>
          )}
        </div>
        <div className="flex flex-wrap gap-1.5">
          <button
            onClick={() => onVerticalChange(null)}
            className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors
              ${!vertical ? "bg-accent text-white" : "bg-card text-muted hover:text-foreground border border-border"}`}
          >
            {de ? "Alle" : "All"}
          </button>
          {VERTICALS.map((v) => (
            <button
              key={v.id}
              onClick={() => onVerticalChange(v.id)}
              className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors
                ${vertical === v.id ? "text-white" : "bg-card text-muted hover:text-foreground border border-border"}`}
              style={vertical === v.id ? { backgroundColor: v.color } : undefined}
            >
              {v.icon} {v.id}
            </button>
          ))}
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-red-400 text-sm">
          {error}
        </div>
      )}

      {/* Results + Analytics */}
      {data && (
        <div className="flex flex-col lg:flex-row gap-6">
          {/* Main: results */}
          <div className="flex-1 min-w-0 space-y-4">
            {/* Meta bar */}
            <div className="flex items-center justify-between text-xs text-muted">
              <span>
                {data.analytics.total_matches} {de ? "Treffer" : "matches"}
                {data.meta.embedding_available ? "" : " (FTS only)"}
              </span>
              <span>{data.took_ms}ms</span>
            </div>

            {/* Embedding-only hint */}
            {data.meta.embedding_only && data.results.length > 0 && (
              <div className="rounded-lg border border-accent/20 bg-accent/5 px-4 py-3 text-sm text-muted">
                {de
                  ? "Keine exakte Textübereinstimmung — Ergebnisse basieren auf semantischer Ähnlichkeit."
                  : "No exact text match — results are based on semantic similarity."}
              </div>
            )}

            {/* Not enough data hint */}
            {!hasAnalytics && data.analytics.total_matches > 0 && (
              <div className="rounded-lg border border-border bg-card px-4 py-3 text-sm text-muted">
                {de
                  ? `Zu wenige Signale (${data.analytics.total_matches}) für Trend-Analyse. Mindestens 30 Treffer nötig.`
                  : `Too few signals (${data.analytics.total_matches}) for trend analysis. At least 30 matches needed.`}
              </div>
            )}

            {/* No results */}
            {data.results.length === 0 && (
              <div className="text-center py-12 text-muted">
                {de ? "Keine Treffer" : "No results"}
              </div>
            )}

            {/* Result cards */}
            {data.results.map((r) => {
              const maxRrf = data.results[0]?.rrf_score || 1;
              const relevance = Math.round((r.rrf_score / maxRrf) * 100);
              return <ResultCard key={r.id} result={r} de={de} relevance={relevance} />;
            })}
          </div>

          {/* Sidebar: analytics */}
          {hasAnalytics && a && (
            <div className="w-full lg:w-80 xl:w-96 shrink-0 space-y-5">
              <TimelineChart timeline={a.timeline} de={de} />
              <LeadTimeBreakdown leadTime={a.lead_time} total={a.total_matches} de={de} />
              <VerticalDistribution verticals={a.verticals} de={de} />
              <PestelProfile pestel={a.pestel} total={a.total_matches} de={de} />
              <MegaTrendDistribution megaTrends={a.mega_trends} de={de} />
              <CoOccurrenceCloud tags={a.co_occurrence} de={de} />
            </div>
          )}
        </div>
      )}

      {/* Empty state */}
      {!data && !loading && !error && (
        <div className="text-center py-20 text-muted space-y-2">
          <div className="text-4xl opacity-30">&#x1F50D;</div>
          <p className="text-sm">
            {de
              ? "Suchbegriff eingeben, um Trend-Signale zu entdecken"
              : "Enter a search term to discover trend signals"}
          </p>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Result card
// ---------------------------------------------------------------------------
function ResultCard({ result: r, de, relevance }: { result: SearchResult; de: boolean; relevance: number }) {
  const vi = getVerticalInfo(r.primary_vertical as Vertical);
  const tierCfg = TIER_CONFIG[r.lead_time_tier as keyof typeof TIER_CONFIG] ?? TIER_CONFIG.unknown;

  return (
    <a
      href={`/trends/${r.slug}`}
      className="block rounded-lg border border-border bg-card p-4 hover:bg-card-hover transition-colors"
    >
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1.5 flex-wrap">
            <span
              className="inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium"
              style={{ backgroundColor: `${vi.color}15`, color: vi.color, border: `1px solid ${vi.color}30` }}
            >
              {vi.icon} {vi.id}
            </span>
            <span
              className="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium"
              style={{ backgroundColor: `${tierCfg.color}20`, color: tierCfg.color, border: `1px solid ${tierCfg.color}40` }}
            >
              {tierCfg.label_en}
            </span>
            {r.mega_trend && (
              <span className="text-[10px] text-muted truncate max-w-[160px]">
                {getMegaTrendInfo(r.mega_trend)?.[de ? "name_de" : "name_en"] ?? r.mega_trend.replace(/_/g, " ")}
              </span>
            )}
          </div>
          <h3 className="font-semibold text-sm leading-snug mb-1">
            {de ? r.title_de : r.title_en}
          </h3>
          <p className="text-xs text-muted line-clamp-2">
            {de ? (r.summary_de || r.summary_en) : r.summary_en}
          </p>
          <div className="mt-2 flex items-center gap-3 text-[10px] text-muted">
            <span>{r.source_name}</span>
            {r.source_date && (
              <span>{new Date(r.source_date).toLocaleDateString(de ? "de-DE" : "en-US", { month: "short", day: "numeric", year: "numeric" })}</span>
            )}
            {relevance > 0 && (
              <span className="text-accent">{relevance}%</span>
            )}
          </div>
        </div>
      </div>
    </a>
  );
}

// ---------------------------------------------------------------------------
// Timeline chart (simple SVG bar chart)
// ---------------------------------------------------------------------------
function TimelineChart({ timeline, de }: { timeline: Analytics["timeline"]; de: boolean }) {
  if (!timeline.length) return null;
  const maxCount = Math.max(...timeline.map((m) => m.count), 1);
  const barW = Math.max(4, Math.floor(280 / timeline.length) - 1);

  return (
    <AnalyticsCard title={de ? "Signal-Timeline" : "Signal Timeline"}>
      <div className="flex items-end gap-px h-24 overflow-x-auto">
        {timeline.map((m) => (
          <div key={m.month} className="flex flex-col items-center group relative">
            <div
              className="bg-accent/70 hover:bg-accent rounded-t transition-colors"
              style={{
                width: barW,
                height: `${Math.max(2, (m.count / maxCount) * 80)}px`,
              }}
            />
            <div className="absolute -top-6 hidden group-hover:block bg-card border border-border rounded px-1.5 py-0.5 text-[10px] whitespace-nowrap z-10">
              {m.month}: {m.count}
            </div>
          </div>
        ))}
      </div>
      <div className="flex justify-between text-[10px] text-muted mt-1">
        <span>{timeline[0]?.month}</span>
        <span>{timeline[timeline.length - 1]?.month}</span>
      </div>
    </AnalyticsCard>
  );
}

// ---------------------------------------------------------------------------
// Lead-time tier breakdown
// ---------------------------------------------------------------------------
function LeadTimeBreakdown({ leadTime, total, de }: { leadTime: Record<string, number>; total: number; de: boolean }) {
  const tiers = ["future", "market", "now"] as const;
  return (
    <AnalyticsCard title={de ? "Signal-Pfad" : "Signal Path"}>
      <div className="space-y-2">
        {tiers.map((tier) => {
          const count = leadTime[tier] || 0;
          const pct = total > 0 ? (count / total) * 100 : 0;
          const cfg = TIER_CONFIG[tier];
          return (
            <div key={tier}>
              <div className="flex justify-between text-xs mb-0.5">
                <span style={{ color: cfg.color }}>
                  {cfg.label_en}
                  <span className="text-muted ml-1 text-[10px]">
                    {de ? cfg.desc_de : cfg.desc_en}
                  </span>
                </span>
                <span className="text-muted">{count} ({Math.round(pct)}%)</span>
              </div>
              <div className="h-2 rounded-full bg-border overflow-hidden">
                <div
                  className="h-full rounded-full transition-all"
                  style={{ width: `${pct}%`, backgroundColor: cfg.color }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </AnalyticsCard>
  );
}

// ---------------------------------------------------------------------------
// Cross-vertical distribution
// ---------------------------------------------------------------------------
function VerticalDistribution({ verticals, de }: { verticals: Record<string, number>; de: boolean }) {
  const entries = Object.entries(verticals).sort((a, b) => b[1] - a[1]);
  const max = entries[0]?.[1] ?? 1;

  return (
    <AnalyticsCard title={de ? "Cross-Vertical" : "Cross-Vertical"}>
      <div className="space-y-1.5">
        {entries.map(([v, count]) => {
          const info = getVerticalInfo(v as Vertical);
          return (
            <div key={v} className="flex items-center gap-2 text-xs">
              <span className="w-5 text-center">{info.icon}</span>
              <span className="w-16 truncate" style={{ color: info.color }}>{v}</span>
              <div className="flex-1 h-2 rounded-full bg-border overflow-hidden">
                <div
                  className="h-full rounded-full"
                  style={{ width: `${(count / max) * 100}%`, backgroundColor: info.color }}
                />
              </div>
              <span className="text-muted w-8 text-right">{count}</span>
            </div>
          );
        })}
      </div>
    </AnalyticsCard>
  );
}

// ---------------------------------------------------------------------------
// PESTEL profile
// ---------------------------------------------------------------------------
function PestelProfile({ pestel, total, de }: { pestel: Record<string, number>; total: number; de: boolean }) {
  const dims = ["P", "E", "S", "T", "En", "L"] as const;
  return (
    <AnalyticsCard title="PESTEL">
      <div className="flex items-end gap-2 h-20">
        {dims.map((d) => {
          const count = pestel[d] || 0;
          const pct = total > 0 ? (count / total) * 100 : 0;
          const info = getPestelInfo(d);
          return (
            <div key={d} className="flex-1 flex flex-col items-center group relative">
              <div
                className="w-full rounded-t transition-colors"
                style={{
                  height: `${Math.max(2, (pct / 100) * 64)}px`,
                  backgroundColor: `${info.color}80`,
                }}
              />
              <span className="text-[10px] mt-1" style={{ color: info.color }}>
                {d}
              </span>
              <div className="absolute -top-6 hidden group-hover:block bg-card border border-border rounded px-1.5 py-0.5 text-[10px] whitespace-nowrap z-10">
                {info.label}: {count} ({Math.round(pct)}%)
              </div>
            </div>
          );
        })}
      </div>
    </AnalyticsCard>
  );
}

// ---------------------------------------------------------------------------
// Mega-trend distribution
// ---------------------------------------------------------------------------
function MegaTrendDistribution({ megaTrends, de }: { megaTrends: Analytics["mega_trends"]; de: boolean }) {
  if (!megaTrends.length) return null;
  const max = megaTrends[0]?.count ?? 1;

  return (
    <AnalyticsCard title={de ? "Mega-Trends" : "Mega Trends"}>
      <div className="space-y-1.5">
        {megaTrends.slice(0, 8).map((mt) => {
          const info = getMegaTrendInfo(mt.mega_trend);
          const label = info
            ? (de ? info.name_de : info.name_en)
            : mt.mega_trend.replace(/_/g, " ");
          return (
            <div key={mt.mega_trend} className="flex items-center gap-2 text-xs">
              <span className="w-5 text-center">{info?.icon ?? "?"}</span>
              <span className="flex-1 truncate text-foreground/80">{label}</span>
              <div className="w-16 h-1.5 rounded-full bg-border overflow-hidden">
                <div
                  className="h-full rounded-full bg-accent/70"
                  style={{ width: `${(mt.count / max) * 100}%` }}
                />
              </div>
              <span className="text-muted w-6 text-right">{mt.count}</span>
            </div>
          );
        })}
      </div>
    </AnalyticsCard>
  );
}

// ---------------------------------------------------------------------------
// Co-occurrence cloud (TF-IDF weighted)
// ---------------------------------------------------------------------------
function CoOccurrenceCloud({ tags, de }: { tags: Analytics["co_occurrence"]; de: boolean }) {
  if (!tags.length) return null;
  const maxTfidf = Math.max(...tags.map((t) => t.tfidf), 1);

  return (
    <AnalyticsCard title={de ? "Verwandte Begriffe" : "Related Terms"}>
      <div className="flex flex-wrap gap-1.5">
        {tags.map((t) => {
          const rel = t.tfidf / maxTfidf;
          const fontSize = 10 + rel * 6; // 10px to 16px
          const opacity = 0.4 + rel * 0.6;
          return (
            <span
              key={t.tag}
              className="inline-block rounded-md bg-accent/10 px-2 py-0.5 text-accent cursor-default transition-opacity hover:opacity-100"
              style={{ fontSize: `${fontSize}px`, opacity }}
              title={`${t.tag}: ${t.count}x (TF-IDF: ${t.tfidf})`}
            >
              {t.tag.replace(/_/g, " ")}
            </span>
          );
        })}
      </div>
    </AnalyticsCard>
  );
}

// ---------------------------------------------------------------------------
// Analytics card wrapper
// ---------------------------------------------------------------------------
function AnalyticsCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <h3 className="text-xs font-semibold text-muted uppercase tracking-wider mb-3">
        {title}
      </h3>
      {children}
    </div>
  );
}
