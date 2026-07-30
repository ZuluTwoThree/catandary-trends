import { q, q1 } from "./pg";
import { ANY_REGION, type Horizon, type RadarCell, type RadarConfigMeta,
         type RadarScope, type RadarView,
         type TrendHorizonProfile } from "./radar-shared";

export * from "./radar-shared";

/**
 * Read access to the horizon radar (radar_configs / radar_scopes / radar_runs /
 * radar_cells, written by pipeline/radar_horizons.py).
 *
 * Batch layer computes, frontend reads — no classification in the request path.
 * Replaces the lead-time-tier radar, whose rings encoded a cluster's *source
 * mix* rather than the maturity of a technology (docs/radar_redesign_proposal.md
 * §1.1). Here a cell is a recommendation: H1 act · H2 build · H3 watch · null =
 * not enough evidence, and the cell says so instead of guessing.
 *
 * Degrades to null/[] when the tables do not exist yet.
 */

// Canonical display order, covering BOTH dimension sets. A radar declares its
// set in radar_configs.dimension_set; the read layer just keeps whichever
// dimensions the run actually produced, in this order. Omitting the PESTEL codes
// here silently emptied the PESTEL radar (2026-07-30).
const DIMENSION_ORDER = [
  // strategic
  "technology", "regulatory", "market", "adoption",
  // PESTEL, in the canonical P-E-S-T-E-L reading order
  "P", "E", "S", "T", "En", "L",
];

function parseJson<T>(v: unknown, fallback: T): T {
  if (v == null) return fallback;
  if (typeof v !== "string") return v as T;
  try {
    return JSON.parse(v) as T;
  } catch {
    return fallback;
  }
}

/** All configured radars (drives the radar selector). */
export async function listRadars(): Promise<RadarConfigMeta[]> {
  try {
    const rows = await q<{
      slug: string;
      name: string;
      description: string | null;
      regions: unknown;
      regulated: boolean | null;
    }>(
      `SELECT c.slug, c.name, c.description, c.regions, c.regulated
         FROM radar_configs c
        WHERE EXISTS (SELECT 1 FROM radar_runs r WHERE r.config_id = c.id)
        ORDER BY c.name`
    );
    return rows.map((r) => ({
      slug: r.slug,
      name: r.name,
      description: r.description,
      regions: parseJson<string[]>(r.regions, []),
      regulated: Boolean(r.regulated),
    }));
  } catch {
    return [];
  }
}

/** Latest run of one radar, with every cell. */
export async function getRadar(slug: string): Promise<RadarView | null> {
  try {
    const cfg = await q1<{
      id: number;
      slug: string;
      name: string;
      description: string | null;
      regions: unknown;
      regulated: boolean | null;
    }>(
      "SELECT id, slug, name, description, regions, regulated FROM radar_configs WHERE slug = $1",
      [slug]
    );
    if (!cfg) return null;

    const run = await q1<{ id: number; created_at: string; n_signals: number }>(
      `SELECT id, created_at::text AS created_at, n_signals
         FROM radar_runs WHERE config_id = $1 ORDER BY id DESC LIMIT 1`,
      [cfg.id]
    );
    if (!run) return null;

    const scopes = await q<{ slug: string; label: string }>(
      "SELECT slug, label FROM radar_scopes WHERE config_id = $1 ORDER BY sort_order, id",
      [cfg.id]
    );

    const rows = await q<{
      scope_slug: string;
      dimension: string;
      region: string;
      horizon: string | null;
      score: number | null;
      n_signals: number | null;
      method: string | null;
      rationale: string | null;
      evidence: unknown;
      override_horizon: string | null;
      override_note: string | null;
    }>(
      `SELECT scope_slug, dimension, region, horizon, score, n_signals, method,
              rationale, evidence, override_horizon, override_note
         FROM radar_cells WHERE run_id = $1`,
      [run.id]
    );

    const cells: RadarCell[] = rows.map((r) => {
      const computed = (r.horizon as Horizon | null) ?? null;
      const override = (r.override_horizon as Horizon | null) ?? null;
      return {
        scope_slug: r.scope_slug,
        dimension: r.dimension,
        region: r.region,
        horizon: computed,
        effective: override ?? computed,
        score: r.score,
        n_signals: r.n_signals ?? 0,
        method: r.method ?? "",
        rationale: r.rationale ?? "",
        evidence: parseJson<number[]>(r.evidence, []),
        override_horizon: override,
        override_note: r.override_note,
      };
    });

    const dims = DIMENSION_ORDER.filter((d) => cells.some((c) => c.dimension === d));
    const configured = parseJson<string[]>(cfg.regions, []);
    const present = [...new Set(cells.map((c) => c.region))].filter(
      (r) => r !== ANY_REGION
    );
    const regions = configured.filter((r) => present.includes(r));

    return {
      config: {
        slug: cfg.slug,
        name: cfg.name,
        description: cfg.description,
        regions,
        regulated: Boolean(cfg.regulated),
      },
      scopes,
      dimensions: dims,
      regions: regions.length ? regions : present,
      cells,
      generated: run.created_at,
      n_signals: run.n_signals ?? 0,
    };
  } catch {
    return null;
  }
}

/** Titles + links for a cell's evidence, resolved on demand. */
export async function getEvidence(ids: number[]): Promise<
  { id: number; title: string; source_url: string | null; source_name: string | null }[]
> {
  if (!ids.length) return [];
  try {
    const rows = await q<{
      id: number;
      title_en: string;
      source_url: string | null;
      source_name: string | null;
      slug: string;
      status: string;
    }>(
      `SELECT id, title_en, source_url, source_name, slug, status
         FROM trends WHERE id = ANY($1::int[])`,
      [ids]
    );
    const byId = new Map(rows.map((r) => [r.id, r]));
    return ids
      .map((id) => byId.get(id))
      .filter((r): r is NonNullable<typeof r> => Boolean(r))
      .map((r) => ({
        id: r.id,
        title: r.title_en,
        source_url: r.source_url,
        source_name: r.source_name,
      }));
  } catch {
    return [];
  }
}

/**
 * Horizon profile of a single trend, for the small badge on trend cards.
 * A trend is not a technology field, so the profile is inherited from the
 * radar scope the trend belongs to — and the caller must show the field name
 * alongside it, otherwise the badge claims a precision it does not have.
 */
export async function getTrendHorizons(
  trendId: number,
  region = "GLOBAL"
): Promise<TrendHorizonProfile | null> {
  try {
    const hit = await q1<{
      scope_slug: string;
      label: string;
      radar_slug: string;
      run_id: number;
    }>(
      `SELECT st.scope_slug, sc.label, c.slug AS radar_slug, st.run_id
         FROM radar_scope_trends st
         JOIN radar_runs run ON run.id = st.run_id
         JOIN radar_configs c ON c.id = run.config_id
         LEFT JOIN radar_scopes sc
                ON sc.config_id = run.config_id AND sc.slug = st.scope_slug
        WHERE st.trend_id = $1
        ORDER BY st.run_id DESC LIMIT 1`,
      [trendId]
    );
    if (!hit) return null;
    const rows = await q<{
      dimension: string;
      horizon: string | null;
      override_horizon: string | null;
    }>(
      `SELECT dimension, horizon, override_horizon FROM radar_cells
        WHERE run_id = $1 AND scope_slug = $2 AND region IN ($3, '*')
          AND dimension IN ('technology','regulatory','market')`,
      [hit.run_id, hit.scope_slug, region]
    );
    const cells = rows
      .map((r) => ({
        dimension: r.dimension,
        horizon: ((r.override_horizon ?? r.horizon) as Horizon | null),
      }))
      .filter((r): r is { dimension: string; horizon: Horizon } => Boolean(r.horizon));
    if (!cells.length) return null;
    return {
      scope_slug: hit.scope_slug,
      scope_label: hit.label || hit.scope_slug,
      radar_slug: hit.radar_slug,
      cells,
    };
  } catch {
    return null;
  }
}

/**
 * Batch variant of getTrendHorizons for card lists: one query for the whole
 * page instead of one per card. Returns a map trend_id → profile; trends that
 * belong to no radar field are simply absent.
 */
export async function getTrendHorizonsBatch(
  trendIds: number[],
  region = "GLOBAL"
): Promise<Record<number, TrendHorizonProfile>> {
  if (!trendIds.length) return {};
  try {
    const rows = await q<{
      trend_id: number;
      scope_slug: string;
      label: string | null;
      radar_slug: string;
      dimension: string;
      horizon: string | null;
      override_horizon: string | null;
    }>(
      `WITH latest AS (
         SELECT DISTINCT ON (config_id) id, config_id
           FROM radar_runs ORDER BY config_id, id DESC
       )
       SELECT st.trend_id, st.scope_slug, sc.label, c.slug AS radar_slug,
              cell.dimension, cell.horizon, cell.override_horizon
         FROM radar_scope_trends st
         JOIN latest ON latest.id = st.run_id
         JOIN radar_configs c ON c.id = latest.config_id
         LEFT JOIN radar_scopes sc
                ON sc.config_id = latest.config_id AND sc.slug = st.scope_slug
         JOIN radar_cells cell
                ON cell.run_id = st.run_id AND cell.scope_slug = st.scope_slug
               AND cell.region IN ($2, '*')
               AND cell.dimension IN ('technology','regulatory','market')
        WHERE st.trend_id = ANY($1::int[])`,
      [trendIds, region]
    );
    const out: Record<number, TrendHorizonProfile> = {};
    for (const r of rows) {
      const h = (r.override_horizon ?? r.horizon) as Horizon | null;
      if (!h) continue;
      const cur =
        out[r.trend_id] ??
        (out[r.trend_id] = {
          scope_slug: r.scope_slug,
          scope_label: r.label || r.scope_slug,
          radar_slug: r.radar_slug,
          cells: [],
        });
      if (!cur.cells.some((c) => c.dimension === r.dimension))
        cur.cells.push({ dimension: r.dimension, horizon: h });
    }
    return out;
  } catch {
    return {};
  }
}
