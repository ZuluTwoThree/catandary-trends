"use client";

import Link from "next/link";
import { useState, useCallback, useRef, useEffect } from "react";
import {
  getVerticalInfo,
  getPestelInfo,
  getMegaTrendInfo,
  VERTICALS,
  type Vertical,
} from "@/lib/types";
import type { ForesightCluster } from "@/lib/foresight";
import ClusterCard from "./foresight/ClusterCard";

// Concrete example searches so a first-time user never faces a blank box —
// one click runs a real search and teaches what the tool does.
const EXAMPLE_QUERIES = [
  "longevity microbiome",
  "solid-state batteries",
  "GLP-1",
  "creator economy",
  "carbon capture",
  "generative AI",
];

// Queries shorter than this never trigger a request — avoids burning searches
// (and rate limit) on single keystrokes.
const MIN_QUERY_CHARS = 3;

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

interface SearchError {
  message: string;
  /** 402: link the message to the pricing page. */
  pricingLink?: boolean;
}

/** Map an HTTP error status to user-facing copy — never expose raw status codes. */
function errorForStatus(status: number, retryAfter: string | null): SearchError {
  if (status === 429) {
    const secs = retryAfter ? parseInt(retryAfter, 10) : NaN;
    return {
      message:
        Number.isFinite(secs) && secs > 0
          ? `Too many searches — available again in about ${secs} second${secs === 1 ? "" : "s"}.`
          : "Too many searches — available again in a moment.",
    };
  }
  if (status === 402) {
    return {
      message: "This search depth is part of a paid plan.",
      pricingLink: true,
    };
  }
  return { message: "Search is briefly unavailable — please try again." };
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
export default function ForesightCockpit({
  topClusters = [],
}: {
  topClusters?: ForesightCluster[];
} = {}) {
  const [query, setQuery] = useState("");
  const [vertical, setVertical] = useState<string | null>(null);
  const [data, setData] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<SearchError | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  const doSearch = useCallback(
    async (q: string, v: string | null) => {
      const trimmed = q.trim();
      if (trimmed.length < MIN_QUERY_CHARS) {
        setData(null);
        setError(null);
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const params = new URLSearchParams({ q: trimmed, limit: "20" });
        if (v) params.set("vertical", v);
        const resp = await fetch(`/api/search?${params}`);
        if (!resp.ok) {
          setError(errorForStatus(resp.status, resp.headers.get("retry-after")));
          return;
        }
        const json: SearchResponse = await resp.json();
        setData(json);
      } catch {
        // Network failure or malformed response
        setError({ message: "Search is briefly unavailable — please try again." });
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

  const onExample = useCallback(
    (q: string) => {
      setQuery(q);
      doSearch(q, vertical);
    },
    [doSearch, vertical]
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
          Search any topic and see how it&apos;s moving — across research,
          patents, funding and the market, with the trends that surround it.
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
            aria-label="Search the signal space"
            className="w-full border border-border bg-card px-4 py-3 font-sans text-paper
                       placeholder:text-muted placeholder:font-mono placeholder:text-[12px] placeholder:uppercase placeholder:tracking-[0.12em]
                       focus:border-accent transition-colors"
          />
          {loading && (
            <div
              role="status"
              className="absolute right-3 top-1/2 -translate-y-1/2"
            >
              <div
                className="h-4 w-4 animate-spin border-2 border-border border-t-accent"
                aria-hidden="true"
              />
              <span className="sr-only">Searching…</span>
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
        <div
          role="alert"
          className="border border-warn/40 bg-warn/10 px-4 py-3 text-warn font-sans text-sm"
        >
          {error.message}
          {error.pricingLink && (
            <>
              {" "}
              <Link
                href="/trends/pricing"
                className="underline underline-offset-2 hover:text-paper transition-colors"
              >
                See plans →
              </Link>
            </>
          )}
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
                <span> matches{data.meta.embedding_available ? "" : " (text match only)"}</span>
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

      {/* Empty state — value-first: example searches + what's moving now, so a
          first-time user immediately sees something useful and learns by example. */}
      {!data && !loading && !error && (
        <div className="space-y-10">
          <div className="space-y-3">
            <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted">
              —— Try a search
            </div>
            <div className="flex flex-wrap gap-2">
              {EXAMPLE_QUERIES.map((q) => (
                <button
                  key={q}
                  onClick={() => onExample(q)}
                  className="font-mono text-[11px] tracking-[0.04em] text-paper border border-border px-3 py-1.5 hover:border-accent hover:text-accent hover:bg-accent/5 transition-colors"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>

          {/* Entry points to the explorers, so the hub isn't a dead end */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Link
              href="/trends/foresight/technology"
              className="group border border-border p-4 hover:border-accent hover:bg-accent/5 transition-colors"
            >
              <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-accent">
                Technology Explorer →
              </div>
              <div className="font-sans text-sm text-text mt-1">
                Per-technology improvement rate (MIT method) + research→market lead times
              </div>
            </Link>
            <Link
              href="/trends/foresight/clusters"
              className="group border border-border p-4 hover:border-accent hover:bg-accent/5 transition-colors"
            >
              <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-accent">
                Cluster Explorer →
              </div>
              <div className="font-sans text-sm text-text mt-1">
                What&apos;s moving right now — momentum clusters across all verticals
              </div>
            </Link>
            <Link
              href="/trends/foresight/research"
              className="group border border-border p-4 hover:border-accent hover:bg-accent/5 transition-colors"
            >
              <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-accent">
                Research Explorer →
              </div>
              <div className="font-sans text-sm text-text mt-1">
                What your peers publish — 430k+ searchable papers, preprints and grants
              </div>
            </Link>
            <Link
              href="/trends/foresight/patents"
              className="group border border-border p-4 hover:border-accent hover:bg-accent/5 transition-colors"
            >
              <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-accent">
                Patent Explorer →
              </div>
              <div className="font-sans text-sm text-text mt-1">
                What gets protected — 19M+ searchable patents with abstracts and technology facets
              </div>
            </Link>
          </div>

          {topClusters.length > 0 && (
            <div className="space-y-4">
              <div className="flex items-baseline justify-between">
                <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent">
                  —— Moving right now
                </div>
                <Link
                  href="/trends/foresight/clusters"
                  className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted hover:text-paper transition-colors"
                >
                  All clusters →
                </Link>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {topClusters.map((c) => (
                  <ClusterCard key={c.id} cluster={c} />
                ))}
              </div>
            </div>
          )}
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
    <AnalyticsCard title="Signal Themes">
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
