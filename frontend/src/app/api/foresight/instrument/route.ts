import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { NextResponse } from "next/server";
import { canAccess } from "@/lib/entitlement";

export const dynamic = "force-dynamic";
export const maxDuration = 30;

/**
 * The plotting table — one route for board, queue, rating and projection.
 *
 * The logic stays in Python (`scripts/instrument.py`): curve classifier,
 * stratified sample, expertise weighting and the relevance calibration are
 * measured procedures, and a second implementation in TypeScript would
 * guarantee silent drift. Process start costs ~50 ms — nothing next to a
 * rating a human types.
 *
 * `project` is the expensive one (~3.5 s: HNSW sweep over 1.13M signals plus a
 * sampled relevance estimate per field), hence maxDuration 30.
 */

function repoRoot(): string {
  let dir = process.cwd();
  for (let i = 0; i < 5; i++) {
    if (existsSync(path.join(dir, ".venv", "bin", "python"))) return dir;
    dir = path.dirname(dir);
  }
  return process.cwd();
}

const FIELD = /^(cluster:\d+:\d+|mega:[a-z0-9_]+|vertical:[A-Z]+|search:.{1,80})$/;
const HANDLE = /^[a-z0-9_-]{1,32}$/;

async function run(args: string[]) {
  const root = repoRoot();
  const out = await new Promise<string>((resolve, reject) => {
    execFile(
      path.join(root, ".venv", "bin", "python"),
      ["scripts/instrument.py", ...args],
      { cwd: root, timeout: 25_000, maxBuffer: 16 * 1024 * 1024 },
      (err, stdout) => (err ? reject(err) : resolve(stdout))
    );
  });
  const line = out.trim().split("\n").filter(Boolean).pop() ?? "{}";
  return JSON.parse(line);
}

export async function GET(req: Request) {
  if (!(await canAccess("starter"))) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }
  const url = new URL(req.url);
  const what = url.searchParams.get("what") ?? "board";
  const rater = (url.searchParams.get("rater") ?? "owner").toLowerCase();
  if (!HANDLE.test(rater)) {
    return NextResponse.json({ error: "bad_rater" }, { status: 400 });
  }
  try {
    if (what === "search") {
      const term = (url.searchParams.get("q") ?? "").trim().slice(0, 80);
      if (term.length < 2) {
        return NextResponse.json({ error: "too_short" }, { status: 400 });
      }
      return NextResponse.json(await run(["search", "--q", term]));
    }
    if (what === "discover") {
      return NextResponse.json(await run(["discover"]));
    }
    if (what === "project") {
      return NextResponse.json(await run(["project"]));
    }
    if (what === "catalog") {
      return NextResponse.json(await run(["catalog"]));
    }
    if (what === "queue") {
      const field = url.searchParams.get("field") ?? "";
      if (!FIELD.test(field)) {
        return NextResponse.json({ error: "bad_field" }, { status: 400 });
      }
      return NextResponse.json(
        await run(["queue", "--field", field, "--rater", rater])
      );
    }
    return NextResponse.json(await run(["board", "--rater", rater]));
  } catch {
    return NextResponse.json({ error: "compute_failed" }, { status: 500 });
  }
}

export async function POST(req: Request) {
  if (!(await canAccess("starter"))) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }
  // Same-Origin: ohne Session die einzige CSRF-Abwehr.
  const origin = req.headers.get("origin");
  const host = req.headers.get("host");
  if (origin && host && !origin.endsWith(host)) {
    return NextResponse.json({ error: "bad_origin" }, { status: 403 });
  }

  let body: {
    field?: string; trend?: number; points?: number | null;
    skip?: boolean; rater?: string; add?: string; remove?: string;
    label?: string; reset?: boolean;
  };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "bad_body" }, { status: 400 });
  }
  const rater = (body.rater ?? "owner").toLowerCase();
  if (!HANDLE.test(rater)) {
    return NextResponse.json({ error: "bad_rater" }, { status: 400 });
  }

  try {
    if (body.add) {
      if (!FIELD.test(body.add)) {
        return NextResponse.json({ error: "bad_field" }, { status: 400 });
      }
      return NextResponse.json(
        await run(["fields", "--add", body.add,
                   ...(body.label ? ["--label", body.label.slice(0, 120)] : [])])
      );
    }
    if (body.reset) {
      return NextResponse.json(await run(["reset"]));
    }
    if (body.remove) {
      if (!FIELD.test(body.remove)) {
        return NextResponse.json({ error: "bad_field" }, { status: 400 });
      }
      return NextResponse.json(await run(["fields", "--remove", body.remove]));
    }
    const field = body.field ?? "";
    if (!FIELD.test(field) || !Number.isInteger(body.trend)) {
      return NextResponse.json({ error: "bad_params" }, { status: 400 });
    }
    const pts = body.points;
    if (!body.skip && (!Number.isInteger(pts) || (pts as number) < 0 || (pts as number) > 4)) {
      return NextResponse.json({ error: "bad_points" }, { status: 400 });
    }
    return NextResponse.json(
      await run([
        "rate", "--field", field, "--rater", rater,
        "--trend", String(body.trend),
        ...(body.skip ? ["--skip"] : ["--points", String(pts)]),
      ])
    );
  } catch {
    return NextResponse.json({ error: "compute_failed" }, { status: 500 });
  }
}
