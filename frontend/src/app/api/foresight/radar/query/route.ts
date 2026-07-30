import { NextResponse } from "next/server";
import { execFile } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { canAccess } from "@/lib/entitlement";
import { rateLimitInfo, clientIp, ConcurrencyGate } from "@/lib/rateLimit";
import { ResponseCache, cacheKey } from "@/lib/responseCache";

export const dynamic = "force-dynamic";
export const maxDuration = 30;

/**
 * GET /api/foresight/radar/query?q=<phrase>
 *
 * Builds a horizon radar for a free-text query — the same RadarView the saved
 * radars serve, computed on demand and persisted nowhere. GET because the
 * result is a *view*: idempotent, cacheable, and the state belongs in the URL
 * (both existing search tools keep it in React state instead, which is why
 * their results cannot be shared or reloaded — issue KEY-04).
 *
 * No GPU: the whole path is Postgres FTS plus the same cell logic the curated
 * radars use. Measured 0.07-0.28 s, hence the modest maxDuration.
 *
 * Guard order is copied from api/foresight/analyze/route.ts — cache lookup sits
 * BEFORE the rate limit so a repeated query never spends a token. The one
 * deliberate deviation: that route's cache is an unbounded Map; here it is the
 * bounded ResponseCache (lib/responseCache.ts).
 */

const RL_LIMIT = 8; // free-text radars per minute per IP
const RL_WINDOW_MS = 60_000;
const MAX_CONCURRENT = 2;

const gate = new ConcurrencyGate(MAX_CONCURRENT);
const cache = new ResponseCache<unknown>({ maxEntries: 200, ttlMs: 15 * 60_000 });

const JURISDICTIONS = ["US", "EU", "UK", "IL", "APAC", "GLOBAL"];

/** Repo root by walking up from cwd (dev = repo root, prod = frontend/). */
function repoRoot(): string {
  let dir = process.cwd();
  for (let i = 0; i < 5; i++) {
    if (fs.existsSync(path.join(dir, "scripts", "radar_query.py"))) return dir;
    const up = path.dirname(dir);
    if (up === dir) break;
    dir = up;
  }
  return process.cwd();
}

export async function GET(request: Request) {
  // Viewing a radar is Starter; this builds one from arbitrary input, which is
  // the Super Pro+ promise ("Analyze any technology or topic you bring").
  if (!(await canAccess("superpro"))) {
    return NextResponse.json(
      { error: "Building a radar from your own query is part of Super Pro+", upgrade: "/trends/pricing" },
      { status: 402 }
    );
  }

  const sp = new URL(request.url).searchParams;
  const q = (sp.get("q") || "").trim().replace(/\s+/g, " ");
  if (q.length < 3 || q.length > 120) {
    return NextResponse.json(
      { error: "Enter between 3 and 120 characters." },
      { status: 400 }
    );
  }

  const dim = sp.get("dim") === "pestel" ? "pestel" : "strategic";
  const regulated = sp.get("regulated") === "1";
  const regions = (sp.get("regions") || "US,EU,GLOBAL")
    .split(",")
    .map((r) => r.trim().toUpperCase())
    .filter((r) => JURISDICTIONS.includes(r))
    .slice(0, 6);
  const regionArg = (regions.length ? regions : ["GLOBAL"]).join(",");

  const key = cacheKey({ q: q.toLowerCase(), dim, regulated: regulated ? 1 : 0, regions: regionArg });
  const cached = cache.get(key);
  if (cached) {
    return NextResponse.json(cached, { headers: { "x-cache": "hit" } });
  }

  const rl = rateLimitInfo(`radar-q:${clientIp(request)}`, RL_LIMIT, RL_WINDOW_MS);
  if (!rl.ok) {
    return NextResponse.json(
      { error: "Too many radars — try again shortly." },
      { status: 429, headers: { "retry-after": String(rl.retryAfterSec ?? 30) } }
    );
  }

  if (!gate.tryAcquire()) {
    return NextResponse.json(
      { error: "Busy — another radar is being built. Try again in a moment." },
      { status: 503, headers: { "retry-after": "10" } }
    );
  }

  try {
    const root = repoRoot();
    const args = ["scripts/radar_query.py", "--query", q, "--regions", regionArg, "--dim", dim, "--json"];
    if (regulated) args.push("--regulated");

    const body = await new Promise<unknown>((resolve, reject) => {
      execFile(
        path.join(root, ".venv", "bin", "python"),
        args,
        { cwd: root, timeout: 25_000, maxBuffer: 8 * 1024 * 1024 },
        (err, stdout) => {
          if (err) return reject(err);
          const lines = stdout.trim().split("\n").filter(Boolean);
          const last = lines[lines.length - 1];
          try {
            resolve(JSON.parse(last));
          } catch {
            reject(new Error("unparseable output"));
          }
        }
      );
    });

    // The script reports too_broad / too_thin as data, not as failure: both are
    // statements about the corpus, the same kind the empty cell makes.
    const payload = body as { error?: string };
    if (payload?.error === "too_broad") {
      return NextResponse.json(body, { status: 400 });
    }

    cache.set(key, body);
    return NextResponse.json(body, { headers: { "x-cache": "miss" } });
  } catch (err) {
    const e = err as NodeJS.ErrnoException & { killed?: boolean; signal?: string };
    const timedOut =
      /timed out|ETIMEDOUT/.test(e?.message ?? "") || e?.killed === true || e?.signal === "SIGTERM";
    return NextResponse.json(
      { error: timedOut ? "That query took too long — try a narrower phrase." : "Could not build the radar." },
      { status: timedOut ? 504 : 500 }
    );
  } finally {
    gate.release();
  }
}
