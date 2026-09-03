import { NextResponse } from "next/server";
import { execFile } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { rateLimit, clientIp, ConcurrencyGate } from "@/lib/rateLimit";

export const dynamic = "force-dynamic";
export const maxDuration = 180;

// --- resource guards (wie trajectory, #55): q-Modus shellt Python + GPU-Embedding-
// Handover, codes-Modus schwere SQL-Aggregate — beides ungeschützt eine
// Resource-Exhaustion-Fläche. Single-server, in-process.
const RL_Q_LIMIT = 6;              // Freitext-Analysen pro Minute pro IP (GPU)
const RL_CODES_LIMIT = 12;         // Checkbox-Re-Runs pro Minute pro IP (SQL)
const RL_WINDOW_MS = 60_000;
const MAX_CONCURRENT = 2;          // gleichzeitige schwere Berechnungen
const CACHE_TTL_MS = 10 * 60_000;  // Cache für normalisierte Freitext-Queries
const gate = new ConcurrencyGate(MAX_CONCURRENT);
const cache = new Map<string, { at: number; body: unknown }>();

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
      return NextResponse.json({ error: "No valid patent classes selected." }, { status: 400 });
    }
    args = ["--codes", ...codes, "--json"];
  } else {
    if (q.length < 4 || q.length > 200) {
      return NextResponse.json({ error: "Enter between 4 and 200 characters." }, { status: 400 });
    }
    args = ["--query", q, "--json"];
  }

  // Cache (nur Freitext — codes-Auswahlen sind zu individuell für sinnvolle Hits).
  const cacheKey = codesRaw ? null : q.toLowerCase().replace(/\s+/g, " ");
  if (cacheKey) {
    const hit = cache.get(cacheKey);
    if (hit && Date.now() - hit.at < CACHE_TTL_MS) {
      return NextResponse.json(hit.body, { headers: { "x-cache": "hit" } });
    }
  }

  // Per-IP-Rate-Limit (Freitext strenger als Checkbox-Re-Runs).
  const rlKey = codesRaw ? `analyze-codes:${clientIp(request)}` : `analyze-q:${clientIp(request)}`;
  if (!rateLimit(rlKey, codesRaw ? RL_CODES_LIMIT : RL_Q_LIMIT, RL_WINDOW_MS)) {
    return NextResponse.json(
      { error: "rate limit exceeded — please wait a moment" },
      { status: 429, headers: { "retry-after": "30" } }
    );
  }

  // Globales Concurrency-Gate: ablehnen statt GPU-Handover/Worker stapeln.
  if (!gate.tryAcquire()) {
    return NextResponse.json(
      { error: "analysis service busy — try again shortly" },
      { status: 503, headers: { "retry-after": "15" } }
    );
  }

  const root = repoRoot();
  const py = path.join(root, ".venv", "bin", "python");
  const script = path.join(root, "scripts", "tech_analyze.py");

  try {
    const result = await new Promise<string>((resolve, reject) => {
      execFile(
        py,
        [script, ...args],
        { cwd: root, timeout: 170_000, maxBuffer: 8 * 1024 * 1024 },
        (err: (Error & { killed?: boolean; signal?: string }) | null, stdout) => {
          if (err) return reject(err);
          resolve(stdout);
        }
      );
    });
    const line = result.trim().split("\n").filter(Boolean).pop() || "{}";
    const body = JSON.parse(line);
    if (cacheKey) cache.set(cacheKey, { at: Date.now(), body });
    return NextResponse.json(body, cacheKey ? { headers: { "x-cache": "miss" } } : undefined);
  } catch (e) {
    // execFile's own timeout kills with SIGTERM and an err WITHOUT "timed out" in
    // the message — classify it as a timeout too so slow GPU handovers surface a
    // clear retry hint instead of a bare "analysis failed".
    const err = e as (Error & { killed?: boolean; signal?: string });
    const msg = err instanceof Error ? err.message : String(e);
    const timedOut = /timed out|ETIMEDOUT/.test(msg) || err?.killed === true || err?.signal === "SIGTERM";
    return NextResponse.json(
      { error: timedOut ? "This analysis is taking longer than usual — please try again in a minute." : "Analysis failed — please try again." },
      { status: timedOut ? 504 : 500 }
    );
  } finally {
    gate.release();
  }
}
