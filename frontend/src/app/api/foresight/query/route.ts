import { NextResponse } from "next/server";
import { execFile } from "node:child_process";
import path from "node:path";

export const dynamic = "force-dynamic";
export const maxDuration = 120;

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
  const url = new URL(request.url);
  const q = (url.searchParams.get("q") || "").trim();
  const threshold = Math.min(0.9, Math.max(0.2, Number(url.searchParams.get("threshold")) || 0.45));

  if (q.length < 4 || q.length > 200) {
    return NextResponse.json({ error: "query must be 4–200 characters" }, { status: 400 });
  }

  const repoRoot = path.resolve(process.cwd(), "..");
  const py = path.join(repoRoot, ".venv", "bin", "python");
  const script = path.join(repoRoot, "scripts", "tech_query.py");

  try {
    const result = await new Promise<string>((resolve, reject) => {
      execFile(
        py,
        [script, q, "--threshold", String(threshold), "--json"],
        { cwd: repoRoot, timeout: 110_000, maxBuffer: 4 * 1024 * 1024 },
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
