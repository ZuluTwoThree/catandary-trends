import fs from "node:fs";
import { spawnDetached } from "./detachedSpawn";
import path from "node:path";
import { repoRoot } from "./researchPulseWorker";

/**
 * "Recompute" for the cluster layer (Owner 2026-09-15: the layer stays as an
 * owner instrument under the radar rule — a document with a date and a
 * button, never a cron). Same shape as the pulse worker: the button does what
 * the owner would type on the workstation,
 *
 *   .venv/bin/python -m pipeline.foresight_snapshot --all-verticals --dim1024   (clusters)
 *   .venv/bin/python -m pipeline.foresight_snapshot --lineage --dim1024          (evolution)
 *
 * --dim1024 is not optional here: the first desk run (2026-09-15) went for the
 * full 4096-dim column, reached 56 GB and was OOM-killed — taking the :3001
 * service with it. The job now runs in its own systemd scope (detachedSpawn).
 *
 * detached from the Next process, output to data/foresight_snapshot/<stamp>.log.
 * CPU only (KMeans on the stored embeddings, no model, no GPU handover), so
 * it may run beside anything else; 10–20 min over ~1.75M signals. One run at a time via data/foresight_snapshot.lock.
 *
 * Server-side only; app/trends/foresight/actions.ts is the sole caller and
 * re-checks owner mode + same-origin before reaching here.
 */

export type SnapshotMode = "clusters" | "lineage" | "emerging";

export interface SnapshotWorkerStatus {
  running: boolean;
  pid: number | null;
  startedAt: string | null;
  log: string | null;
  mode: SnapshotMode | null;
}

export type SnapshotStartResult =
  | { ok: true; pid: number; log: string }
  | { ok: false; reason: "busy" | "missing" | "spawn" | "bad"; detail?: string };

function lockPath(): string {
  return path.join(repoRoot(), "data", "foresight_snapshot.lock");
}

function alive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

export function snapshotWorkerStatus(): SnapshotWorkerStatus {
  const none: SnapshotWorkerStatus = { running: false, pid: null, startedAt: null, log: null, mode: null };
  let raw: string;
  try {
    raw = fs.readFileSync(lockPath(), "utf8");
  } catch {
    return none;
  }
  try {
    const j = JSON.parse(raw) as { pid?: unknown; startedAt?: unknown; log?: unknown; mode?: unknown };
    const pid = Number(j.pid);
    if (!Number.isInteger(pid) || pid <= 0) return none;
    const mode =
      j.mode === "clusters" || j.mode === "lineage" || j.mode === "emerging" ? j.mode : null;
    const startedAt = typeof j.startedAt === "string" ? j.startedAt : null;
    const log = typeof j.log === "string" ? j.log : null;
    if (!alive(pid)) return none;
    return { running: true, pid, startedAt, log, mode };
  } catch {
    return none;
  }
}

/** Only the two fixed invocations ever reach the shell — no user input becomes an argument. */
export function snapshotWorkerArgs(mode: string): string[] | null {
  if (mode === "clusters") return ["-m", "pipeline.foresight_snapshot", "--all-verticals", "--dim1024"];
  if (mode === "lineage") return ["-m", "pipeline.foresight_snapshot", "--lineage", "--dim1024"];
  // The emerging layer has its own module: fine partition of a recent slice,
  // then a dating pass over the whole archive. CPU only, ~5 min per scope.
  // Stage 5 of the topic-search plan (2026-09-17): global plus the four
  // conversations, no longer one run per vertical — the search page is where
  // a topic is checked, the pockets only supply suggestions.
  if (mode === "emerging")
    return ["-m", "pipeline.emerging_snapshot", "--scope", "global", "--all-tiers"];
  return null;
}

export function startSnapshotWorker(mode: string): SnapshotStartResult {
  const args = snapshotWorkerArgs(mode);
  if (!args) return { ok: false, reason: "bad" };
  if (snapshotWorkerStatus().running) return { ok: false, reason: "busy" };
  const root = repoRoot();
  const py = path.join(root, ".venv", "bin", "python");
  const mod = path.join(root, "pipeline",
    mode === "emerging" ? "emerging_snapshot.py" : "foresight_snapshot.py");
  if (!fs.existsSync(py) || !fs.existsSync(mod)) return { ok: false, reason: "missing", detail: root };
  const logDir = path.join(root, "data", "foresight_snapshot");
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const log = path.join(logDir, `${stamp}-${mode}.log`);
  const env = { ...process.env, PYTHONUNBUFFERED: "1" };
  try {
    fs.mkdirSync(logDir, { recursive: true });
    const fd = fs.openSync(log, "a");
    const child = spawnDetached(py, args, { unit: `snapshot-${mode}`, cwd: root, env, logFd: fd });
    fs.closeSync(fd);
    if (!child.pid) return { ok: false, reason: "spawn" };
    fs.writeFileSync(lockPath(), JSON.stringify({ pid: child.pid, startedAt: new Date().toISOString(), log, mode }));
    return { ok: true, pid: child.pid, log };
  } catch (e) {
    return { ok: false, reason: "spawn", detail: e instanceof Error ? e.message : String(e) };
  }
}

/** Notice after a Recompute click: ?worker=<code>. */
export const SNAPSHOT_NOTICE: Record<string, { text: string; warn: boolean }> = {
  started: {
    text: "Recompute started — CPU only, 10–45 minutes depending on the layer. Reload to see the new date.",
    warn: false,
  },
  busy: { text: "A snapshot run is already in progress; try again once it has finished.", warn: true },
  missing: { text: "Worker not found: .venv/bin/python or the snapshot module is missing next to this frontend.", warn: true },
  spawn: { text: "The worker could not be started (see server log).", warn: true },
  bad: { text: "Unknown snapshot mode — nothing started.", warn: true },
};
