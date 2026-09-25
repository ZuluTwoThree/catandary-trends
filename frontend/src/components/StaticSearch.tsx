"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  PESTEL,
  VERTICALS,
  type PestelDimension,
  type TrendSignalType,
  type Vertical,
} from "@/lib/types";
import { SIGNAL_TYPE_LABELS } from "@/lib/filter-params";
import {
  EMPTY_FILTERS,
  INDEX_PATH,
  MAX_RESULTS,
  buildSearchHash,
  entryToTrend,
  isActive,
  megaOptions,
  parseSearchHash,
  prepareIndex,
  search,
  toggleValue,
  type IndexEntry,
  type MegaOption,
  type PreparedEntry,
  type SearchFilters,
  type SearchResult,
  SIGNAL_TYPE_ORDER,
} from "@/lib/staticSearch";
import TrendCard from "./TrendCard";

/**
 * Search + filter of the STATIC export (design Schritt 5 / D). Rendered only
 * when `isStaticExport()` (components/StaticFeed.tsx) — the workstation feed
 * keeps its server-side `?q=` search and never mounts this.
 *
 * Three pieces share one context:
 *   <StaticSearchProvider vertical>  state, lazy index load, URL hash
 *   <StaticSearch />                 input + chips (Vertical / PESTEL / Theme),
 *                                    lives in StaticFilterBar's children slot
 *   <StaticSearchScope>              the listing's body; swapped for the hit
 *                                    grid while a search is active
 *
 * The index (/trends/index.json, lib/staticSearch.ts) is fetched once, on
 * the first focus/click, and kept across client navigations. Server and
 * first client render are identical (defaults, idle) — the URL hash is read
 * in an effect, so hydration never mismatches. Hash writes are imperative
 * (in the updater, not an effect) so a hash present at load is never
 * clobbered by the initial render.
 */

type Status = "idle" | "loading" | "ready" | "error";

interface SearchContext {
  defaults: SearchFilters;
  filters: SearchFilters;
  update: (next: SearchFilters) => void;
  reset: () => void;
  status: Status;
  ensureLoaded: () => void;
  indexed: number;
  themes: MegaOption[];
  active: boolean;
  result: SearchResult | null;
}

const Ctx = createContext<SearchContext | null>(null);

function useSearch(): SearchContext {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("StaticSearch must be rendered inside StaticSearchProvider");
  return ctx;
}

export function StaticSearchProvider({
  vertical,
  children,
}: {
  /** The page's vertical (/trends/v/<v>) — its chip is the default. */
  vertical: Vertical | null;
  children: ReactNode;
}) {
  const defaults = useMemo<SearchFilters>(
    () => ({ ...EMPTY_FILTERS, verticals: vertical ? [vertical] : [] }),
    [vertical]
  );
  const [filters, setFilters] = useState<SearchFilters>(defaults);
  const [status, setStatus] = useState<Status>("idle");
  const [prepared, setPrepared] = useState<PreparedEntry[]>([]);
  const [themes, setThemes] = useState<MegaOption[]>([]);
  const loading = useRef(false);

  const ensureLoaded = useCallback(() => {
    if (loading.current) return;
    loading.current = true;
    setStatus("loading");
    fetch(INDEX_PATH, { headers: { accept: "application/json" } })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data: unknown) => {
        if (!Array.isArray(data)) throw new Error("index is not an array");
        const entries = data as IndexEntry[];
        setPrepared(prepareIndex(entries));
        setThemes(megaOptions(entries));
        setStatus("ready");
      })
      .catch((err: unknown) => {
        loading.current = false;
        setStatus("error");
        console.error("search index failed to load:", err);
      });
  }, []);

  const writeHash = useCallback(
    (next: SearchFilters) => {
      if (typeof window === "undefined") return;
      const hash = isActive(next, defaults) ? buildSearchHash(next) : "";
      if (hash === window.location.hash) return;
      const { pathname, search: qs } = window.location;
      window.history.replaceState(window.history.state, "", `${pathname}${qs}${hash}`);
    },
    [defaults]
  );

  const update = useCallback(
    (next: SearchFilters) => {
      setFilters(next);
      writeHash(next);
      if (isActive(next, defaults)) ensureLoaded();
    },
    [defaults, ensureLoaded, writeHash]
  );

  const reset = useCallback(() => update(defaults), [defaults, update]);

  // URL hash -> state: on mount, on a client navigation to another listing
  // page (new defaults) and on manual hash edits / back-forward.
  useEffect(() => {
    const apply = () => {
      const parsed = parseSearchHash(window.location.hash);
      setFilters(parsed ?? defaults);
      if (parsed) ensureLoaded();
    };
    apply();
    window.addEventListener("hashchange", apply);
    return () => window.removeEventListener("hashchange", apply);
  }, [defaults, ensureLoaded]);

  const active = isActive(filters, defaults);
  const result = useMemo(
    () => (active && status === "ready" ? search(prepared, filters) : null),
    [active, status, prepared, filters]
  );

  const value = useMemo<SearchContext>(
    () => ({
      defaults,
      filters,
      update,
      reset,
      status,
      ensureLoaded,
      indexed: prepared.length,
      themes,
      active,
      result,
    }),
    [defaults, filters, update, reset, status, ensureLoaded, prepared.length, themes, active, result]
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

const GROUP_LABEL =
  "font-mono text-[9px] uppercase tracking-[0.22em] text-muted px-3 flex items-center border-r border-border whitespace-nowrap select-none";
const CHIP =
  "font-mono text-[10px] uppercase tracking-[0.1em] px-3 py-2 flex items-center gap-2 transition-colors";
const CHIP_IDLE = "text-muted hover:text-paper hover:bg-white/[0.02]";
const THEME_COLLAPSED = 8;

/** Input + chips. Mounted in StaticFilterBar's children slot. */
export default function StaticSearch() {
  const { filters, update, reset, status, ensureLoaded, indexed, themes, active, result } =
    useSearch();
  const inputId = useId();
  const [themesOpen, setThemesOpen] = useState(false);

  const setQuery = (q: string) => update({ ...filters, q });
  const toggleVertical = (v: Vertical) =>
    update({ ...filters, verticals: toggleValue(filters.verticals, v) });
  const togglePestel = (p: PestelDimension) =>
    update({ ...filters, pestel: toggleValue(filters.pestel, p) });
  const toggleMega = (key: string) => update({ ...filters, mega: toggleValue(filters.mega, key) });
  const toggleSignal = (t: TrendSignalType) =>
    update({ ...filters, signal: toggleValue(filters.signal, t) });

  const visibleThemes = themesOpen ? themes : themes.slice(0, THEME_COLLAPSED);

  let statusText: ReactNode;
  if (status === "error") {
    statusText = (
      <span>
        Search index unavailable.{" "}
        <button
          type="button"
          onClick={ensureLoaded}
          className="underline underline-offset-2 hover:text-accent"
        >
          Retry
        </button>
      </span>
    );
  } else if (status === "loading") {
    statusText = <span>Loading the search index…</span>;
  } else if (status === "ready" && active && result) {
    statusText = (
      <span>
        <span className="text-accent tabular-nums">{result.total.toLocaleString("en-US")}</span>{" "}
        {result.total === 1 ? "match" : "matches"}
      </span>
    );
  } else if (status === "ready") {
    statusText = (
      <span>
        <span className="text-paper tabular-nums">{indexed.toLocaleString("en-US")}</span> signals
        indexed — type or pick a chip
      </span>
    );
  } else {
    statusText = <span>Search titles and summaries — the index loads on first use</span>;
  }

  return (
    <div
      data-testid="static-search"
      className="space-y-3"
      aria-busy={status === "loading" || undefined}
    >
      <div
        role="search"
        className="flex items-stretch border border-border bg-background/40 focus-within:border-accent/70 transition-colors"
      >
        <label htmlFor={inputId} className={`${GROUP_LABEL} text-accent`}>
          Search
        </label>
        <input
          id={inputId}
          type="search"
          value={filters.q}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={ensureLoaded}
          onKeyDown={(e) => {
            if (e.key === "Escape" && filters.q) {
              e.preventDefault();
              setQuery("");
            }
          }}
          placeholder="Search titles and summaries…"
          autoComplete="off"
          spellCheck={false}
          maxLength={200}
          className="flex-1 bg-transparent font-mono text-[11px] text-paper placeholder:text-muted px-3 py-2 min-w-0"
        />
        {filters.q && (
          <button
            type="button"
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => setQuery("")}
            className="px-3 font-mono text-[10px] text-muted hover:text-accent transition-colors border-l border-border"
            aria-label="Clear search"
          >
            ×
          </button>
        )}
      </div>

      <div className="flex flex-wrap gap-3 items-stretch">
        <div role="group" aria-label="Vertical" className="flex flex-wrap items-stretch border border-border">
          <span className={GROUP_LABEL}>Vertical</span>
          {VERTICALS.map((v, idx) => {
            const on = filters.verticals.includes(v.id);
            const last = idx === VERTICALS.length - 1;
            return (
              <button
                key={v.id}
                type="button"
                onClick={() => toggleVertical(v.id)}
                aria-pressed={on}
                title={v.label}
                className={`${CHIP} ${!last ? "border-r border-border" : ""} ${
                  on ? "bg-white/[0.04]" : CHIP_IDLE
                }`}
                style={on ? { color: v.color } : undefined}
              >
                <span
                  className="inline-block w-[8px] h-[3px]"
                  style={{ backgroundColor: v.color, opacity: on ? 1 : 0.5 }}
                  aria-hidden="true"
                />
                <span>{v.code}</span>
              </button>
            );
          })}
        </div>

        <div role="group" aria-label="PESTEL" className="flex items-stretch border border-border">
          <span className={GROUP_LABEL}>PESTEL</span>
          {PESTEL.map((p, i) => {
            const on = filters.pestel.includes(p.id);
            const last = i === PESTEL.length - 1;
            return (
              <button
                key={p.id}
                type="button"
                onClick={() => togglePestel(p.id)}
                aria-pressed={on}
                aria-label={`Toggle ${p.label}`}
                title={p.label}
                className={`font-mono text-[12px] font-semibold px-3 py-2 transition-colors min-w-[40px] ${
                  !last ? "border-r border-border" : ""
                } ${on ? "bg-white/[0.05]" : "hover:bg-white/[0.02]"}`}
                style={{ color: on ? p.color : "var(--color-muted)" }}
              >
                {p.id}
              </button>
            );
          })}
        </div>

        <div role="group" aria-label="Signal type" className="flex flex-wrap items-stretch border border-border">
          <span className={GROUP_LABEL}>Signal</span>
          {SIGNAL_TYPE_ORDER.map((t, i) => {
            const on = filters.signal.includes(t);
            const last = i === SIGNAL_TYPE_ORDER.length - 1;
            return (
              <button
                key={t}
                type="button"
                onClick={() => toggleSignal(t)}
                aria-pressed={on}
                title={SIGNAL_TYPE_LABELS[t]}
                className={`${CHIP} ${!last ? "border-r border-border" : ""} ${
                  on ? "bg-white/[0.04] text-accent" : CHIP_IDLE
                }`}
              >
                <span>{SIGNAL_TYPE_LABELS[t]}</span>
              </button>
            );
          })}
        </div>
      </div>

      <div role="group" aria-label="Theme" className="border border-border p-3">
        <div className="flex items-center justify-between gap-3 mb-2">
          <span className="font-mono text-[9px] uppercase tracking-[0.22em] text-muted">
            Theme
          </span>
          {status === "ready" && themes.length > THEME_COLLAPSED && (
            <button
              type="button"
              onClick={() => setThemesOpen((o) => !o)}
              aria-expanded={themesOpen}
              className="font-mono text-[9px] uppercase tracking-[0.18em] text-muted hover:text-accent transition-colors"
            >
              {themesOpen ? "Collapse ↑" : `+${themes.length - THEME_COLLAPSED} more ↓`}
            </button>
          )}
          {status === "idle" && (
            <button
              type="button"
              onClick={ensureLoaded}
              className="font-mono text-[9px] uppercase tracking-[0.18em] text-muted hover:text-accent transition-colors"
            >
              Load themes ↓
            </button>
          )}
        </div>
        {status === "ready" ? (
          <div className="flex flex-wrap gap-1.5">
            {visibleThemes.map((m) => {
              const on = filters.mega.includes(m.key);
              return (
                <button
                  key={m.key}
                  type="button"
                  onClick={() => toggleMega(m.key)}
                  aria-pressed={on}
                  className={`font-mono text-[10px] uppercase tracking-[0.08em] px-2.5 py-1.5 border transition-colors inline-flex items-center gap-2 ${
                    on
                      ? "border-accent text-accent bg-accent/5"
                      : "border-border text-muted hover:text-paper hover:border-rule"
                  }`}
                >
                  <span className="truncate max-w-[22ch]">{m.name}</span>
                  <span className="text-[9px] opacity-60 tabular-nums">{m.count}</span>
                </button>
              );
            })}
          </div>
        ) : (
          <p className="font-mono text-[10px] text-muted/70">
            {status === "loading"
              ? "Loading…"
              : status === "error"
                ? "Unavailable until the index loads."
                : "Themes come with the search index."}
          </p>
        )}
      </div>

      <div
        className="flex flex-wrap items-center justify-between gap-3 font-mono text-[10px] uppercase tracking-[0.18em] text-muted"
        aria-live="polite"
      >
        {statusText}
        {active && (
          <button
            type="button"
            onClick={reset}
            className="text-muted hover:text-accent transition-colors"
          >
            Reset filters ×
          </button>
        )}
      </div>
    </div>
  );
}

/** The listing body — replaced by the hit grid while a search is active. */
export function StaticSearchScope({ children }: { children: ReactNode }) {
  const { active, status, result, reset } = useSearch();
  if (!active || status !== "ready" || !result) return <>{children}</>;

  const { total, hits } = result;
  return (
    <div data-testid="static-search-results">
      <div className="mb-6 flex items-baseline justify-between">
        <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted">
          <span className="text-accent tabular-nums">{total.toLocaleString("en-US")}</span>
          <span className="text-muted/70">
            {" "}
            / {total === 1 ? "Match" : "Matches"}
            {total > MAX_RESULTS ? ` · first ${MAX_RESULTS}` : ""}
          </span>
        </div>
        <button
          type="button"
          onClick={reset}
          className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted hover:text-accent transition-colors"
        >
          Back to the feed ×
        </button>
      </div>

      <h2 className="sr-only">Search results</h2>
      {total === 0 ? (
        <div className="border border-border border-dashed px-8 py-16 text-center">
          <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted mb-4">
            —— 0 results
          </div>
          <h3 className="font-display text-[32px] leading-[1.1] text-paper">
            Nothing in the window matches <span className="italic">that</span>.
          </h3>
          <p className="mt-4 text-[13px] text-muted">
            Try fewer terms, or drop a chip.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {hits.map((entry) => (
            <TrendCard key={entry.slug} trend={entryToTrend(entry)} />
          ))}
        </div>
      )}

      {total > MAX_RESULTS && (
        <p className="mt-8 pt-6 border-t border-border font-mono text-[10px] uppercase tracking-[0.18em] text-muted text-center">
          Showing the {MAX_RESULTS} most relevant of {total.toLocaleString("en-US")} — add a term
          or a chip to narrow down.
        </p>
      )}
    </div>
  );
}
