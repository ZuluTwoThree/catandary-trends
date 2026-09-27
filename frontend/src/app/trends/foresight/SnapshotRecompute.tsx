import { recomputeSnapshotAction } from "./actions";
import {
  SNAPSHOT_NOTICE,
  snapshotWorkerStatus,
  type SnapshotMode,
} from "@/lib/foresightSnapshotWorker";

/**
 * Compute stamp + "Recompute" button for the cluster layer (radar rule: a
 * document with a date and a button, no cron). Server component; the action
 * re-checks owner mode and same-origin. `asOf` is the persisted run's date
 * (null = no snapshot yet), `back` the page to return to.
 *
 * Lives INSIDE app/trends/foresight rather than in components/, and must stay
 * there: it imports the server action from this tree, and the static export
 * strips the whole tree (static-export.exclude mirrors BLOCKED_PREFIXES). As a
 * component it survived the strip while its import did not, and the 03:15
 * publish died on "Cannot find module @/app/trends/foresight/actions" —
 * nothing uploaded, the previous day's site left online (2026-09-16).
 * `staticExport.test.ts` now fails any import that crosses this boundary.
 */
export default function SnapshotRecompute({
  mode,
  asOf,
  back,
  notice,
}: {
  mode: SnapshotMode;
  asOf: string | null;
  back: string;
  notice?: string;
}) {
  const worker = snapshotWorkerStatus();
  const n = notice ? SNAPSHOT_NOTICE[notice] : undefined;
  const label =
    mode === "lineage"
      ? "Recompute lineage"
      : mode === "emerging"
        ? "Recompute pockets"
        : mode === "space"
          ? "Recompute cloud"
          : "Recompute snapshot";
  return (
    <div className="mb-8 flex flex-wrap items-center gap-x-4 gap-y-2 border border-border px-4 py-3 font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
      <span>
        Computed / <span className="text-paper">{asOf ?? "never"}</span>
      </span>
      <span className="text-border">——</span>
      <span>On demand only, no cron</span>
      {worker.running ? (
        <span className="text-accent">run in progress{worker.mode ? ` · ${worker.mode}` : ""}</span>
      ) : (
        <form action={recomputeSnapshotAction} className="ml-auto">
          <input type="hidden" name="mode" value={mode} />
          <input type="hidden" name="back" value={back} />
          <button className="border border-accent px-3 py-1.5 text-accent transition-colors hover:bg-accent hover:text-ink">
            {label}
          </button>
        </form>
      )}
      {n && (
        <p className={`basis-full normal-case tracking-normal ${n.warn ? "text-warn" : "text-text"}`}>{n.text}</p>
      )}
    </div>
  );
}
