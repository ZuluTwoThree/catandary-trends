import { NextResponse } from "next/server";
import { execFile } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { isSameOrigin } from "@/lib/apiGuards";
import { ConcurrencyGate } from "@/lib/rateLimit";

export const dynamic = "force-dynamic";
// One heavy computation at a time (Python + GPU handover, 40-110 s).
const gate = new ConcurrencyGate(1);
export const maxDuration = 120;

/** Repo root by walking up from cwd (dev = repo root, prod = frontend/). */
function repoRoot(): string {
  let dir = process.cwd();
  for (let i = 0; i < 5; i++) {
    if (fs.existsSync(path.join(dir, "scripts", "tir_for_cpc.py"))) return dir;
    const up = path.dirname(dir);
    if (up === dir) break;
    dir = up;
  }
  return process.cwd();
}

/**
 * GET /api/foresight/tir?cpc=C12P  ("Deep analysis")
 *
 * Computes the real TIR for one CPC subclass on the citation graph (~40-70s),
 * as opposed to the instant proxy the ad-hoc query shows. cpc is validated
 * against the subclass pattern before it ever reaches the shell (execFile,
 * argv — no injection).
 */
export async function GET(request: Request) {
  // Security review 2026-10-04: this GET starts a Python job and a GPU handover.
  // A cross-site <img src=…> from any page the owner opens must not be able to
  // trigger it (no Origin/Referer of ours → 403), and at most one runs at a time.
  if (!isSameOrigin(request)) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }
  const cpc = (new URL(request.url).searchParams.get("cpc") || "").toUpperCase();
  if (!/^[A-H][0-9]{2}[A-Z]$/.test(cpc)) {
    return NextResponse.json({ error: "invalid CPC subclass" }, { status: 400 });
  }

  const root = repoRoot();
  const py = path.join(root, ".venv", "bin", "python");
  const script = path.join(root, "scripts", "tir_for_cpc.py");

  if (!gate.tryAcquire()) {
    return NextResponse.json(
      { error: "computation service busy — try again shortly" },
      { status: 503, headers: { "retry-after": "15" } }
    );
  }
  try {
    const stdout = await new Promise<string>((resolve, reject) => {
      execFile(
        py,
        [script, cpc, "--json"],
        { cwd: root, timeout: 110_000, maxBuffer: 2 * 1024 * 1024 },
        (err, out) => (err ? reject(err) : resolve(out))
      );
    });
    const line = stdout.trim().split("\n").filter(Boolean).pop() || "{}";
    return NextResponse.json(JSON.parse(line));
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    const timedOut = /timed out|ETIMEDOUT/.test(msg);
    return NextResponse.json(
      { error: timedOut ? "deep analysis timed out" : "computation failed" },
      { status: timedOut ? 504 : 500 }
    );
  } finally {
    gate.release();
  }
}
