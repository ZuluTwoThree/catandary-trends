/** Shared bits of the two pulse pages (overview + theme). Not a route file. */
import type { RatioTone } from "@/lib/researchPulse";

export const TONE_CLASS: Record<RatioTone, string> = {
  up: "text-accent",
  down: "text-muted",
  flat: "text-paper",
  none: "text-muted/60",
};

export const TONE_ARROW: Record<RatioTone, string> = { up: "↗", down: "↘", flat: "→", none: "·" };

/** Desk notice after a Recompute click: ?worker=<code>. */
export const NOTICE: Record<string, { text: string; warn: boolean }> = {
  started: { text: "Recompute started — clustering takes seconds, the paragraph about a minute (model load + Gemma). Reload to see the new version.", warn: false },
  busy: { text: "A pulse run is already in progress; try again once it has finished.", warn: true },
  missing: { text: "Worker not found: .venv/bin/python or scripts/research_pulse.py missing next to this frontend.", warn: true },
  spawn: { text: "The worker could not be started (see server log).", warn: true },
  bad: { text: "Unknown theme or malformed week — nothing started.", warn: true },
};

/** computed_at is a naive workstation timestamp (to_char in db.ts). */
export function fmtStamp(ts: string | null): string {
  if (!ts) return "—";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts.slice(0, 16).replace("T", " ");
  return d.toLocaleString("en-GB", { hour12: false, dateStyle: "medium", timeStyle: "short" });
}
