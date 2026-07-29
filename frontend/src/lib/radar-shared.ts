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

export const ANY_REGION = "*";

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
}

export interface RadarView {
  config: RadarConfigMeta;
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
