import { spawn, type ChildProcess } from "node:child_process";
import fs from "node:fs";

/**
 * Start a workstation job from the Next process without sharing its fate.
 *
 * Every desk button (research pulse, cluster
 * snapshot) spawns a detached Python process. Detached or not, that child
 * lives in the cgroup of the systemd service that runs :3001 — and on
 * 2026-09-15 the cluster recompute grew to 56 GB, the kernel OOM-killed it,
 * systemd saw an oom-kill inside the service cgroup and restarted the whole
 * frontend. So when `systemd-run` is available the job is wrapped in its own
 * transient scope with a memory ceiling: an OOM then ends the job alone,
 * and the frontend never notices. Without systemd-run (tests, other hosts)
 * this is a plain detached spawn.
 *
 * The returned child is the `systemd-run` process in scope mode; it lives
 * exactly as long as the job and forwards SIGTERM, so lock files may keep
 * its pid for liveness checks and cancellation.
 */

export const DEFAULT_MEMORY_MAX = process.env.WORKER_MEMORY_MAX || "40G";

const SYSTEMD_RUN = "/usr/bin/systemd-run";

export function systemdRunAvailable(): boolean {
  try {
    return process.platform === "linux" && fs.existsSync(SYSTEMD_RUN);
  } catch {
    return false;
  }
}

/** Pure: the command line to execute, with or without the scope wrapper. */
export function detachedCommand(
  cmd: string,
  args: string[],
  opts: { unit: string; memoryMax?: string; useScope: boolean }
): { cmd: string; args: string[] } {
  if (!opts.useScope) return { cmd, args };
  const unit = `catandary-${opts.unit.replace(/[^A-Za-z0-9_.-]/g, "-")}-${Date.now()}`;
  return {
    cmd: SYSTEMD_RUN,
    args: [
      "--user",
      "--scope",
      "--quiet",
      "--collect",
      "-p",
      `MemoryMax=${opts.memoryMax ?? DEFAULT_MEMORY_MAX}`,
      `--unit=${unit}`,
      "--",
      cmd,
      ...args,
    ],
  };
}

export function spawnDetached(
  cmd: string,
  args: string[],
  opts: { unit: string; cwd: string; env: NodeJS.ProcessEnv; logFd: number; memoryMax?: string }
): ChildProcess {
  const line = detachedCommand(cmd, args, {
    unit: opts.unit,
    memoryMax: opts.memoryMax,
    useScope: systemdRunAvailable(),
  });
  const child = spawn(line.cmd, line.args, {
    cwd: opts.cwd,
    env: opts.env,
    detached: true,
    stdio: ["ignore", opts.logFd, opts.logFd],
  });
  child.unref();
  return child;
}
