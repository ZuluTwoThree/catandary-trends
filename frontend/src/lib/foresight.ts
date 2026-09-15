import { q, q1, withTransaction } from "./pg";

/**
 * Read access to the persisted foresight artifacts (foresight_runs /
 * foresight_clusters, written by pipeline/foresight_snapshot.py).
 * Batch layer computes, frontend reads — no clustering in request paths.
 * All functions degrade gracefully (null / []) if the tables are missing.
 */

export interface ClusterRep {
  id: number;
  title: string;
  source_url: string | null;
  source_name: string | null;
  slug: string | null;
  status: string | null;
  date: string | null;
}

export interface ForesightCluster {
  id: number;
  cluster_idx: number;
  label: string;
  size: number;
  cohesion: number;
  mega_trend: string | null;
  mega_purity: number;
  verticals: string[];
  top_tags: string[];
  n_sources: number;
  /** Largest single source in the cluster and its share — concentration, so a
   *  "420 sources" headline cannot imply corroboration it does not have. */
  top_source: string | null;
  top_source_share: number;
  /** The two panel shares the pp delta is made of (0..1). A pp figure alone
   *  is unreadable: +0.5 pp is a big move for a 1 % cluster, noise for a 20 %
   *  one. */
  share_early: number | null;
  share_late: number | null;
  /** Raw item count change, late vs early window. Kept for the detail view —
   *  in a growing corpus every cluster's raw count grows, so it says more
   *  about our ingest than about the theme. */
  vol_delta_pct: number | null;
  momentum: "rising" | "stable" | "declining" | "unknown";
  sov_delta_pp: number;
  tier: string | null;
  reps: ClusterRep[];
  monthly_series: { m: string; n: number; share: number }[];
}

export interface ForesightRun {
  id: number;
  scope: string;
  tier: string | null;
  k: number;
  signals: number;
  first_month: string | null;
  last_month: string | null;
  created_at: string;
  /** Clustered slice: ISO lower bound and its length (0/null = full history). */
  since: string | null;
  window_months: number | null;
  /** Momentum panel: sources that delivered in BOTH comparison windows, and
   *  the share of window rows they carry. applied=false means the panel was
   *  too thin and every source counted. */
  cohort_sources: number | null;
  cohort_coverage: number | null;
  cohort_applied: boolean;
}

/** Row of the cluster detail view: a signal near the cluster centre. */
export interface ClusterNeighbour {
  id: number;
  title: string;
  source_name: string | null;
  source_url: string | null;
  slug: string | null;
  status: string | null;
  date: string | null;
  sim: number;
}

function parseJson<T>(raw: unknown, fallback: T): T {
  if (typeof raw !== "string" || !raw) return fallback;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

/** Latest persisted run for a scope ('global' | 'vertical:FOOD' | …). */
export async function getLatestClusterRun(
  scope: string
): Promise<{ run: ForesightRun; clusters: ForesightCluster[] } | null> {
  try {
    const run = await q1<RunRow>(
      RUN_COLUMNS + " FROM foresight_runs WHERE scope = $1 ORDER BY id DESC LIMIT 1",
      [scope]
    );
    if (!run) return null;

    const rows = await q(
      CLUSTER_COLUMNS + " FROM foresight_clusters WHERE run_id = $1 ORDER BY size DESC",
      [run.id]
    );

    // Evidence one click away: resolve representative signals to their
    // original source links in one query.
    const repIds = [
      ...new Set(rows.flatMap((r) => parseJson<number[]>(r.rep_trend_ids, []))),
    ];
    const repMap = new Map<number, ClusterRep>();
    if (repIds.length > 0) {
      const reps = await q<{
        id: number;
        title_en: string;
        source_url: string | null;
        source_name: string | null;
        slug: string | null;
        status: string | null;
        date: string | null;
      }>(
        "SELECT id, title_en, source_url, source_name, slug, status, " +
          "to_char(sort_date, 'YYYY-MM-DD') AS date " +
          "FROM trends WHERE id = ANY($1::int[])",
        [repIds]
      );
      for (const r of reps) {
        repMap.set(r.id, {
          id: r.id,
          title: r.title_en,
          source_url: r.source_url,
          source_name: r.source_name,
          slug: r.slug,
          status: r.status,
          date: r.date,
        });
      }
    }

    const clusters: ForesightCluster[] = rows.map((r) => ({
      id: r.id as number,
      cluster_idx: r.cluster_idx as number,
      label: (r.label as string) || `Cluster ${r.cluster_idx}`,
      size: r.size as number,
      cohesion: r.cohesion as number,
      mega_trend: (r.mega_trend as string) || null,
      mega_purity: (r.mega_purity as number) ?? 0,
      verticals: parseJson<string[]>(r.verticals, []),
      top_tags: parseJson<string[]>(r.top_tags, []),
      n_sources: (r.n_sources as number) ?? 0,
      top_source: (r.top_source as string) || null,
      top_source_share: (r.top_source_share as number) ?? 0,
      share_early: r.share_early == null ? null : (r.share_early as number),
      share_late: r.share_late == null ? null : (r.share_late as number),
      vol_delta_pct: r.vol_delta_pct == null ? null : (r.vol_delta_pct as number),
      momentum: (r.momentum as ForesightCluster["momentum"]) || "unknown",
      sov_delta_pp: (r.sov_delta_pp as number) ?? 0,
      tier: (r.tier as string) || null,
      reps: parseJson<number[]>(r.rep_trend_ids, [])
        .map((id) => repMap.get(id))
        .filter((x): x is ClusterRep => Boolean(x)),
      monthly_series: parseJson<{ m: string; n: number; share: number }[]>(
        r.monthly_series,
        []
      ),
    }));
    return { run: hydrateRun(run), clusters };
  } catch {
    return null; // tables not present yet → page renders its empty state
  }
}

const RUN_COLUMNS =
  "SELECT id, scope, tier, k, signals, first_month, last_month, " +
  "created_at::text AS created_at, since, window_months, cohort_sources, " +
  "cohort_coverage, cohort_applied";

const CLUSTER_COLUMNS =
  "SELECT id, run_id, cluster_idx, label, size, cohesion, mega_trend, mega_purity, " +
  "verticals, top_tags, n_sources, top_source, top_source_share, vol_delta_pct, " +
  "share_early, share_late, " +
  "momentum, sov_delta_pp, tier, rep_trend_ids, rep_titles, monthly_series";

type RunRow = Omit<ForesightRun, "cohort_applied"> & { cohort_applied: number | boolean | null };

function hydrateRun(r: RunRow): ForesightRun {
  return {
    ...r,
    since: r.since ?? null,
    window_months: r.window_months ?? null,
    cohort_sources: r.cohort_sources ?? null,
    cohort_coverage: r.cohort_coverage ?? null,
    // pre-2026-09-15 runs have no column value; treat them as "not applied"
    cohort_applied: r.cohort_applied === 1 || r.cohort_applied === true,
  };
}

/**
 * One cluster plus its run — the detail view's anchor. Cards used to be a dead
 * end: 95,000 signals behind three representative titles and no way in
 * (audit 2026-09-15).
 */
export async function getClusterDetail(
  clusterId: number
): Promise<{ run: ForesightRun; cluster: ForesightCluster } | null> {
  try {
    const row = await q1<Record<string, unknown>>(
      CLUSTER_COLUMNS + " FROM foresight_clusters WHERE id = $1",
      [clusterId]
    );
    if (!row) return null;
    const run = await q1<RunRow>(RUN_COLUMNS + " FROM foresight_runs WHERE id = $1", [
      row.run_id as number,
    ]);
    if (!run) return null;
    const data = await getLatestClusterRun(run.scope);
    const cluster = data?.clusters.find((c) => c.id === clusterId);
    if (!cluster) return null;
    return { run: hydrateRun(run), cluster };
  } catch {
    return null;
  }
}

/**
 * Signals nearest the cluster centre, inside the run's own scope and window.
 *
 * The centroid is persisted with the cluster (float32 bytes), so "show me this
 * cluster" is one pgvector lookup instead of re-clustering or storing hundreds
 * of thousands of memberships. ef_search is raised for this statement only —
 * the default (40) caps the candidate list far below the page size — which is
 * why this runs on a single pooled client inside a transaction.
 */
export async function getClusterNeighbours(
  clusterId: number,
  limit = 200
): Promise<ClusterNeighbour[]> {
  try {
    return await withTransaction(async (client) => {
      const meta = await client.query(
        "SELECT c.centroid, r.scope, r.since, r.status_filter " +
          "FROM foresight_clusters c JOIN foresight_runs r ON r.id = c.run_id " +
          "WHERE c.id = $1",
        [clusterId]
      );
      const m = meta.rows[0];
      if (!m?.centroid) return [];
      const vec = Buffer.isBuffer(m.centroid) ? m.centroid : Buffer.from(m.centroid);
      const floats = new Float32Array(
        vec.buffer.slice(vec.byteOffset, vec.byteOffset + vec.byteLength)
      );
      if (floats.length < 8) return [];
      const literal = "[" + Array.from(floats, (v) => v.toFixed(6)).join(",") + "]";
      const scope = String(m.scope || "");
      const vertical = scope.startsWith("vertical:") ? scope.slice("vertical:".length) : null;
      const statuses = String(m.status_filter || "signal,published")
        .split(",")
        .map((x) => x.trim())
        .filter(Boolean);

      const where = [
        "t.embedding_1024 IS NOT NULL",
        "t.status = ANY($2::text[])",
      ];
      const params: unknown[] = [literal, statuses];
      if (vertical) {
        params.push(vertical);
        where.push(`t.primary_vertical = $${params.length}`);
      }
      if (m.since) {
        params.push(m.since);
        where.push(`r.published_date >= $${params.length}`);
      }
      params.push(limit);
      await client.query("SET LOCAL hnsw.ef_search = 400");
      const res = await client.query(
        "SELECT t.id, t.title_en, t.source_name, t.source_url, t.slug, t.status, " +
          "to_char(COALESCE(r.published_date, t.sort_date), 'YYYY-MM-DD') AS date, " +
          "1 - (t.embedding_1024 <=> $1::vector) AS sim " +
          "FROM trends t JOIN raw_entries r ON r.id = t.raw_entry_id " +
          `WHERE ${where.join(" AND ")} ` +
          `ORDER BY t.embedding_1024 <=> $1::vector LIMIT $${params.length}`,
        params
      );
      return res.rows.map((r) => ({
        id: r.id as number,
        title: (r.title_en as string) || "",
        source_name: (r.source_name as string) || null,
        source_url: (r.source_url as string) || null,
        slug: (r.slug as string) || null,
        status: (r.status as string) || null,
        date: (r.date as string) || null,
        sim: Number(r.sim ?? 0),
      }));
    });
  } catch {
    return [];
  }
}

/* ----------------------------- Lead-time layer ---------------------------- */
/**
 * Cross-tier lead-time (#9/#2): the four lead-time tiers (research → patents →
 * funding → market) projected onto the shared CPC axis, read from the batch-
 * built cpc_tier_series / cpc_tier_totals / cpc_leadtime_summary. SoV (share of
 * a tier's yearly volume) is the honest unit — it normalizes out each tier's
 * different corpus depth, so the curves are comparable. A headline lead-time is
 * surfaced ONLY where the corpus can prove it (reliable = genuine in-window
 * emergence in both compared tiers); otherwise we show the curves, no number.
 */

export type TierName = "science" | "patent" | "funding" | "market";

export interface LeadTech {
  cpc: string;
  title: string;
  curated_name: string | null;
  lead_science_vs_market: number | null;
  science_takeoff: number | null;
  market_takeoff: number | null;
  reliable: boolean;
  science_n: number;
  market_n: number;
}

/** Cleaned display name for a CPC — curated Explorer name, else tidied caption. */
export function cpcDisplayName(title: string, curated: string | null): string {
  if (curated) return curated;
  let t = title.split(/[;(]/)[0].replace(/,?\s*NOT OTHERWISE PROVIDED FOR/gi, "");
  t = t.replace(/\s+/g, " ").trim().toLowerCase();
  t = t.charAt(0).toUpperCase() + t.slice(1);
  // restore bracketed acronyms: "[uav]" → "[UAV]"
  return t.replace(/\[([^\]]+)\]/g, (_, a: string) => `[${a.toUpperCase()}]`);
}

/** Reliable emerging technologies with a credible research→market lead. */
export async function getLeadTimeTechnologies(limit = 12): Promise<LeadTech[]> {
  try {
    const rows = await q<LeadTech>(
      `SELECT s.cpc, d.title, i.name AS curated_name,
              s.lead_science_vs_market, s.science_takeoff, s.market_takeoff,
              (s.reliable = 1) AS reliable, s.science_n, s.market_n
       FROM cpc_leadtime_summary s
       JOIN cpc_definitions d ON d.symbol = s.cpc
       LEFT JOIN cpc_insights i ON i.symbol = s.cpc
       WHERE s.reliable = 1 AND s.lead_science_vs_market > 0
       -- curated Explorer axes first (recognizable names), then by market
       -- prominence — so the default view opens on a technology people know
       ORDER BY (i.name IS NULL), s.market_n DESC
       LIMIT $1`,
      [limit]
    );
    return rows;
  } catch {
    return [];
  }
}

export interface TierPoint { year: number; sov: number; n: number }

/** Per-tier yearly SoV curve for one CPC (SoV = share of that tier's year). */
export async function getTierCurves(
  cpc: string
): Promise<{ tiers: Record<TierName, TierPoint[]>; lead: LeadTech | null }> {
  const empty = { science: [], patent: [], funding: [], market: [] } as Record<
    TierName,
    TierPoint[]
  >;
  try {
    const rows = await q<{ tier: TierName; year: number; sov: number; n: number }>(
      `SELECT s.tier, s.year, (s.n::float / NULLIF(t.total, 0)) AS sov, s.n
       FROM cpc_tier_series s
       JOIN cpc_tier_totals t ON t.tier = s.tier AND t.year = s.year
       WHERE s.cpc = $1 AND s.year >= 1995
       ORDER BY s.year`,
      [cpc.toUpperCase()]
    );
    const tiers = { science: [], patent: [], funding: [], market: [] } as Record<
      TierName,
      TierPoint[]
    >;
    for (const r of rows) {
      if (r.tier in tiers && r.sov != null)
        tiers[r.tier].push({ year: r.year, sov: r.sov, n: r.n });
    }
    const lead = await q1<LeadTech>(
      `SELECT s.cpc, d.title, i.name AS curated_name, s.lead_science_vs_market,
              s.science_takeoff, s.market_takeoff, (s.reliable = 1) AS reliable,
              s.science_n, s.market_n
       FROM cpc_leadtime_summary s JOIN cpc_definitions d ON d.symbol = s.cpc
       LEFT JOIN cpc_insights i ON i.symbol = s.cpc WHERE s.cpc = $1`,
      [cpc.toUpperCase()]
    );
    return { tiers: rows.length ? tiers : empty, lead };
  } catch {
    return { tiers: empty, lead: null };
  }
}

/** Scopes that actually have persisted runs (drives the tab row). */
export async function getClusterScopes(): Promise<string[]> {
  try {
    const rows = await q<{ scope: string }>(
      "SELECT DISTINCT scope FROM foresight_runs ORDER BY scope"
    );
    return rows.map((r) => r.scope);
  } catch {
    return [];
  }
}

/* ------------------------------- Lineage view ------------------------------ */
/**
 * Cross-window cluster lineage (#2 phase 1): trend evolution over time —
 * emergence / continuation / split / merge / decline and semantic drift, read
 * from foresight_lineage_{runs,nodes,edges} (built by run_lineage). The
 * frontend reads the latest lineage per scope; no clustering in the request
 * path. Centroid bytes are intentionally not shipped to the client.
 */
export interface LineageNode {
  node_idx: number;
  window_start: string;
  window_end: string;
  label: string;
  size: number;
  sov_share: number;
  cohesion: number;
  top_tags: string[];
  status: "" | "emerged" | "declined";
}

export interface LineageEdge {
  from_node: number;
  to_node: number;
  sim: number;
  drift: number;
  relation: "continue" | "split" | "merge" | "split_merge";
}

export interface LineageData {
  scope: string;
  first_window: string | null;
  last_window: string | null;
  windows: number;
  nodes: LineageNode[];
  edges: LineageEdge[];
}

export async function getLatestLineage(scope: string): Promise<LineageData | null> {
  try {
    const run = await q1<{
      id: number;
      first_window: string | null;
      last_window: string | null;
      windows: number;
    }>(
      "SELECT id, first_window, last_window, windows FROM foresight_lineage_runs " +
        "WHERE scope = $1 ORDER BY id DESC LIMIT 1",
      [scope]
    );
    if (!run) return null;
    const nodes = await q(
      "SELECT node_idx, window_start, window_end, label, size, sov_share, cohesion, " +
        "top_tags, status FROM foresight_lineage_nodes WHERE run_id = $1 ORDER BY node_idx",
      [run.id]
    );
    const edges = await q(
      "SELECT from_node, to_node, sim, drift, relation FROM foresight_lineage_edges " +
        "WHERE run_id = $1",
      [run.id]
    );
    return {
      scope,
      first_window: run.first_window,
      last_window: run.last_window,
      windows: run.windows,
      nodes: nodes.map((n) => ({
        node_idx: n.node_idx as number,
        window_start: n.window_start as string,
        window_end: n.window_end as string,
        label: (n.label as string) || "Cluster",
        size: n.size as number,
        sov_share: (n.sov_share as number) ?? 0,
        cohesion: (n.cohesion as number) ?? 0,
        top_tags: parseJson<string[]>(n.top_tags, []),
        status: (n.status as LineageNode["status"]) || "",
      })),
      edges: edges.map((e) => ({
        from_node: e.from_node as number,
        to_node: e.to_node as number,
        sim: (e.sim as number) ?? 0,
        drift: (e.drift as number) ?? 0,
        relation: (e.relation as LineageEdge["relation"]) || "continue",
      })),
    };
  } catch {
    return null;
  }
}

/** Scopes that have a persisted lineage (drives the selector). */
export async function getLineageScopes(): Promise<string[]> {
  try {
    const rows = await q<{ scope: string }>(
      "SELECT DISTINCT scope FROM foresight_lineage_runs ORDER BY scope"
    );
    return rows.map((r) => r.scope);
  } catch {
    return [];
  }
}

/**
 * Thread a lineage into human-readable theme trajectories: follow each chain
 * forward through 'continue'/'split' edges from its earliest node, so a theme
 * becomes one ordered series of (window, share, size) points. Split/merge are
 * annotated but do not fork the primary thread (we follow the strongest
 * successor). Threads are classified by their endpoints: 'emerging' (starts
 * with an emerged node in the recent half), 'fading' (ends declined),
 * 'ongoing'. Pure read-side shaping — no DB access.
 */
export interface LineageThread {
  key: number; // node_idx of the thread head
  label: string;
  kind: "emerging" | "fading" | "ongoing";
  points: { window_start: string; share: number; size: number }[];
  peak_share: number;
  latest_share: number;
  drift: number; // 1 - similarity accumulated along the thread (semantic move)
}

export function threadLineage(data: LineageData): LineageThread[] {
  const byIdx = new Map(data.nodes.map((n) => [n.node_idx, n]));
  // strongest successor per node (continue/split), and set of nodes that are a successor
  const bestNext = new Map<number, LineageEdge>();
  const hasPred = new Set<number>();
  for (const e of data.edges) {
    hasPred.add(e.to_node);
    const cur = bestNext.get(e.from_node);
    if (!cur || e.sim > cur.sim) bestNext.set(e.from_node, e);
  }
  const windowsSorted = [...new Set(data.nodes.map((n) => n.window_start))].sort();
  const recentCut = windowsSorted[Math.floor(windowsSorted.length / 2)] ?? "";

  const threads: LineageThread[] = [];
  const consumed = new Set<number>();

  const walk = (start: LineageNode): { thread: LineageThread; lastStatus: string } => {
    const points: LineageThread["points"] = [];
    let cur: LineageNode | undefined = start;
    let drift = 0;
    let lastStatus: LineageNode["status"] = "";
    const guard = new Set<number>();
    while (cur && !guard.has(cur.node_idx)) {
      guard.add(cur.node_idx);
      consumed.add(cur.node_idx);
      points.push({ window_start: cur.window_start, share: cur.sov_share, size: cur.size });
      lastStatus = cur.status;
      const nx = bestNext.get(cur.node_idx);
      if (!nx) break;
      drift += nx.drift;
      cur = byIdx.get(nx.to_node);
    }
    const peak = Math.max(...points.map((p) => p.share), 0);
    return {
      thread: {
        key: start.node_idx,
        label: start.label,
        kind: "ongoing",
        points,
        peak_share: peak,
        latest_share: points[points.length - 1]?.share ?? 0,
        drift: Number(drift.toFixed(3)),
      },
      lastStatus,
    };
  };

  // 1. Emerging seeds first: an emerged node in the recent half starts its own
  //    thread even when an overlapping neighbour precedes it (that neighbour is
  //    only a step old, not a full span — the emergence is real).
  const emergedSeeds = data.nodes
    .filter((n) => n.status === "emerged" && n.window_start >= recentCut)
    .sort((a, b) => b.size - a.size);
  for (const seed of emergedSeeds) {
    if (consumed.has(seed.node_idx)) continue;
    const { thread } = walk(seed);
    if (thread.points.length) threads.push({ ...thread, kind: "emerging" });
  }

  // 2. Remaining chain heads → ongoing, or fading if they end declined.
  const heads = data.nodes
    .filter((n) => !hasPred.has(n.node_idx) && !consumed.has(n.node_idx))
    .sort((a, b) => b.size - a.size);
  for (const head of heads) {
    if (consumed.has(head.node_idx)) continue;
    const { thread, lastStatus } = walk(head);
    if (!thread.points.length) continue;
    threads.push({ ...thread, kind: lastStatus === "declined" ? "fading" : "ongoing" });
  }
  return threads;
}
