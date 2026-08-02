import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { NextResponse } from "next/server";
import { canAccess } from "@/lib/entitlement";

export const dynamic = "force-dynamic";
export const maxDuration = 30;

/**
 * Die Signalwolke eines Radar-Felds.
 *
 * Sie wird nicht mit dem Radar vorgerechnet, weil sie zehntausendmal größer ist
 * als seine 32 Zellen und nur beim Hinsehen gebraucht wird. Die Berechnung ist
 * reine Klassifikation über schon geladene Zeilen — kein Modell, keine GPU.
 */

function repoRoot(): string {
  let dir = process.cwd();
  for (let i = 0; i < 5; i++) {
    if (existsSync(path.join(dir, ".venv", "bin", "python"))) return dir;
    dir = path.dirname(dir);
  }
  return process.cwd();
}

const SLUG = /^[a-z0-9-]{1,64}$/;

export async function GET(req: Request) {
  if (!(await canAccess("starter"))) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }
  const url = new URL(req.url);
  const radar = (url.searchParams.get("radar") ?? "").toLowerCase();
  const scope = (url.searchParams.get("scope") ?? "").toLowerCase();
  if (!SLUG.test(radar) || !SLUG.test(scope)) {
    return NextResponse.json({ error: "bad_params" }, { status: 400 });
  }

  const root = repoRoot();
  try {
    const payload = await new Promise<string>((resolve, reject) => {
      execFile(
        path.join(root, ".venv", "bin", "python"),
        ["scripts/radar_cloud.py", "--radar", radar, "--scope", scope],
        { cwd: root, timeout: 25_000, maxBuffer: 32 * 1024 * 1024 },
        (err, stdout) => (err ? reject(err) : resolve(stdout))
      );
    });
    const line = payload.trim().split("\n").filter(Boolean).pop() ?? "{}";
    const data = JSON.parse(line);
    if (data?.error) return NextResponse.json(data, { status: 404 });
    return NextResponse.json(data, {
      headers: { "cache-control": "private, max-age=300" },
    });
  } catch {
    return NextResponse.json({ error: "compute_failed" }, { status: 500 });
  }
}
