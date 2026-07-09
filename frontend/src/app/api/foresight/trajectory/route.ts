import { NextResponse } from "next/server";
import { execFile } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

export const dynamic = "force-dynamic";
export const maxDuration = 120;

/** Repo root by walking up from cwd (dev = repo root, prod = frontend/). */
function repoRoot(): string {
  let dir = process.cwd();
  for (let i = 0; i < 5; i++) {
    if (fs.existsSync(path.join(dir, "scripts", "tech_trajectory.py"))) return dir;
    const up = path.dirname(dir);
    if (up === dir) break;
    dir = up;
  }
  return process.cwd();
}

/**
 * GET /api/foresight/trajectory?q=<phrase>  (#36/#42/#43)
 *
 * Free text → nearest FINE CPC codes (the technology domain) → year-by-year TIR
 * trajectory K(t) + S-curve direction. Shells to scripts/tech_trajectory.py
 * --json; the phrase is an argv (execFile, no shell) so there is no injection
 * surface. Latency ~10-40s (embedding GPU handover) — a premium computation.
 */
export async function GET(request: Request) {
  const q = (new URL(request.url).searchParams.get("q") || "").trim();
  if (q.length < 4 || q.length > 200) {
    return NextResponse.json({ error: "query must be 4–200 characters" }, { status: 400 });
  }

  const root = repoRoot();
  const py = path.join(root, ".venv", "bin", "python");
  const script = path.join(root, "scripts", "tech_trajectory.py");

  try {
    const result = await new Promise<string>((resolve, reject) => {
      execFile(
        py,
        [script, q, "--json"],
        { cwd: root, timeout: 110_000, maxBuffer: 8 * 1024 * 1024 },
        (err, stdout) => {
          if (err) return reject(err);
          resolve(stdout);
        }
      );
    });
    // tech_trajectory --json prints one compact JSON line last; earlier lines
    // may be GPU-handover logs
    const line = result.trim().split("\n").filter(Boolean).pop() || "{}";
    return NextResponse.json(JSON.parse(line));
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    const timedOut = /timed out|ETIMEDOUT/.test(msg);
    return NextResponse.json(
      { error: timedOut ? "computation timed out — try a narrower phrase" : "trajectory failed" },
      { status: timedOut ? 504 : 500 }
    );
  }
}
