import { NextResponse } from "next/server";
import { canAccess } from "@/lib/entitlement";
import { execFile } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

export const dynamic = "force-dynamic";
export const maxDuration = 120;

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
 * GET /api/foresight/query/evidence?q=<phrase>&tier=science&year=2021&threshold=0.45
 *
 * The signals behind one tier's bar — surfaced when the user clicks a sparkline.
 * Shells out to tech_query.py --evidence (execFile, argv — no injection); tier
 * and year are validated before use.
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
  const tier = (url.searchParams.get("tier") || "").toLowerCase();
  const yearRaw = url.searchParams.get("year");
  const threshold = Math.min(0.9, Math.max(0.2, Number(url.searchParams.get("threshold")) || 0.45));

  if (q.length < 4 || q.length > 200) {
    return NextResponse.json({ error: "query must be 4–200 characters" }, { status: 400 });
  }
  if (!["science", "patent", "funding", "market"].includes(tier)) {
    return NextResponse.json({ error: "invalid tier" }, { status: 400 });
  }
  const yearOk = yearRaw && /^\d{4}$/.test(yearRaw);

  const root = repoRoot();
  const py = path.join(root, ".venv", "bin", "python");
  const script = path.join(root, "scripts", "tech_query.py");
  const argv = [script, q, "--evidence", tier, "--threshold", String(threshold), "--json"];
  if (yearOk) argv.push("--year", yearRaw);

  try {
    const stdout = await new Promise<string>((resolve, reject) => {
      execFile(py, argv, { cwd: root, timeout: 110_000, maxBuffer: 4 * 1024 * 1024 }, (err, out) =>
        err ? reject(err) : resolve(out)
      );
    });
    const line = stdout.trim().split("\n").filter(Boolean).pop() || "{}";
    return NextResponse.json(JSON.parse(line));
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    const timedOut = /timed out|ETIMEDOUT/.test(msg);
    return NextResponse.json(
      { error: timedOut ? "evidence lookup timed out" : "lookup failed" },
      { status: timedOut ? 504 : 500 }
    );
  }
}
