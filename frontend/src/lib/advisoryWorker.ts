import fs from "node:fs";
import { spawnDetached } from "./detachedSpawn";
import path from "node:path";
import { repoRoot, workerStatus, type StartResult } from "./dossierWorker";

/**
 * Start the Advisor for one note, detached from the Next process —
 * `.venv/bin/python -m scripts.advisory --note N`, output to
 * data/advisory/<stamp>.log. Shares the GPU with the dossier worker: while a
 * dossier run holds the lock, the desk refuses to start (busy). One advisory
 * run at a time (data/advisory.lock, pid + log).
 */

function lockPath(): string {
  return path.join(repoRoot(), "data", "advisory.lock");
}

export function advisoryRunning(): boolean {
  try {
    const raw = fs.readFileSync(lockPath(), "utf8");
    const { pid } = JSON.parse(raw) as { pid?: number };
    if (!pid) return false;
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

export function startAdvisory(noteId: number): StartResult {
  if (workerStatus().running || advisoryRunning()) return { ok: false, reason: "busy" };
  const root = repoRoot();
  const py = path.join(root, ".venv", "bin", "python");
  const script = path.join(root, "scripts", "advisory.py");
  if (!fs.existsSync(py) || !fs.existsSync(script)) return { ok: false, reason: "missing", detail: root };
  const logDir = path.join(root, "data", "advisory");
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const log = path.join(logDir, `${stamp}.log`);
  const uid = process.getuid?.() ?? 1000;
  const env = {
    ...process.env,
    PYTHONUNBUFFERED: "1",
    XDG_RUNTIME_DIR: process.env.XDG_RUNTIME_DIR ?? `/run/user/${uid}`,
    DBUS_SESSION_BUS_ADDRESS: process.env.DBUS_SESSION_BUS_ADDRESS ?? `unix:path=/run/user/${uid}/bus`,
  };
  try {
    fs.mkdirSync(logDir, { recursive: true });
    const fd = fs.openSync(log, "a");
    const child = spawnDetached(py, ["-m", "scripts.advisory", "--note", String(noteId)], {
      unit: "advisory", cwd: root, env, logFd: fd,
    });
    fs.closeSync(fd);
    if (!child.pid) return { ok: false, reason: "spawn" };
    fs.writeFileSync(
      lockPath(),
      JSON.stringify({ pid: child.pid, startedAt: new Date().toISOString(), log, args: ["--note", noteId] })
    );
    return { ok: true, pid: child.pid, log };
  } catch (e) {
    return { ok: false, reason: "spawn", detail: e instanceof Error ? e.message : String(e) };
  }
}
