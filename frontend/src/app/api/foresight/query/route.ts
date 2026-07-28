import { NextResponse } from "next/server";
import { canAccess } from "@/lib/entitlement";
import { execFile } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

export const dynamic = "force-dynamic";
export const maxDuration = 120;

/** Repo root, found by walking up from cwd — robust to whether the server runs
 *  with cwd at the repo root (dev) or the frontend/ dir (standalone prod). */
function repoRoot(): string {
  let dir = process.cwd();
  for (let i = 0; i < 5; i++) {
    if (fs.existsSync(path.join(dir, "scripts", "tech_query.py"))) return dir;
    const up = path.dirname(dir);
    if (up === dir) break;
    dir = up;
  }
  return process.cwd();
}

/**
 * GET /api/foresight/query?q=<phrase>&threshold=0.45  (Super Pro+ on-demand scope)
 *
 * Embeds the phrase and projects it onto the four lead-time tiers + nearest CPC
 * TIR by shelling out to scripts/tech_query.py --json. The query text is passed
 * as an argv (execFile, no shell) so there is no injection surface; only the
 * embedding model sees the free text. Latency is ~10-40s (GPU handover) — this
 * is a premium on-demand computation, not a cached lookup.
 */
export async function GET(request: Request) {
  // Entitlement guard (CONF-02): Super Pro+ data must not be free over the raw
  // API while the paywall is on. No-op while PAYWALL_ENABLED=0.
  if (!(await canAccess("superpro"))) {
    return NextResponse.json(
      { error: "This data is part of the Super Pro+ plan", upgrade: "/trends/pricing" },
      { status: 402 }
    );
  }
  const url = new URL(request.url);
  const q = (url.searchParams.get("q") || "").trim();
  const threshold = Math.min(0.9, Math.max(0.2, Number(url.searchParams.get("threshold")) || 0.45));

  if (q.length < 4 || q.length > 200) {
    return NextResponse.json({ error: "query must be 4–200 characters" }, { status: 400 });
  }

  const root = repoRoot();
  const py = path.join(root, ".venv", "bin", "python");
  const script = path.join(root, "scripts", "tech_query.py");

  try {
    const result = await new Promise<string>((resolve, reject) => {
      execFile(
        py,
        [script, q, "--threshold", String(threshold), "--json"],
        { cwd: root, timeout: 110_000, maxBuffer: 4 * 1024 * 1024 },
        (err, stdout) => {
          if (err) return reject(err);
          resolve(stdout);
        }
      );
    });
    // the script may emit non-JSON log lines to stdout under some backends;
    // take the last non-empty line, which is the JSON payload
    const line = result.trim().split("\n").filter(Boolean).pop() || "{}";
    return NextResponse.json(JSON.parse(line));
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    const timedOut = /timed out|ETIMEDOUT/.test(msg);
    return NextResponse.json(
      { error: timedOut ? "computation timed out — try a narrower phrase" : "query failed" },
      { status: timedOut ? 504 : 500 }
    );
  }
}
