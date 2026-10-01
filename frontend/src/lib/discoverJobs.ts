/**
 * Job shapes of the live discovery service (pipeline/domain_service.py) and the
 * small helpers the page needs on the client. No server imports here — the
 * client component imports this file; lib/discover.ts holds the server side.
 */
export type JobState =
  | "queued"
  | "select"
  | "preview"
  | "pockets"
  | "done"
  | "failed"
  | "discarded";

export interface PreviewCard {
  id: number;
  title: string;
  source: string | null;
  tier: string;
  month: string | null;
  p: number;
}

export interface DiscoverPreview {
  window_from: string;
  window_months: number;
  members_window: number;
  members_archive: number;
  first_month: string | null;
  by_tier: Record<string, number>;
  literal_share: number;
  literal_sample: number;
  seeds: Record<string, number>;
  auc: number | null;
  examples: PreviewCard[];
  just_outside: PreviewCard[];
  enough: boolean;
  min_signals: number;
}

export interface DiscoverOutline {
  group: number;
  label: string | null;
  nests: { name: string; size: number; first_month: string | null }[];
}

export interface DiscoverJob {
  id: string;
  term: string;
  also: string[];
  key: string;
  window_months: number;
  state: JobState;
  stage: string;
  log: { t: number; msg: string }[];
  preview: DiscoverPreview | null;
  result: {
    run_id: number;
    scope: string;
    nests: number;
    groups: number;
    in_pockets: number;
    named: number;
    naming: string;
    outline: DiscoverOutline[];
  } | null;
  error: string | null;
  seconds_select: number | null;
  seconds_pockets: number | null;
}

export interface ServiceHealth {
  ready: boolean;
  loading: string;
  rows: number;
  built_at: string | null;
  refreshed_at: string | null;
  queue: number;
  running: string | null;
}

/** Labels for the job states shown on the page. */
export const STATE_LABEL: Record<JobState, string> = {
  queued: "queued",
  select: "selecting signals",
  preview: "selection ready",
  pockets: "finding pockets",
  done: "done",
  failed: "failed",
  discarded: "discarded",
};

export function isRunning(state: JobState): boolean {
  return state === "queued" || state === "select" || state === "pockets";
}
