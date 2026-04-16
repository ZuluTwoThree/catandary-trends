"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import {
  getVerticalInfo,
  getPestelInfo,
  getMegaTrendInfo,
  VERTICALS,
  type Vertical,
} from "@/lib/types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
interface SearchResult {
  id: number;
  slug: string;
  title_en: string;
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
  future: { label: "Future", color: "#a78bfa", desc: "Science / Research (5-10y)" },
  market: { label: "Market", color: "#60a5fa", desc: "Trade Press (1-2y)" },
  now: { label: "Now", color: "#d4ff3a", desc: "Consumer / Lifestyle (real-time)" },
  unknown: { label: "Other", color: "#8a8d82", desc: "" },
} as const;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
export default function ForesightCockpit() {
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

  useEffect(() => () => { if (debounceRef.current) clearTimeout(debounceRef.current); }, []);

  const a = data?.analytics;
  const hasAnalytics = a?.has_enough_data ?? false;

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-3">
          —— Premium Intelligence
        </div>
        <h1 className="font-display text-4xl md:text-[44px] leading-[1.05] tracking-tight text-paper mb-3">
          Foresight <span className="italic">Cockpit</span>
        </h1>
        <p className="font-sans text-text text-base max-w-2xl leading-relaxed">
          Semantic trend search with signal analysis, lead-time tracking, and
          cross-vertical insights.
        </p>
      </div>

      {/* Search bar + vertical filter */}
      <div className="flex flex-col gap-3">
        <div className="relative">
          <input
            type="text"
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            placeholder="Enter search term..."
            className="w-full border border-border bg-card px-4 py-3 font-sans text-paper
                       placeholder:text-muted placeholder:font-mono placeholder:text-[12px] placeholder:uppercase placeholder:tracking-[0.12em]
                       focus:outline-none focus:border-accent transition-colors"
            autoFocus
          />
          {loading && (
            <div className="absolute right-3 top-1/2 -translate-y-1/2">
              <div className="h-4 w-4 animate-spin border-2 border-border border-t-accent" />
            </div>
          )}
        </div>
        <div className="flex flex-wrap border border-border">
          <button
            onClick={() => onVerticalChange(null)}
            className={`font-mono text-[10px] uppercase tracking-[0.12em] px-4 py-2.5 border-r border-border transition-colors ${
              !vertical
                ? "text-accent bg-accent/5"
                : "text-muted hover:text-paper hover:bg-white/[0.02]"
            }`}
          >
            All
          </button>
          {VERTICALS.map((v, idx) => (
            <button
              key={v.id}
              onClick={() => onVerticalChange(v.id)}
              className={`font-mono text-[10px] uppercase tracking-[0.12em] px-4 py-2.5 inline-flex items-center gap-2 transition-colors ${
                idx < VERTICALS.length - 1 ? "border-r border-border" : ""
              } ${
                vertical === v.id
                  ? "bg-accent/5"
                  : "text-muted hover:text-paper hover:bg-white/[0.02]"
              }`}
              style={vertical === v.id ? { color: v.color } : undefined}
            >
              <span
                className="inline-block w-2 h-[3px]"
                style={{ backgroundColor: v.color }}
                aria-hidden="true"
              />
              <span>{v.code}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="border border-warn/40 bg-warn/10 px-4 py-3 text-warn font-mono text-xs uppercase tracking-[0.12em]">
          {error}
        </div>
      )}

      {/* Results + Analytics */}
      {data && (
        <div className="flex flex-col lg:flex-row gap-6">
          {/* Main: results */}
          <div className="flex-1 min-w-0 space-y-3">
            {/* Meta bar */}
            <div className="flex items-center justify-between font-mono text-[10px] uppercase tracking-[0.14em] text-muted pb-2 border-b border-border">
              <span>
                <span className="text-paper">{data.analytics.total_matches}</span>
                <span> matches{data.meta.embedding_available ? "" : " (FTS only)"}</span>
              </span>
              <span>{data.took_ms}ms</span>
            </div>

            {/* Embedding-only hint */}
            {data.meta.embedding_only && data.results.length > 0 && (
              <div className="border-l-[3px] border-accent pl-4 py-1 font-sans text-sm text-text">
                No exact text match — results are based on semantic similarity.
              </div>
            )}

            {/* Not enough data hint */}
            {!hasAnalytics && data.analytics.total_matches > 0 && (
              <div className="border border-border bg-card/40 px-4 py-3 font-sans text-sm text-muted">
                Too few signals ({data.analytics.total_matches}) for trend
                analysis. At least 30 matches needed.
              </div>
            )}

            {/* No results */}
            {data.results.length === 0 && (
              <div className="text-center py-12 font-mono text-[11px] uppercase tracking-[0.18em] text-muted">
                No Results
              </div>
            )}

            {/* Result cards */}
            {data.results.map((r) => {
              const RRF_MAX = 2 / 61;
              const relevance = Math.round((r.rrf_score / RRF_MAX) * 100);
              return <ResultCard key={r.id} result={r} relevance={relevance} />;
            })}
          </div>

          {/* Sidebar: analytics */}
          {hasAnalytics && a && (
            <div className="w-full lg:w-80 xl:w-96 shrink-0 space-y-4">
              <TimelineChart timeline={a.timeline} />
              <LeadTimeBreakdown leadTime={a.lead_time} total={a.total_matches} />
              <VerticalDistribution verticals={a.verticals} />
              <PestelProfile pestel={a.pestel} total={a.total_matches} />
              <MegaTrendDistribution megaTrends={a.mega_trends} />
              <CoOccurrenceCloud tags={a.co_occurrence} />
            </div>
          )}
        </div>
      )}

      {/* Empty state */}
      {!data && !loading && !error && (
        <div className="text-center py-20 space-y-3 border border-dashed border-border">
          <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent">
            Awaiting Query
          </div>
          <p className="font-sans text-sm text-muted">
            Enter a search term to discover trend signals
          </p>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Result card
// ---------------------------------------------------------------------------
function ResultCard({ result: r, relevance }: { result: SearchResult; relevance: number }) {
  const vi = getVerticalInfo(r.primary_vertical as Vertical);
  const tierCfg = TIER_CONFIG[r.lead_time_tier as keyof typeof TIER_CONFIG] ?? TIER_CONFIG.unknown;

  return (
    <a
      href={`/trends/${r.slug}`}
      className="block border border-border border-l-[3px] bg-card/40 p-4 hover:bg-card transition-colors"
      style={{ borderLeftColor: vi.color }}
    >
      <div className="flex items-center gap-2 mb-2 flex-wrap">
        <span
          className="inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.12em] px-2 py-0.5 border"
          style={{ backgroundColor: `${vi.color}12`, color: vi.color, borderColor: `${vi.color}55` }}
        >
          <span
            className="inline-block w-2 h-[3px]"
            style={{ backgroundColor: vi.color }}
            aria-hidden="true"
          />
          <span>{vi.code}</span>
        </span>
        <span
          className="inline-flex items-center font-mono text-[9px] uppercase tracking-[0.12em] px-2 py-0.5 border"
          style={{ backgroundColor: `${tierCfg.color}15`, color: tierCfg.color, borderColor: `${tierCfg.color}55` }}
        >
          {tierCfg.label}
        </span>
        {r.mega_trend && (
          <span className="font-mono text-[9px] uppercase tracking-[0.12em] text-muted truncate max-w-[160px]">
            {getMegaTrendInfo(r.mega_trend)?.name_en ?? r.mega_trend.replace(/_/g, " ")}
          </span>
        )}
      </div>
      <h3 className="font-display text-[17px] leading-snug text-paper mb-1">
        {r.title_en}
      </h3>
      <p className="font-sans text-xs text-text line-clamp-2">{r.summary_en}</p>
      <div className="mt-3 pt-2 border-t border-dashed border-border flex items-center gap-3 font-mono text-[9px] uppercase tracking-[0.14em] text-muted">
        <span>{r.source_name}</span>
        {r.source_date && (
          <span>
            {new Date(r.source_date).toLocaleDateString("en-US", {
              month: "short", day: "numeric", year: "numeric",
            })}
          </span>
        )}
        {relevance > 0 && <span className="ml-auto text-accent">{relevance}%</span>}
      </div>
    </a>
  );
}

// ---------------------------------------------------------------------------
// Timeline chart
// ---------------------------------------------------------------------------
function TimelineChart({ timeline }: { timeline: Analytics["timeline"] }) {
  if (!timeline.length) return null;
  const maxCount = Math.max(...timeline.map((m) => m.count), 1);
  const barW = Math.max(4, Math.floor(280 / timeline.length) - 1);

  return (
    <AnalyticsCard title="Signal Timeline">
      <div className="flex items-end gap-px h-24 overflow-x-auto">
        {timeline.map((m) => (
          <div key={m.month} className="flex flex-col items-center group relative">
            <div
              className="bg-accent/70 hover:bg-accent transition-colors"
              style={{
                width: barW,
                height: `${Math.max(2, (m.count / maxCount) * 80)}px`,
              }}
            />
            <div className="absolute -top-6 hidden group-hover:block bg-card border border-border px-1.5 py-0.5 font-mono text-[10px] whitespace-nowrap z-10">
              {m.month}: {m.count}
            </div>
          </div>
        ))}
      </div>
      <div className="flex justify-between font-mono text-[9px] uppercase tracking-[0.14em] text-muted mt-2">
        <span>{timeline[0]?.month}</span>
        <span>{timeline[timeline.length - 1]?.month}</span>
      </div>
    </AnalyticsCard>
  );
}

// ---------------------------------------------------------------------------
// Lead-time tier breakdown
// ---------------------------------------------------------------------------
function LeadTimeBreakdown({ leadTime, total }: { leadTime: Record<string, number>; total: number }) {
  const tiers = ["future", "market", "now"] as const;
  return (
    <AnalyticsCard title="Signal Path">
      <div className="space-y-3">
        {tiers.map((tier) => {
          const count = leadTime[tier] || 0;
          const pct = total > 0 ? (count / total) * 100 : 0;
          const cfg = TIER_CONFIG[tier];
          return (
            <div key={tier}>
              <div className="flex justify-between font-mono text-[10px] uppercase tracking-[0.12em] mb-1">
                <span style={{ color: cfg.color }}>{cfg.label}</span>
                <span className="text-muted">{count} · {Math.round(pct)}%</span>
              </div>
              <div className="h-[3px] bg-border overflow-hidden">
                <div
                  className="h-full transition-all"
                  style={{ width: `${pct}%`, backgroundColor: cfg.color }}
                />
              </div>
              {cfg.desc && (
                <div className="font-mono text-[9px] uppercase tracking-[0.12em] text-muted/70 mt-1">
                  {cfg.desc}
                </div>
              )}
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
function VerticalDistribution({ verticals }: { verticals: Record<string, number> }) {
  const entries = Object.entries(verticals).sort((a, b) => b[1] - a[1]);
  const max = entries[0]?.[1] ?? 1;

  return (
    <AnalyticsCard title="Cross-Vertical">
      <div className="space-y-2">
        {entries.map(([v, count]) => {
          const info = getVerticalInfo(v as Vertical);
          return (
            <div key={v} className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.12em]">
              <span
                className="inline-block w-2 h-[3px] shrink-0"
                style={{ backgroundColor: info.color }}
                aria-hidden="true"
              />
              <span className="w-12 shrink-0" style={{ color: info.color }}>{info.code}</span>
              <div className="flex-1 h-[3px] bg-border overflow-hidden">
                <div
                  className="h-full"
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
function PestelProfile({ pestel, total }: { pestel: Record<string, number>; total: number }) {
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
                className="w-full transition-colors"
                style={{
                  height: `${Math.max(2, (pct / 100) * 64)}px`,
                  backgroundColor: `${info.color}80`,
                }}
              />
              <span
                className="font-mono text-[10px] uppercase tracking-[0.12em] mt-1"
                style={{ color: info.color }}
              >
                {d}
              </span>
              <div className="absolute -top-6 hidden group-hover:block bg-card border border-border px-1.5 py-0.5 font-mono text-[10px] whitespace-nowrap z-10">
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
function MegaTrendDistribution({ megaTrends }: { megaTrends: Analytics["mega_trends"] }) {
  if (!megaTrends.length) return null;
  const max = megaTrends[0]?.count ?? 1;

  return (
    <AnalyticsCard title="Mega Trends">
      <div className="space-y-2">
        {megaTrends.slice(0, 8).map((mt) => {
          const info = getMegaTrendInfo(mt.mega_trend);
          const label = info ? info.name_en : mt.mega_trend.replace(/_/g, " ");
          return (
            <div key={mt.mega_trend} className="flex items-center gap-2 text-xs">
              <span className="flex-1 truncate font-sans text-paper/90">{label}</span>
              <div className="w-16 h-[3px] bg-border overflow-hidden">
                <div
                  className="h-full bg-accent/70"
                  style={{ width: `${(mt.count / max) * 100}%` }}
                />
              </div>
              <span className="font-mono text-[10px] text-muted w-6 text-right">{mt.count}</span>
            </div>
          );
        })}
      </div>
    </AnalyticsCard>
  );
}

// ---------------------------------------------------------------------------
// Co-occurrence cloud
// ---------------------------------------------------------------------------
function CoOccurrenceCloud({ tags }: { tags: Analytics["co_occurrence"] }) {
  if (!tags.length) return null;
  const maxTfidf = Math.max(...tags.map((t) => t.tfidf), 1);

  return (
    <AnalyticsCard title="Related Terms">
      <div className="flex flex-wrap gap-1.5">
        {tags.map((t) => {
          const rel = t.tfidf / maxTfidf;
          const fontSize = 10 + rel * 6;
          const opacity = 0.4 + rel * 0.6;
          return (
            <span
              key={t.tag}
              className="inline-block font-mono uppercase tracking-[0.08em] border border-accent/40 bg-accent/10 px-1.5 py-0.5 text-accent cursor-default transition-opacity hover:opacity-100"
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
    <div className="border border-border bg-card/40 p-4">
      <h3 className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted mb-4 pb-2 border-b border-dashed border-border">
        —— {title}
      </h3>
      {children}
    </div>
  );
}
