/**
 * URL search-param bridge for the horizon radar.
 *
 * Mirrors lib/filter-params.ts and its rule: "All filter state lives in the URL
 * (no client-side store)". The two existing search tools break that rule —
 * their results die on reload and cannot be shared (issue KEY-04) — and this
 * one deliberately does not repeat it.
 */

export const RADAR_JURISDICTIONS = ["US", "EU", "UK", "IL", "APAC", "GLOBAL"] as const;
export type RadarJurisdiction = (typeof RADAR_JURISDICTIONS)[number];

export const RADAR_DIMENSION_SETS = ["strategic", "pestel"] as const;
export type RadarDimensionSet = (typeof RADAR_DIMENSION_SETS)[number];

/** Upper bound on selectable sub-fields — the arc's row packing is tested to 3 rows/band. */
export const MAX_FIELDS = 12;

export const Q_MIN = 3;
export const Q_MAX = 120;

export interface RadarParams {
  /** Free-text query. Its presence switches the page into query mode. */
  q: string | null;
  /** Saved radar slug. Mutually exclusive with `q`; `q` wins. */
  radar: string | null;
  /** Selected sub-field slugs. */
  fields: string[];
  /** Drill-down target. */
  field: string | null;
  region: RadarJurisdiction | null;
  dim: RadarDimensionSet;
  regulated: boolean;
}

type Raw = Record<string, string | string[] | undefined>;

const one = (v: string | string[] | undefined): string | null =>
  typeof v === "string" ? v : Array.isArray(v) ? (v[0] ?? null) : null;

const SLUG = /^[a-z0-9-]{1,40}$/;

export function parseRadarParams(raw: Raw): RadarParams {
  const rawQ = (one(raw.q) ?? "").trim().replace(/\s+/g, " ");
  const q = rawQ.length >= Q_MIN ? rawQ.slice(0, Q_MAX) : null;

  // `q` and `radar` cannot both be honoured — a query radar is not a saved one.
  const radar = q ? null : one(raw.radar);

  const fields = (one(raw.fields) ?? "")
    .split(",")
    .map((s) => s.trim().toLowerCase())
    .filter((s) => SLUG.test(s))
    .slice(0, MAX_FIELDS);

  const fieldRaw = (one(raw.field) ?? "").trim().toLowerCase();
  const field = SLUG.test(fieldRaw) ? fieldRaw : null;

  const regionRaw = (one(raw.region) ?? "").toUpperCase() as RadarJurisdiction;
  const region = RADAR_JURISDICTIONS.includes(regionRaw) ? regionRaw : null;

  const dimRaw = (one(raw.dim) ?? "") as RadarDimensionSet;
  const dim = RADAR_DIMENSION_SETS.includes(dimRaw) ? dimRaw : "strategic";

  return { q, radar, fields, field, region, dim, regulated: one(raw.regulated) === "1" };
}

/** Serialize back to a query string, omitting everything at its default. */
export function radarQueryString(p: Partial<RadarParams>): string {
  const sp = new URLSearchParams();
  if (p.q) sp.set("q", p.q);
  else if (p.radar) sp.set("radar", p.radar);
  if (p.fields?.length) sp.set("fields", p.fields.slice(0, MAX_FIELDS).join(","));
  if (p.field) sp.set("field", p.field);
  if (p.region) sp.set("region", p.region);
  if (p.dim && p.dim !== "strategic") sp.set("dim", p.dim);
  if (p.regulated) sp.set("regulated", "1");
  const s = sp.toString();
  return s ? `?${s}` : "";
}

/** Query string for the API route (a subset — `field`/`radar` are view-only). */
export function radarApiQuery(p: Pick<RadarParams, "q" | "fields" | "dim" | "regulated"> & {
  regions?: string[];
}): string {
  const sp = new URLSearchParams();
  sp.set("q", p.q ?? "");
  if (p.fields?.length) sp.set("fields", p.fields.join(","));
  if (p.dim !== "strategic") sp.set("dim", p.dim);
  if (p.regulated) sp.set("regulated", "1");
  if (p.regions?.length) sp.set("regions", p.regions.join(","));
  return sp.toString();
}
