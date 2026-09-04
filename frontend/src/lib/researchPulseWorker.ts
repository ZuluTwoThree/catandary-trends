import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { MEGA_TRENDS } from "./mega-trends.generated";
import { cliWeek, type PulseWeekRef } from "./researchPulse";

/**
 * "Recompute" for one Research Pulse theme (#73) — the same shape as the
 * dossier worker (lib/dossierWorker.ts): the button does exactly what the
 * owner would type on the workstation,
 *
 *   .venv/bin/python scripts/research_pulse.py --themes <key> --week 2026-W35
 *
 * detached from the Next process, output to data/research_pulse/<stamp>.log.
 * The script does the GPU handover itself (Gemma-4-26B for the paragraph)
 * and restores the resting state afterwards. One run at a time via a lock
 * file (data/research_pulse.lock, pid + log) checked with kill(pid, 0); a
 * run started from a terminal is invisible to the lock — the page then just
 * shows the newest row once it lands.
 *
 * Server-side only; app/trends/foresight/research/pulse/actions.ts is the
 * sole caller and re-checks owner mode + same-origin before reaching here.
 */

export interface PulseWorkerStatus {
  running: boolean;
  pid: number | null;
  startedAt: string | null;
  log: string | null;
  theme: string | null;
  stale: boolean;
}

export type PulseStartResult =
  | { ok: true; pid: number; log: string }
  | { ok: false; reason: "busy" | "missing" | "spawn" | "bad"; detail?: string };

export function repoRoot(): string {
  return process.env.DOSSIER_WORKER_ROOT || path.resolve(process.cwd(), "..");
}

function lockPath(): string {
  return path.join(repoRoot(), "data", "research_pulse.lock");
}

function alive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

export function pulseWorkerStatus(): PulseWorkerStatus {
  const none: PulseWorkerStatus = { running: false, pid: null, startedAt: null, log: null, theme: null, stale: false };
  let raw: string;
  try {
    raw = fs.readFileSync(lockPath(), "utf8");
  } catch {
    return none;
  }
  try {
    const j = JSON.parse(raw) as { pid?: unknown; startedAt?: unknown; log?: unknown; theme?: unknown };
    const pid = Number(j.pid);
    if (!Number.isInteger(pid) || pid <= 0) return none;
    const startedAt = typeof j.startedAt === "string" ? j.startedAt : null;
    const log = typeof j.log === "string" ? j.log : null;
    const theme = typeof j.theme === "string" ? j.theme : null;
    if (alive(pid)) return { running: true, pid, startedAt, log, theme, stale: false };
    return { running: false, pid, startedAt, log, theme, stale: true };
  } catch {
    return none;
  }
}

/** Only a known theme key and a well-formed week ever reach the shell. */
export function pulseWorkerArgs(theme: string, week: PulseWeekRef | null): string[] | null {
  if (!MEGA_TRENDS.some((m) => m.key === theme)) return null;
  const args = ["--themes", theme];
  if (week) {
    if (!Number.isInteger(week.year) || !Number.isInteger(week.week)
      || week.week < 1 || week.week > 53 || week.year < 2000 || week.year > 2100) return null;
    args.push("--week", cliWeek(week));
  }
  return args;
}

export function startPulseWorker(theme: string, week: PulseWeekRef | null): PulseStartResult {
  const args = pulseWorkerArgs(theme, week);
  if (!args) return { ok: false, reason: "bad" };
  if (pulseWorkerStatus().running) return { ok: false, reason: "busy" };
  const root = repoRoot();
  const py = path.join(root, ".venv", "bin", "python");
  const script = path.join(root, "scripts", "research_pulse.py");
  if (!fs.existsSync(py) || !fs.existsSync(script)) {
    return { ok: false, reason: "missing", detail: root };
  }
  const logDir = path.join(root, "data", "research_pulse");
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
    const child = spawn(py, [script, ...args], {
      cwd: root,
      env,
      detached: true,
      stdio: ["ignore", fd, fd],
    });
    child.unref();
    fs.closeSync(fd);
    if (!child.pid) return { ok: false, reason: "spawn" };
    fs.writeFileSync(
      lockPath(),
      JSON.stringify({ pid: child.pid, startedAt: new Date().toISOString(), log, theme, args })
    );
    return { ok: true, pid: child.pid, log };
  } catch (e) {
    return { ok: false, reason: "spawn", detail: e instanceof Error ? e.message : String(e) };
  }
}
