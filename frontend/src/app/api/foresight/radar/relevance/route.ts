import { NextResponse } from "next/server";
import { q, q1 } from "@/lib/pg";
import { canAccess } from "@/lib/entitlement";

export const dynamic = "force-dynamic";

/**
 * Trendrelevanz: das Kriterienschema, die Bewertungen des Nutzers und der
 * maschinelle Vorschlag daneben.
 *
 * Blechschmidt (Quick Guide Trendmanagement, S. 100): „Die Trendrelevanz ist
 * ein Maß für die Bedeutung des Trends für das jeweilige Unternehmen." Sie
 * hängt davon ab, wer fragt, und steht deshalb prinzipiell nicht in unserem
 * Korpus. Diese Route schreibt, was der Nutzer setzt — und liefert daneben,
 * was die Maschine vermuten würde, damit ein Abweichen sichtbar bleibt statt
 * in einer Vorbelegung zu verschwinden (Owner-Entscheidung 2026-08-04).
 */

const SLUG = /^[a-z0-9-]{1,64}$/;
const KEY = /^[a-z_]{1,32}$/;

async function configId(radar: string): Promise<number | null> {
  const row = await q1<{ id: number }>(
    "SELECT id FROM radar_configs WHERE slug = $1",
    [radar]
  );
  return row?.id ?? null;
}

export async function GET(req: Request) {
  if (!(await canAccess("starter"))) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }
  const radar = (new URL(req.url).searchParams.get("radar") ?? "").toLowerCase();
  if (!SLUG.test(radar)) {
    return NextResponse.json({ error: "bad_params" }, { status: 400 });
  }
  const id = await configId(radar);
  if (!id) return NextResponse.json({ error: "unknown_radar" }, { status: 404 });

  const criteria = await q<{
    key: string; label: string; question: string | null;
    anchor_0: string | null; anchor_4: string | null; weight: number;
  }>(
    `SELECT key, label, question, anchor_0, anchor_4, weight
       FROM radar_relevance_criteria WHERE config_id = $1 ORDER BY sort_order, id`,
    [id]
  );
  const scores = await q<{ scope_slug: string; criterion_key: string; points: number | null; note: string | null }>(
    `SELECT scope_slug, criterion_key, points, note
       FROM radar_relevance_scores WHERE config_id = $1`,
    [id]
  );
  const maturity = await q<{ scope_slug: string; score: number | null; stage: string | null; criteria: unknown; relevance_hint: unknown }>(
    `SELECT m.scope_slug, m.score, m.stage, m.criteria, m.relevance_hint
       FROM radar_maturity m
      WHERE m.run_id = (SELECT max(id) FROM radar_runs WHERE config_id = $1)`,
    [id]
  );

  return NextResponse.json({ criteria, scores, maturity });
}

export async function POST(req: Request) {
  if (!(await canAccess("starter"))) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }
  // Same-Origin-Prüfung: ohne Session ist sie die einzige CSRF-Abwehr.
  const origin = req.headers.get("origin");
  const host = req.headers.get("host");
  if (origin && host && !origin.endsWith(host)) {
    return NextResponse.json({ error: "bad_origin" }, { status: 403 });
  }

  let body: { radar?: string; scope?: string; criterion?: string; points?: number | null; note?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "bad_body" }, { status: 400 });
  }
  const radar = (body.radar ?? "").toLowerCase();
  const scope = (body.scope ?? "").toLowerCase();
  const crit = (body.criterion ?? "").toLowerCase();
  if (!SLUG.test(radar) || !SLUG.test(scope) || !KEY.test(crit)) {
    return NextResponse.json({ error: "bad_params" }, { status: 400 });
  }
  const pts = body.points;
  if (pts !== null && pts !== undefined && (!Number.isInteger(pts) || pts < 0 || pts > 4)) {
    return NextResponse.json({ error: "bad_points" }, { status: 400 });
  }

  const id = await configId(radar);
  if (!id) return NextResponse.json({ error: "unknown_radar" }, { status: 404 });

  // `rated_by` bleibt bis zur Auth ein fester Platzhalter. Die Spalte existiert
  // schon, weil Blechschmidt mehrere Bewerter ausdrücklich vorsieht und vor dem
  // flachen Mitteln warnt (S. 102) — das Datenmodell soll dafür nicht später
  // umgebaut werden müssen.
  await q(
    `INSERT INTO radar_relevance_scores (config_id, scope_slug, criterion_key, points, note, rated_by)
     VALUES ($1, $2, $3, $4, $5, 'owner')
     ON CONFLICT (config_id, scope_slug, criterion_key, rated_by)
     DO UPDATE SET points = EXCLUDED.points, note = EXCLUDED.note,
                   rated_at = CURRENT_TIMESTAMP`,
    [id, scope, crit, pts ?? null, (body.note ?? "").slice(0, 500) || null]
  );
  return NextResponse.json({ ok: true });
}
