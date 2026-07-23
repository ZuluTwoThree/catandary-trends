import { NextResponse } from "next/server";
import { canAccess } from "@/lib/entitlement";
import { execFile } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { rateLimit, clientIp, ConcurrencyGate } from "@/lib/rateLimit";

export const dynamic = "force-dynamic";
export const maxDuration = 120;

// --- resource guards (#55): this route shells to Python + a GPU embedding handover,
// so an unguarded public GET is a resource-exhaustion vector. Single-server, in-process.
const RL_LIMIT = 6;               // requests …
const RL_WINDOW_MS = 60_000;      // … per minute per IP
const MAX_CONCURRENT = 2;         // simultaneous heavy computations (GPU handover)
const CACHE_TTL_MS = 10 * 60_000; // normalized-query result cache
const gate = new ConcurrencyGate(MAX_CONCURRENT);
const cache = new Map<string, { at: number; body: unknown }>();

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
  // Entitlement guard (CONF-02): Pro data must not be free over the raw
  // API while the paywall is on. No-op while PAYWALL_ENABLED=0.
  if (!(await canAccess("pro"))) {
    return NextResponse.json(
      { error: "This data is part of the Pro plan", upgrade: "/trends/pricing" },
      { status: 402 }
    );
  }
  const q = (new URL(request.url).searchParams.get("q") || "").trim();
  if (q.length < 4 || q.length > 200) {
    return NextResponse.json({ error: "query must be 4–200 characters" }, { status: 400 });
  }

  // Normalized-query cache: cheap repeated/popular queries never hit Python/GPU.
  const cacheKey = q.toLowerCase().replace(/\s+/g, " ");
  const cached = cache.get(cacheKey);
  if (cached && Date.now() - cached.at < CACHE_TTL_MS) {
    return NextResponse.json(cached.body, { headers: { "x-cache": "hit" } });
  }

  // Per-IP rate limit.
  if (!rateLimit(`traj:${clientIp(request)}`, RL_LIMIT, RL_WINDOW_MS)) {
    return NextResponse.json(
      { error: "rate limit exceeded — please wait a moment" },
      { status: 429, headers: { "retry-after": "30" } }
    );
  }

  // Global concurrency gate: refuse rather than pile up GPU handovers / Node workers.
  if (!gate.tryAcquire()) {
    return NextResponse.json(
      { error: "analysis service busy — try again shortly" },
      { status: 503, headers: { "retry-after": "15" } }
    );
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
    const body = JSON.parse(line);
    cache.set(cacheKey, { at: Date.now(), body });
    return NextResponse.json(body, { headers: { "x-cache": "miss" } });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    const timedOut = /timed out|ETIMEDOUT/.test(msg);
    return NextResponse.json(
      { error: timedOut ? "computation timed out — try a narrower phrase" : "trajectory failed" },
      { status: timedOut ? 504 : 500 }
    );
  } finally {
    gate.release();
  }
}
