/**
 * URL search-param <-> `TrendsFilterOptions` bridge.
 *
 * All filter state lives in the URL (no client-side store), so every filter
 * control is a link that mutates one param. This helper parses the incoming
 * params on the server and provides a stable `toggleValue` API for the client
 * components to emit new query strings.
 */
import type {
  TrendsFilterOptions,
  TrendsSortBy,
  TrendsDateRange,
  TrendsViewMode,
} from "./db";
import type {
  PestelDimension,
  TrendSignalType,
  Vertical,
} from "./types";

// ─────────────────────────────────────────────────────────────────────────────
// Whitelists (also used by UI components for rendering)
// ─────────────────────────────────────────────────────────────────────────────

export const VALID_VERTICALS: Vertical[] = [
  "FOOD",
  "TECH",
  "HEALTH",
  "ECO",
  "DESIGN",
  "FASHION",
  "BIZ",
  "LIFESTYLE",
];

export const VALID_PESTEL: PestelDimension[] = ["P", "E", "S", "T", "En", "L"];

export const VALID_SIGNAL_TYPES: TrendSignalType[] = [
  "product_launch",
  "research",
  "market_shift",
  "consumer_behavior",
  "regulation",
  "funding",
  "partnership",
  "patent",
];

export const VALID_SORT_BY: TrendsSortBy[] = [
  "date_desc",
  "date_asc",
  "score_desc",
  "engagement_desc",
  "source_date_desc",
];

export const VALID_DATE_RANGE: TrendsDateRange[] = ["1d", "7d", "30d", "all"];

export const VALID_VIEW_MODE: TrendsViewMode[] = ["grid", "list"];

// Human-readable labels for sort options (used in SortSelect)
export const SORT_LABELS: Record<TrendsSortBy, string> = {
  date_desc: "Newest first",
  date_asc: "Oldest first",
  score_desc: "Signal strength",
  engagement_desc: "Most read",
  source_date_desc: "Source date",
};

export const SIGNAL_TYPE_LABELS: Record<TrendSignalType, string> = {
  product_launch: "Product launch",
  research: "Research",
  market_shift: "Market shift",
  consumer_behavior: "Consumer behavior",
  regulation: "Regulation",
  funding: "Funding",
  partnership: "Partnership",
  patent: "Patent",
};

export const DATE_RANGE_LABELS: Record<TrendsDateRange, string> = {
  "1d": "24h",
  "7d": "7d",
  "30d": "30d",
  all: "All",
};

// ─────────────────────────────────────────────────────────────────────────────
// Param names (single source of truth — keep short for pretty URLs)
// ─────────────────────────────────────────────────────────────────────────────

export const PARAM = {
  verticals: "v",
  pestel: "pestel",
  signal: "signal",
  mega: "mega",
  excludeSources: "exclude",
  minScore: "min_score",
  dateRange: "range",
  search: "q",
  sort: "sort",
  view: "view",
  page: "page",
} as const;

// ─────────────────────────────────────────────────────────────────────────────
// Parse: URLSearchParams -> structured filter state
// ─────────────────────────────────────────────────────────────────────────────

type RawParams = Record<string, string | string[] | undefined>;

function getParam(raw: RawParams, key: string): string | undefined {
  const v = raw[key];
  if (Array.isArray(v)) return v[0];
  return v;
}

function splitList(v: string | undefined): string[] {
  if (!v) return [];
  return v
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function filterWhitelist<T extends string>(
  values: string[],
  whitelist: readonly T[]
): T[] {
  return values.filter((x): x is T => (whitelist as readonly string[]).includes(x));
}

export interface ParsedFilters extends TrendsFilterOptions {
  /** View mode is a UI-layer concern (grid/list); DB doesn't care. */
  view: TrendsViewMode;
  /** Page is 1-based for the UI; converted to `offset` at query time. */
  page: number;
}

export const PAGE_SIZE = 12;
export const LIST_PAGE_SIZE = 30;

export function parseFilterParams(raw: RawParams): ParsedFilters {
  const verticals = filterWhitelist(
    splitList(getParam(raw, PARAM.verticals)),
    VALID_VERTICALS
  );
  const pestel = filterWhitelist(
    splitList(getParam(raw, PARAM.pestel)),
    VALID_PESTEL
  );
  const signalTypes = filterWhitelist(
    splitList(getParam(raw, PARAM.signal)),
    VALID_SIGNAL_TYPES
  );

  const excludeSources = splitList(getParam(raw, PARAM.excludeSources));

  const megaRaw = getParam(raw, PARAM.mega);
  const mega_trend = megaRaw && megaRaw.length > 0 ? megaRaw : undefined;

  const minScoreRaw = getParam(raw, PARAM.minScore);
  const minScore = minScoreRaw ? Math.max(0, Math.min(100, parseInt(minScoreRaw, 10))) : 0;

  const dateRangeRaw = getParam(raw, PARAM.dateRange);
  const date_range: TrendsDateRange = (VALID_DATE_RANGE as readonly string[]).includes(
    dateRangeRaw || ""
  )
    ? (dateRangeRaw as TrendsDateRange)
    : "all";

  const search = (getParam(raw, PARAM.search) || "").trim() || undefined;

  const sortRaw = getParam(raw, PARAM.sort);
  const sort_by: TrendsSortBy = (VALID_SORT_BY as readonly string[]).includes(
    sortRaw || ""
  )
    ? (sortRaw as TrendsSortBy)
    : "date_desc";

  const viewRaw = getParam(raw, PARAM.view);
  const view: TrendsViewMode = (VALID_VIEW_MODE as readonly string[]).includes(
    viewRaw || ""
  )
    ? (viewRaw as TrendsViewMode)
    : "grid";

  const pageRaw = getParam(raw, PARAM.page);
  const page = Math.max(1, parseInt(pageRaw || "1", 10) || 1);

  const perPage = view === "list" ? LIST_PAGE_SIZE : PAGE_SIZE;

  return {
    status: "published",
    verticals: verticals.length > 0 ? verticals : undefined,
    pestel: pestel.length > 0 ? pestel : undefined,
    signal_types: signalTypes.length > 0 ? signalTypes : undefined,
    mega_trend,
    exclude_sources: excludeSources.length > 0 ? excludeSources : undefined,
    min_trend_score: minScore > 0 ? minScore : undefined,
    date_range,
    search,
    sort_by,
    view,
    page,
    limit: perPage,
    offset: (page - 1) * perPage,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Build: mutate one param + serialize back to a URL query string
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Build a new query string from an existing `URLSearchParams` by applying a
 * set of mutations. Drops `page` whenever any filter param changes (otherwise
 * the user lands on an empty paginated view). Deletes keys with empty values.
 */
export function buildQueryString(
  current: URLSearchParams,
  mutations: Record<string, string | null>,
  { resetPage = true }: { resetPage?: boolean } = {}
): string {
  const next = new URLSearchParams(current.toString());

  for (const [key, value] of Object.entries(mutations)) {
    if (value === null || value === "") {
      next.delete(key);
    } else {
      next.set(key, value);
    }
  }

  if (resetPage) {
    next.delete(PARAM.page);
  }

  const s = next.toString();
  return s ? `?${s}` : "";
}

/**
 * Toggle a single value in/out of a comma-separated list param.
 * Returns the new value-string (not the full query-string).
 */
export function toggleListValue(current: string | null, value: string): string | null {
  const list = splitList(current || "");
  const i = list.indexOf(value);
  if (i >= 0) list.splice(i, 1);
  else list.push(value);
  return list.length > 0 ? list.join(",") : null;
}

/**
 * Count active filters (excluding pagination, view mode, sort order).
 * Used by FilterBar to show "3 filters active" / enable "Clear all".
 */
export function countActiveFilters(f: ParsedFilters): number {
  let n = 0;
  if (f.verticals?.length) n += f.verticals.length;
  if (f.pestel?.length) n += f.pestel.length;
  if (f.signal_types?.length) n += f.signal_types.length;
  if (f.mega_trend) n += 1;
  if (f.exclude_sources?.length) n += f.exclude_sources.length;
  if (f.min_trend_score && f.min_trend_score > 0) n += 1;
  if (f.date_range && f.date_range !== "all") n += 1;
  if (f.search && f.search.length > 0) n += 1;
  return n;
}

/**
 * List of removable filter chips. Each entry carries the param key + display
 * label + the mutation needed to remove it. FilterBar renders these.
 */
export interface ActiveChip {
  key: string;
  label: string;
  /** Mutation to pass into `buildQueryString` to remove this chip. */
  mutation: Record<string, string | null>;
}

export function getActiveChips(f: ParsedFilters): ActiveChip[] {
  const chips: ActiveChip[] = [];

  if (f.search) {
    chips.push({
      key: `q:${f.search}`,
      label: `"${f.search}"`,
      mutation: { [PARAM.search]: null },
    });
  }

  if (f.date_range && f.date_range !== "all") {
    chips.push({
      key: `range:${f.date_range}`,
      label: DATE_RANGE_LABELS[f.date_range],
      mutation: { [PARAM.dateRange]: null },
    });
  }

  for (const v of f.verticals ?? []) {
    chips.push({
      key: `v:${v}`,
      label: v,
      mutation: {
        [PARAM.verticals]: toggleListValue((f.verticals ?? []).join(","), v),
      },
    });
  }

  for (const p of f.pestel ?? []) {
    chips.push({
      key: `pestel:${p}`,
      label: `PESTEL ${p}`,
      mutation: {
        [PARAM.pestel]: toggleListValue((f.pestel ?? []).join(","), p),
      },
    });
  }

  for (const s of f.signal_types ?? []) {
    chips.push({
      key: `signal:${s}`,
      label: SIGNAL_TYPE_LABELS[s] ?? s,
      mutation: {
        [PARAM.signal]: toggleListValue((f.signal_types ?? []).join(","), s),
      },
    });
  }

  if (f.mega_trend) {
    chips.push({
      key: `mega:${f.mega_trend}`,
      label: `Mega · ${f.mega_trend.replace(/_/g, " ")}`,
      mutation: { [PARAM.mega]: null },
    });
  }

  for (const src of f.exclude_sources ?? []) {
    chips.push({
      key: `exclude:${src}`,
      label: `−${src}`,
      mutation: {
        [PARAM.excludeSources]: toggleListValue(
          (f.exclude_sources ?? []).join(","),
          src
        ),
      },
    });
  }

  if (f.min_trend_score && f.min_trend_score > 0) {
    chips.push({
      key: `min_score:${f.min_trend_score}`,
      label: `score ≥ ${f.min_trend_score}`,
      mutation: { [PARAM.minScore]: null },
    });
  }

  return chips;
}

/**
 * Mutation object that wipes every filter (but preserves view/sort).
 */
export const CLEAR_ALL_MUTATION: Record<string, string | null> = {
  [PARAM.verticals]: null,
  [PARAM.pestel]: null,
  [PARAM.signal]: null,
  [PARAM.mega]: null,
  [PARAM.excludeSources]: null,
  [PARAM.minScore]: null,
  [PARAM.dateRange]: null,
  [PARAM.search]: null,
};
