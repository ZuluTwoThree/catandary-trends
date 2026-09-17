import { execFile } from "node:child_process";
import path from "node:path";
import { repoRoot } from "./dossierWorker";
import type { TierName } from "./emerging";
import { TIERS } from "./tiers";

/**
 * Topic search, stage 2 (2026-09-17): the page shells out to the read-only
 * engine `python -m pipeline.topic_report "<term>" --json`. One call per
 * request; the engine caches per (query, tiers) for seven days, so a repeated
 * question comes back in under a second, a new one in a few seconds (warm)
 * or ~10 s when the corpus month totals have to be recounted (once a day).
 *
 * Server-side only (node:child_process). No user input reaches a shell: the
 * term is passed as ONE argv element to execFile, never interpolated.
 */

export interface TopicRow {
  id: number;
  title: string;
  source: string | null;
  url: string | null;
  slug: string | null;
  date: string | null;
  sim: number;
}

export interface TopicTier {
  status: "ok" | "thin" | "none";
  head: number;
  head_min: number;
  cut: number;
  found: number;
  hits: number;
  capped: boolean;
  index: "tier" | "scan";
  hits_damped: number;
  sources: number;
  top_source: string | null;
  top_source_share: number | null;
  series: [string, number][];
  first_hit: string | null;
  first_month?: string | null;
  age_months?: number | null;
  hits_recent?: number;
  oldest: TopicRow[];
  newest: TopicRow[];
  sample: TopicRow[];
  tagged_share: number | null;
}

export interface TopicReport {
  query: string;
  query_norm: string;
  tiers_key: string;
  tiers_requested: TierName[];
  status: "ok" | "nothing" | "ambiguous";
  ambiguity: {
    reason: string;
    fields: { vertical: string; share: number; titles: string[] }[];
  } | null;
  params: {
    head_min: Partial<Record<TierName, number>>;
    drop: number;
    floor: number;
    neighbours: number;
    walk_gate: number;
    exact: boolean;
  };
  corpus: { first_month: string | null; last_month: string | null; months: number; computed_at: string | null };
  tiers: Partial<Record<TierName, TopicTier>>;
  overall: {
    first_month: string | null;
    age_months: number | null;
    hits_total: number | null;
    hits_recent: number | null;
    novelty_lift: number | null;
    accel: number | null;
    established_share: number | null;
    tier_order: TierName[] | null;
    science_to_market_months: number | null;
    actors_early: number;
    actors_late: number;
    actor_growth: number | null;
  };
  fulltext_oldest: TopicRow[];
  vocabulary: { term: string; first_month: string; hits: number; sim: number }[];
  generated_at: string;
  duration_s?: number;
  timing?: Record<string, number>;
  cached?: boolean;
  report_id?: number | null;
}

export type TopicResult = { ok: true; report: TopicReport } | { ok: false; error: string };

const TIMEOUT_MS = 180_000;
const MAX_BUFFER = 16 * 1024 * 1024;
export const MAX_QUERY_CHARS = 200;

/** `?tiers=market,patent` → validated tier list; empty/invalid → all four. */
export function parseTiers(raw: string | undefined): TierName[] {
  if (!raw) return [...TIERS];
  const want = new Set(raw.split(",").map((t) => t.trim().toLowerCase()));
  const out = TIERS.filter((t) => want.has(t));
  return out.length ? out : [...TIERS];
}

export async function runTopicReport(
  query: string,
  tiers: TierName[],
  fresh = false
): Promise<TopicResult> {
  const term = query.trim().slice(0, MAX_QUERY_CHARS);
  if (!term) return { ok: false, error: "empty query" };
  const root = repoRoot();
  const py = path.join(root, ".venv", "bin", "python");
  const args = ["-m", "pipeline.topic_report", term, "--json", "--tiers", tiers.join(",")];
  if (fresh) args.push("--fresh");
  try {
    const out = await new Promise<string>((resolve, reject) => {
      execFile(py, args, { cwd: root, timeout: TIMEOUT_MS, maxBuffer: MAX_BUFFER }, (err, stdout, stderr) => {
        if (err) return reject(new Error(String(stderr || err.message).trim()));
        resolve(stdout);
      });
    });
    const report = JSON.parse(out) as TopicReport;
    return { ok: true, report };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return { ok: false, error: msg.split("\n").slice(-4).join("\n").slice(0, 800) };
  }
}
