/**
 * Client-safe half of the horizon radar: types, labels and the cell lookup.
 *
 * Split out of radar.ts because that module imports the `pg` pool — importing it
 * from a client component pulls node-only code into the browser bundle. The
 * server-side read functions stay in radar.ts and re-export from here, so there
 * is exactly one definition of every type and label.
 */

export type Horizon = "H1" | "H2" | "H3";

export const HORIZON_META: Record<
  Horizon,
  { label: string; action: string; blurb: string; color: string }
> = {
  H1: {
    label: "H1",
    action: "Act now",
    blurb: "In market, approved, established — decisions are due today.",
    color: "#d4ff3a",
  },
  H2: {
    label: "H2",
    action: "Build",
    blurb: "In transition: the path is open, first products exist.",
    color: "#60a5fa",
  },
  H3: {
    label: "H3",
    action: "Watch",
    blurb: "Research stage, no route to market yet — keep an option open.",
    color: "#a78bfa",
  },
};

/** Dimension labels, kept in the read layer so the API and UI cannot diverge. */
export const DIMENSION_META: Record<string, { label: string; blurb: string }> = {
  technology: {
    label: "Technology",
    blurb: "How far the technology itself has come, from the patent record.",
  },
  regulatory: {
    label: "Regulatory",
    blurb: "Whether an approval exists in this jurisdiction — per named authority.",
  },
  market: {
    label: "Market",
    blurb: "Whether products are actually on sale in this jurisdiction.",
  },
  adoption: {
    label: "Adoption",
    blurb: "Whether demand-side behaviour is showing up in the signals.",
  },
};

export interface FieldCheck {
  is_field: boolean;
  vertical_focus: number;
  vertical_focus2: number;
  patent_share: number;
  note: string | null;
}

export const ANY_REGION = "*";

/**
 * Anzeigename einer Jurisdiktion.
 *
 * "GLOBAL" bedeutet seit dem Kalibrierlauf 2026-08-02 nicht mehr "Signale, die
 * wir nicht verorten konnten" (das waren rund die Hälfte aller Signale und als
 * Spalte gelesen strategisch wertlos), sondern WELTWEIT: die Vereinigung aller
 * Signale des Felds. Die Spalte beantwortet damit "gibt es das irgendwo?" neben
 * "gibt es das hier?" — und das Label muss das sagen, sonst liest der Nutzer
 * weiter eine Region.
 */
export function regionLabel(r: string): string {
  return r === "GLOBAL" ? "Worldwide" : r;
}

export interface RadarCell {
  scope_slug: string;
  dimension: string;
  region: string;
  horizon: Horizon | null;
  effective: Horizon | null; // override wins over computed
  score: number | null;
  n_signals: number;
  method: string;
  rationale: string;
  evidence: number[];
  override_horizon: Horizon | null;
  override_note: string | null;
}

export interface RadarScope {
  slug: string;
  label: string;
}

export interface RadarConfigMeta {
  slug: string;
  name: string;
  description: string | null;
  regions: string[];
  regulated: boolean;
  /** 'curated' = seeded in radar_seed.py, 'query' = built from a free-text query. */
  kind?: "curated" | "query";
}

export interface RadarView {
  config: RadarConfigMeta;
  /** Set only on on-demand query radars (compute_query_radar) — never persisted. */
  origin?: { kind: "query"; query: string; field_signals?: Record<string, number> };
  /**
   * Nur bei On-Demand-Query-Radaren: misst, ob die Query überhaupt ein
   * Technologiefeld beschreibt. Ist `is_field` falsch, sind die Horizonte eine
   * Aussage über den Sprachgebrauch der Presse, nicht über Reife — der
   * Zufallszug 2026-08-02 zeigte "cost reduction" mit H1 in jeder Zelle.
   */
  field_check?: FieldCheck | null;
  /** Resolved evidence titles, shipped with query radars so the client never refetches. */
  evidence?: Record<
    number | string,
    { id: number; title: string; source_url: string | null; source_name: string | null }
  >;
  scopes: RadarScope[];
  dimensions: string[];
  regions: string[];
  cells: RadarCell[];
  generated: string | null;
  n_signals: number;
}

/**
 * Cell lookup for one region. Region-blind dimensions (technology) are stored
 * under '*' and served for every region — patent maturity is not jurisdictional,
 * and pretending otherwise would invent precision.
 */
export function cellFor(
  view: RadarView,
  scope: string,
  dimension: string,
  region: string
): RadarCell | null {
  return (
    view.cells.find(
      (c) =>
        c.scope_slug === scope && c.dimension === dimension && c.region === region
    ) ??
    view.cells.find(
      (c) =>
        c.scope_slug === scope &&
        c.dimension === dimension &&
        c.region === ANY_REGION
    ) ??
    null
  );
}


/** Horizon profile of one trend, inherited from its radar field. */
export interface TrendHorizonProfile {
  scope_slug: string;
  scope_label: string;
  radar_slug: string;
  cells: { dimension: string; horizon: Horizon }[];
}

/**
 * PESTEL dimension set. Same engine, different lens — the radar's dimensions are
 * configuration, so a PESTEL radar is not a second system but a second
 * `dimension_set`. Colours match PestelBadge / lib/types so a dimension keeps
 * one identity across the product.
 */
export const PESTEL_META: Record<
  string,
  { label: string; short: string; blurb: string; color: string }
> = {
  P: {
    label: "Political",
    short: "POL",
    blurb: "Policy weather: strategies and funding programmes versus headwind.",
    color: "#ef4444",
  },
  E: {
    label: "Economic",
    short: "ECO",
    blurb: "Commercial activity: funding rounds and product launches.",
    color: "#60a5fa",
  },
  S: {
    label: "Social",
    short: "SOC",
    blurb: "Demand side: is consumer behaviour showing up in the signals?",
    color: "#34d399",
  },
  T: {
    label: "Technological",
    short: "TEC",
    blurb: "How far the technology itself has come, from the patent record.",
    color: "#a78bfa",
  },
  En: {
    label: "Environmental",
    short: "ENV",
    blurb: "Visibility of the environmental argument — not a life-cycle assessment.",
    color: "#22d3ee",
  },
  L: {
    label: "Legal",
    short: "LEG",
    blurb: "Does an approval exist in this jurisdiction, per named authority?",
    color: "#f97316",
  },
};

/** Colour + short code for any dimension, PESTEL or strategic. */
export function dimensionStyle(d: string): {
  label: string;
  short: string;
  blurb: string;
  color: string;
} {
  if (PESTEL_META[d]) return PESTEL_META[d];
  const meta = DIMENSION_META[d];
  const fallback: Record<string, { short: string; color: string }> = {
    technology: { short: "TEC", color: "#a78bfa" },
    regulatory: { short: "REG", color: "#f97316" },
    market: { short: "MKT", color: "#60a5fa" },
    adoption: { short: "ADO", color: "#34d399" },
  };
  const f = fallback[d] ?? { short: d.slice(0, 3).toUpperCase(), color: "#8a8d82" };
  return {
    label: meta?.label ?? d,
    short: f.short,
    blurb: meta?.blurb ?? "",
    color: f.color,
  };
}
