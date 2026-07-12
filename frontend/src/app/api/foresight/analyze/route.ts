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
    if (fs.existsSync(path.join(dir, "scripts", "tech_analyze.py"))) return dir;
    const up = path.dirname(dir);
    if (up === dir) break;
    dir = up;
  }
  return process.cwd();
}

/**
 * GET /api/foresight/analyze  — the merged Technology tool (#28/#36/#42/#43).
 *
 * Two modes, both shelling to scripts/tech_analyze.py --json (execFile, no shell):
 *   ?q=<phrase>              → embed once: user-selectable CPC candidates (with real
 *                             full-archive counts) + smart default selection +
 *                             K(t) trajectory(default) + cross-tier lead-time.
 *                             Latency ~10-40s (embedding GPU handover).
 *   ?codes=A23C19/08,A23C19  → re-run ONLY the trajectory for the explicit user
 *                             selection (pure SQL, fast, no GPU).
 * ONE resolution, ONE TIR — the two views can never diverge again.
 */
export async function GET(request: Request) {
  const sp = new URL(request.url).searchParams;
  const q = (sp.get("q") || "").trim();
  const codesRaw = (sp.get("codes") || "").trim();

  let args: string[];
  if (codesRaw) {
    // sanitize: CPC symbols are [A-Z0-9/], comma-separated
    const codes = codesRaw
      .split(",")
      .map((c) => c.trim())
      .filter((c) => /^[A-Z0-9/]{2,20}$/.test(c))
      .slice(0, 20);
    if (codes.length === 0) {
      return NextResponse.json({ error: "no valid CPC codes" }, { status: 400 });
    }
    args = ["--codes", ...codes, "--json"];
  } else {
    if (q.length < 4 || q.length > 200) {
      return NextResponse.json({ error: "query must be 4–200 characters" }, { status: 400 });
    }
    args = ["--query", q, "--json"];
  }

  const root = repoRoot();
  const py = path.join(root, ".venv", "bin", "python");
  const script = path.join(root, "scripts", "tech_analyze.py");

  try {
    const result = await new Promise<string>((resolve, reject) => {
      execFile(
        py,
        [script, ...args],
        { cwd: root, timeout: 110_000, maxBuffer: 8 * 1024 * 1024 },
        (err, stdout) => {
          if (err) return reject(err);
          resolve(stdout);
        }
      );
    });
    const line = result.trim().split("\n").filter(Boolean).pop() || "{}";
    return NextResponse.json(JSON.parse(line));
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    const timedOut = /timed out|ETIMEDOUT/.test(msg);
    return NextResponse.json(
      { error: timedOut ? "computation timed out — try a narrower phrase" : "analysis failed" },
      { status: timedOut ? 504 : 500 }
    );
  }
}
