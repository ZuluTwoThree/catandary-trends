import { q, q1 } from "./pg";

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
    const run = await q1<ForesightRun>(
      "SELECT id, scope, tier, k, signals, first_month, last_month, created_at::text as created_at " +
        "FROM foresight_runs WHERE scope = $1 ORDER BY id DESC LIMIT 1",
      [scope]
    );
    if (!run) return null;

    const rows = await q("SELECT * FROM foresight_clusters WHERE run_id = $1 ORDER BY size DESC", [
      run.id,
    ]);

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
      }>(
        "SELECT id, title_en, source_url, source_name FROM trends WHERE id = ANY($1::int[])",
        [repIds]
      );
      for (const r of reps) {
        repMap.set(r.id, {
          id: r.id,
          title: r.title_en,
          source_url: r.source_url,
          source_name: r.source_name,
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
    return { run, clusters };
  } catch {
    return null; // tables not present yet → page renders its empty state
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
