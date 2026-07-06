"use client";

import { useState } from "react";

/**
 * Super Pro+ on-demand scope: type any technology phrase, get its TIR and
 * cross-tier lead time computed live over the full signal space. Talks to
 * /api/foresight/query (which embeds the phrase + projects it onto the tiers).
 */

interface Cpc {
  symbol: string;
  title: string;
  dist: number;
  tir_pct: number | null;
  cycle: number | null;
  curated: string | null;
}
interface Tier {
  n: number;
  first: number | null;
  takeoff: number | null;
  median: number | null;
  series: Record<string, number>;
}
interface QueryResult {
  query: string;
  threshold: number;
  nearest_cpcs: Cpc[];
  tiers: Record<string, Tier>;
  tir_pct: number | null;
  tir_cpc: string | null;
  tir_via: string | null;
  tir_is_nearest: boolean;
  cycle_time_years: number | null;
  lead_science_market: number | null;
  lead_patent_market: number | null;
  market_floored: boolean;
  error?: string;
}

const X0 = 1990;
const X1 = 2026;
const YEARS = Array.from({ length: X1 - X0 + 1 }, (_, i) => X0 + i);
const TIER_LABEL: Record<string, string> = {
  science: "Research",
  patent: "Patents",
  funding: "Funding",
  market: "Market",
};
const EXAMPLES = [
  "recombinant food protein for cheesemaking",
  "solid-state battery electrolyte",
  "mRNA vaccine manufacturing",
  "perovskite tandem solar cells",
];

function Spark({ series }: { series: Record<string, number> }) {
  const max = Math.max(1, ...Object.values(series));
  return (
    <svg
      width="100%"
      height={20}
      viewBox={`0 0 ${YEARS.length} 20`}
      preserveAspectRatio="none"
      className="block w-full"
      role="img"
      aria-label={`activity per year ${X0}–${X1}`}
    >
      {YEARS.map((y, i) => {
        const n = series[String(y)] ?? 0;
        if (!n) return null;
        const h = Math.max(1, (n / max) * 19);
        return (
          <rect key={y} x={i + 0.1} y={20 - h} width={0.8} height={h} className="fill-accent/70">
            <title>{`${y}: ${n.toLocaleString("en-US")}`}</title>
          </rect>
        );
      })}
    </svg>
  );
}

interface DeepTir {
  cpc: string;
  title: string;
  tir_pct: number | null;
  cycle_time_years: number | null;
  computed_in_s: number;
  error?: string;
}

export default function TechQuery() {
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);
  const [res, setRes] = useState<QueryResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [deep, setDeep] = useState<DeepTir | null>(null);
  const [deepLoading, setDeepLoading] = useState(false);

  async function runDeep(cpc: string) {
    if (deepLoading) return;
    setDeepLoading(true);
    setDeep(null);
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 115_000);
    try {
      const r = await fetch(`/api/foresight/tir?cpc=${encodeURIComponent(cpc)}`, {
        signal: ctrl.signal,
      });
      const data = (await r.json()) as DeepTir;
      setDeep(r.ok && !data.error ? data : { ...data, error: data.error || "failed" });
    } catch (e) {
      setDeep({
        cpc,
        title: "",
        tir_pct: null,
        cycle_time_years: null,
        computed_in_s: 0,
        error: e instanceof DOMException && e.name === "AbortError" ? "timed out" : "failed",
      });
    } finally {
      clearTimeout(timer);
      setDeepLoading(false);
    }
  }

  async function run(phrase: string) {
    const query = phrase.trim();
    if (query.length < 4 || loading) return;
    setLoading(true);
    setErr(null);
    setRes(null);
    setDeep(null);
    // never leave the button stuck on "Analyzing…" if the GPU handover stalls
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 115_000);
    try {
      const r = await fetch(
        `/api/foresight/query?q=${encodeURIComponent(query)}&threshold=0.45`,
        { signal: ctrl.signal }
      );
      const data = (await r.json()) as QueryResult;
      if (!r.ok || data.error) setErr(data.error || "query failed");
      else setRes(data);
    } catch (e) {
      setErr(
        e instanceof DOMException && e.name === "AbortError"
          ? "timed out — try a narrower phrase"
          : "network error"
      );
    } finally {
      clearTimeout(timer);
      setLoading(false);
    }
  }

  return (
    <section className="border border-accent/40 bg-accent/5 p-5 sm:p-6">
      <div className="flex items-center gap-3 mb-3">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent">
          —— Ask the engine
        </div>
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-paper bg-accent/25 border border-accent/50 px-2 py-0.5">
          Super Pro+
        </span>
      </div>
      <h2 className="font-display text-2xl text-paper mb-1">Any technology, on demand</h2>
      <p className="font-sans text-sm text-text mb-4 max-w-2xl">
        Type a specific technology and we compute its improvement rate and how far
        research led the market — live, over 20M signals. Not a keyword search: the
        phrase is matched semantically across every tier.
      </p>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          run(q);
        }}
        className="flex flex-col sm:flex-row gap-2"
      >
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="e.g. recombinant food protein for cheesemaking"
          maxLength={200}
          className="flex-1 min-w-0 bg-card border border-border px-3 py-2 font-sans text-sm text-paper placeholder:text-muted focus:outline-none focus:border-accent"
        />
        <button
          type="submit"
          disabled={loading || q.trim().length < 4}
          className="font-mono text-xs uppercase tracking-[0.14em] px-4 py-2 border border-accent text-accent hover:bg-accent hover:text-card disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-accent transition-colors shrink-0"
        >
          {loading ? "Analyzing…" : "Analyze"}
        </button>
      </form>

      <div className="mt-2 flex flex-wrap gap-1.5">
        {EXAMPLES.map((ex) => (
          <button
            key={ex}
            onClick={() => {
              setQ(ex);
              run(ex);
            }}
            disabled={loading}
            className="font-mono text-[10px] text-muted border border-border px-2 py-1 hover:text-accent hover:border-accent/50 disabled:opacity-40"
          >
            {ex}
          </button>
        ))}
      </div>

      {loading && (
        <p className="mt-5 font-mono text-xs text-muted animate-pulse">
          Embedding your phrase and projecting it across the maturity chain… (~10–30s)
        </p>
      )}
      {err && <p className="mt-5 font-mono text-xs text-serious">⚠ {err}</p>}

      {res && !loading && (
        <div className="mt-6 flex flex-col gap-5">
          {/* headline findings */}
          <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
            {(res.tir_pct != null || deep?.tir_pct != null) && (
              <div>
                <span className="font-display text-3xl text-paper">
                  ≈{deep?.tir_pct ?? res.tir_pct}%
                </span>
                <span className="font-mono text-[11px] text-muted">
                  /yr improvement{" "}
                  {deep?.tir_pct != null ? (
                    <span className="text-accent">(measured · {deep.title.split(";")[0].toLowerCase()})</span>
                  ) : (
                    <>
                      (predicted)
                      {!res.tir_is_nearest && res.tir_via ? ` · via ${res.tir_via}` : ""}
                    </>
                  )}
                </span>
              </div>
            )}
            {res.lead_science_market != null && (
              <div>
                <span className="font-display text-3xl text-paper">{res.lead_science_market}+</span>
                <span className="font-mono text-[11px] text-muted"> yrs research led the market</span>
              </div>
            )}
            {res.cycle_time_years != null && (
              <div>
                <span className="font-display text-3xl text-paper">{res.cycle_time_years}</span>
                <span className="font-mono text-[11px] text-muted"> yr innovation cycle</span>
              </div>
            )}
          </div>

          {/* deep analysis: compute the real TIR for the ACTUAL nearest class */}
          {res.nearest_cpcs.length > 0 && !deep && (
            <div className="flex items-center gap-3 flex-wrap">
              <button
                onClick={() => runDeep(res.nearest_cpcs[0].symbol)}
                disabled={deepLoading}
                className="font-mono text-[11px] uppercase tracking-[0.12em] px-3 py-1.5 border border-accent/60 text-accent hover:bg-accent hover:text-card disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-accent transition-colors"
              >
                {deepLoading ? "Computing on the graph…" : "▸ Deep analysis"}
              </button>
              <span className="font-mono text-[10px] text-muted">
                {deepLoading
                  ? "measuring TIR for the exact nearest class (~1 min)"
                  : `refine the predicted rate to the measured value for ${res.nearest_cpcs[0].symbol}`}
              </span>
            </div>
          )}
          {deep?.error && (
            <p className="font-mono text-[11px] text-serious">⚠ deep analysis {deep.error}</p>
          )}
          {deep?.tir_pct != null && (
            <p className="font-mono text-[10px] text-muted">
              measured on the citation graph in {deep.computed_in_s}s ·
              {res.tir_pct != null
                ? ` proxy was ≈${res.tir_pct}% (Δ ${Math.abs(deep.tir_pct - res.tir_pct).toFixed(1)}pp)`
                : " no proxy was available"}
            </p>
          )}

          {/* nearest technology classes */}
          <div className="flex flex-wrap gap-1.5">
            <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
              nearest classes
            </span>
            {res.nearest_cpcs.slice(0, 3).map((c) => (
              <span
                key={c.symbol}
                className="font-mono text-[10px] text-text border border-border px-1.5 py-0.5 max-w-[220px] truncate"
                title={`${c.symbol} — ${c.title}${c.tir_pct ? ` · TIR ${c.tir_pct}%/yr` : ""}`}
              >
                {c.curated || c.symbol}
                {c.tir_pct ? ` · ${c.tir_pct}%/yr` : ""}
              </span>
            ))}
          </div>

          {/* tier timelines */}
          <div className="flex flex-col gap-1.5">
            {(["science", "patent", "funding", "market"] as const).map((tier) => {
              const t = res.tiers[tier];
              const has = t && Object.keys(t.series).length > 0;
              return (
                <div key={tier} className="flex items-center gap-2 sm:gap-3">
                  <span className="font-mono text-[9px] sm:text-[10px] uppercase tracking-[0.1em] text-muted w-14 sm:w-16 shrink-0">
                    {TIER_LABEL[tier]}
                  </span>
                  <div className="flex-1 min-w-0">
                    {has ? (
                      <Spark series={t.series} />
                    ) : (
                      <span className="font-mono text-[9px] text-muted italic h-[20px] flex items-center">
                        no clear signal
                      </span>
                    )}
                  </div>
                  <span className="font-mono text-[10px] text-text tabular-nums shrink-0 w-24 text-right">
                    {t && t.n > 0
                      ? `${t.n.toLocaleString("en-US")}${t.takeoff ? ` · from ${t.takeoff}` : ""}`
                      : "—"}
                  </span>
                </div>
              );
            })}
            <div className="flex items-center gap-2 sm:gap-3">
              <span className="w-14 sm:w-16 shrink-0" />
              <div className="flex-1 min-w-0 flex justify-between font-mono text-[9px] text-muted">
                <span>{X0}</span>
                <span>{X1}</span>
              </div>
              <span className="w-24 shrink-0" />
            </div>
          </div>

          <p className="font-mono text-[10px] text-muted">
            Ramp takeoff = first year at ≥15% of peak · science sits at the 1990 window floor, so
            lead time is a lower bound (“N+”). Evidence is the underlying signals per tier.
          </p>
        </div>
      )}
    </section>
  );
}
