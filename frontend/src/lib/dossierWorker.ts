import fs from "node:fs";
import { spawnDetached } from "./detachedSpawn";
import path from "node:path";

/**
 * Starting the dossier worker from the desk (#95, "Neu rechnen").
 *
 * The radar rule applies to dossiers: a dossier is a dated document,
 * recomputed only on the owner's explicit click — never on a cron. The
 * button therefore does exactly what the owner would type on the
 * workstation: `.venv/bin/python -m scripts.dossier_worker [--order N]`,
 * detached from the Next process, output to data/dossier_worker/<stamp>.log.
 * The worker itself does the GPU handover (embedding model → 27B → resting
 * state) and parks every finished run in 'review'.
 *
 * One worker at a time: a lock file (data/dossier_worker.lock, pid + log)
 * written here and checked with kill(pid, 0). A worker started from a
 * terminal is invisible to the lock — the desk shows DB status 'running'
 * for that case (lib/dossiers.ts).
 *
 * Server-side only (node:child_process); the actions in
 * app/trends/dossiers/actions.ts are the sole callers and re-check
 * canManageDossiers() + same-origin before reaching this module.
 */

export interface WorkerStatus {
  running: boolean;
  pid: number | null;
  startedAt: string | null;
  log: string | null;
  /** A lock whose process is gone — the last run's trace, not a live worker. */
  stale: boolean;
}

export type StartResult =
  | { ok: true; pid: number; log: string }
  | { ok: false; reason: "busy" | "missing" | "spawn"; detail?: string };

/** Repo root: the frontend runs with cwd=<repo>/frontend on both worktrees. */
export function repoRoot(): string {
  return process.env.DOSSIER_WORKER_ROOT || path.resolve(process.cwd(), "..");
}

function lockPath(): string {
  return path.join(repoRoot(), "data", "dossier_worker.lock");
}

function alive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

export function workerStatus(): WorkerStatus {
  const none: WorkerStatus = { running: false, pid: null, startedAt: null, log: null, stale: false };
  let raw: string;
  try {
    raw = fs.readFileSync(lockPath(), "utf8");
  } catch {
    return none;
  }
  try {
    const j = JSON.parse(raw) as { pid?: unknown; startedAt?: unknown; log?: unknown };
    const pid = Number(j.pid);
    if (!Number.isInteger(pid) || pid <= 0) return none;
    const startedAt = typeof j.startedAt === "string" ? j.startedAt : null;
    const log = typeof j.log === "string" ? j.log : null;
    if (alive(pid)) return { running: true, pid, startedAt, log, stale: false };
    return { running: false, pid, startedAt, log, stale: true };
  } catch {
    return none;
  }
}

/** Only the two shapes the desk ever needs; anything else is refused. */
export function workerArgs(orderId?: number): string[] | null {
  if (orderId === undefined) return [];
  if (!Number.isInteger(orderId) || orderId <= 0) return null;
  return ["--order", String(orderId)];
}

export function startWorker(args: string[]): StartResult {
  if (workerStatus().running) return { ok: false, reason: "busy" };
  const root = repoRoot();
  const py = path.join(root, ".venv", "bin", "python");
  const script = path.join(root, "scripts", "dossier_worker.py");
  if (!fs.existsSync(py) || !fs.existsSync(script)) {
    return { ok: false, reason: "missing", detail: root };
  }
  const logDir = path.join(root, "data", "dossier_worker");
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const log = path.join(logDir, `${stamp}.log`);
  const uid = process.getuid?.() ?? 1000;
  const env = {
    ...process.env,
    PYTHONUNBUFFERED: "1",
    // cron-needs-xdg-runtime-dir: `systemctl --user` (the GPU handover)
    // fails silently without the user bus.
    XDG_RUNTIME_DIR: process.env.XDG_RUNTIME_DIR ?? `/run/user/${uid}`,
    DBUS_SESSION_BUS_ADDRESS:
      process.env.DBUS_SESSION_BUS_ADDRESS ?? `unix:path=/run/user/${uid}/bus`,
  };
  try {
    fs.mkdirSync(logDir, { recursive: true });
    const fd = fs.openSync(log, "a");
    const child = spawnDetached(py, ["-m", "scripts.dossier_worker", ...args], {
      unit: "dossier", cwd: root, env, logFd: fd,
    });
    fs.closeSync(fd);
    if (!child.pid) return { ok: false, reason: "spawn" };
    fs.writeFileSync(
      lockPath(),
      JSON.stringify({ pid: child.pid, startedAt: new Date().toISOString(), log, args })
    );
    return { ok: true, pid: child.pid, log };
  } catch (e) {
    return { ok: false, reason: "spawn", detail: e instanceof Error ? e.message : String(e) };
  }
}
