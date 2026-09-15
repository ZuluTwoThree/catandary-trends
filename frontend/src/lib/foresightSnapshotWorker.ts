import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { repoRoot } from "./researchPulseWorker";

/**
 * "Recompute" for the cluster layer (Owner 2026-09-15: the layer stays as an
 * owner instrument under the radar rule — a document with a date and a
 * button, never a cron). Same shape as the pulse worker: the button does what
 * the owner would type on the workstation,
 *
 *   .venv/bin/python -m pipeline.foresight_snapshot --all-verticals   (clusters)
 *   .venv/bin/python -m pipeline.foresight_snapshot --lineage          (evolution)
 *
 * detached from the Next process, output to data/foresight_snapshot/<stamp>.log.
 * CPU only (KMeans on the stored embeddings, no model, no GPU handover), so
 * it may run beside anything else. One run at a time via data/foresight_snapshot.lock.
 *
 * Server-side only; app/trends/foresight/actions.ts is the sole caller and
 * re-checks owner mode + same-origin before reaching here.
 */

export type SnapshotMode = "clusters" | "lineage";

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
    const mode = j.mode === "clusters" || j.mode === "lineage" ? j.mode : null;
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
  if (mode === "clusters") return ["-m", "pipeline.foresight_snapshot", "--all-verticals"];
  if (mode === "lineage") return ["-m", "pipeline.foresight_snapshot", "--lineage"];
  return null;
}

export function startSnapshotWorker(mode: string): SnapshotStartResult {
  const args = snapshotWorkerArgs(mode);
  if (!args) return { ok: false, reason: "bad" };
  if (snapshotWorkerStatus().running) return { ok: false, reason: "busy" };
  const root = repoRoot();
  const py = path.join(root, ".venv", "bin", "python");
  const mod = path.join(root, "pipeline", "foresight_snapshot.py");
  if (!fs.existsSync(py) || !fs.existsSync(mod)) return { ok: false, reason: "missing", detail: root };
  const logDir = path.join(root, "data", "foresight_snapshot");
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const log = path.join(logDir, `${stamp}-${mode}.log`);
  const env = { ...process.env, PYTHONUNBUFFERED: "1" };
  try {
    fs.mkdirSync(logDir, { recursive: true });
    const fd = fs.openSync(log, "a");
    const child = spawn(py, args, { cwd: root, env, detached: true, stdio: ["ignore", fd, fd] });
    child.unref();
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
    text: "Recompute started — CPU only, a few minutes for all scopes. Reload to see the new snapshot date.",
    warn: false,
  },
  busy: { text: "A snapshot run is already in progress; try again once it has finished.", warn: true },
  missing: { text: "Worker not found: .venv/bin/python or pipeline/foresight_snapshot.py missing next to this frontend.", warn: true },
  spawn: { text: "The worker could not be started (see server log).", warn: true },
  bad: { text: "Unknown snapshot mode — nothing started.", warn: true },
};
