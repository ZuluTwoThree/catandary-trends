import { q, q1 } from "./pg";

/**
 * Data layer for the owner-only dossier desk (/trends/dossiers).
 *
 * Tables come from scripts/migrate_dossier_orders.py, which — like every
 * additive migration in this repo — must be run MANUALLY once against the
 * live DB. Until then this layer reports `ready: false` instead of crashing
 * (same defensive to_regclass pattern as the dead_links lookup in db.ts).
 *
 * Status contract (mirrors pipeline/dossier_orders.py exactly — every write
 * here re-checks the source status in the WHERE clause, so the page can never
 * push an order somewhere the worker wouldn't):
 *
 *   queued → running → review → done   ('done' only via owner approval here)
 *   queued → cancelled · running/queued → failed → queued (requeue)
 */

export interface DossierOrder {
  id: number;
  slug: string;
  topic: string;
  question: string | null;
  status: "queued" | "running" | "review" | "done" | "failed" | "cancelled";
  error: string | null;
  check: DossierCheck | null;
  dossierVersion: number | null;
  createdAt: string | null;
  finishedAt: string | null;
}

/** Agent end-control verdict (pipeline/dossier_check.py). */
export interface DossierCheck {
  ok: boolean;
  findings: string[];
  ungrounded: string[];
  stripped_citations: number;
  cited: number;
  sources: number;
  open_questions: number;
  words: number;
  quant_ok?: boolean;
  seconds?: number;
}

export interface DossierSeries {
  slug: string;
  topic: string | null;
  versions: number;
  latestVersion: number;
  latestAt: string | null;
}

export interface DossierDoc {
  slug: string;
  version: number;
  topic: string | null;
  question: string;
  reportMd: string;
  createdAt: string | null;
  model: string | null;
}

export async function dossierTablesReady(): Promise<boolean> {
  try {
    const row = await q1<{ orders: string | null; dossiers: string | null }>(
      `SELECT to_regclass('public.dossier_orders')::text AS orders,
              to_regclass('public.dossiers')::text AS dossiers`
    );
    return Boolean(row?.orders && row?.dossiers);
  } catch {
    return false;
  }
}

function parseCheck(raw: unknown): DossierCheck | null {
  if (!raw) return null;
  try {
    const c = typeof raw === "string" ? JSON.parse(raw) : raw;
    if (typeof c !== "object" || c === null) return null;
    const o = c as Record<string, unknown>;
    return {
      ok: Boolean(o.ok),
      findings: Array.isArray(o.findings) ? o.findings.map(String) : [],
      ungrounded: Array.isArray(o.ungrounded) ? o.ungrounded.map(String) : [],
      stripped_citations: Number(o.stripped_citations ?? 0),
      cited: Number(o.cited ?? 0),
      sources: Number(o.sources ?? 0),
      open_questions: Number(o.open_questions ?? 0),
      words: Number(o.words ?? 0),
      quant_ok: o.quant_ok === undefined ? undefined : Boolean(o.quant_ok),
      seconds: o.seconds === undefined ? undefined : Number(o.seconds),
    };
  } catch {
    return null;
  }
}

interface OrderRow {
  id: number;
  slug: string;
  topic: string;
  question: string | null;
  status: DossierOrder["status"];
  error: string | null;
  check_json: string | null;
  dossier_version: number | null;
  created_at: string | null;
  finished_at: string | null;
}

function toOrder(r: OrderRow): DossierOrder {
  return {
    id: r.id,
    slug: r.slug,
    topic: r.topic,
    question: r.question,
    status: r.status,
    error: r.error,
    check: parseCheck(r.check_json),
    dossierVersion: r.dossier_version,
    createdAt: r.created_at ? String(r.created_at) : null,
    finishedAt: r.finished_at ? String(r.finished_at) : null,
  };
}

export async function listDossierOrders(limit = 60): Promise<DossierOrder[]> {
  try {
    const rows = await q<OrderRow>(
      `SELECT id, slug, topic, question, status, error, check_json,
              dossier_version, created_at::text, finished_at::text
         FROM dossier_orders ORDER BY id DESC LIMIT $1`,
      [limit]
    );
    return rows.map(toOrder);
  } catch {
    return [];
  }
}

/** The order whose run produced dossiers(slug, version) — carries the agent's
 *  end-control for the review panel next to the report. */
export async function getOrderForVersion(
  slug: string,
  version: number
): Promise<DossierOrder | null> {
  try {
    const r = await q1<OrderRow>(
      `SELECT id, slug, topic, question, status, error, check_json,
              dossier_version, created_at::text, finished_at::text
         FROM dossier_orders
        WHERE slug = $1 AND dossier_version = $2
        ORDER BY id DESC LIMIT 1`,
      [slug, version]
    );
    return r ? toOrder(r) : null;
  } catch {
    return null;
  }
}

export async function listDossierSeries(): Promise<DossierSeries[]> {
  try {
    return await q<DossierSeries>(
      `SELECT slug,
              max(topic) AS topic,
              count(*)::int AS versions,
              max(version)::int AS "latestVersion",
              max(created_at)::text AS "latestAt"
         FROM dossiers GROUP BY slug ORDER BY max(created_at) DESC`
    );
  } catch {
    return [];
  }
}

export async function listVersions(
  slug: string
): Promise<{ version: number; createdAt: string | null }[]> {
  try {
    return await q<{ version: number; createdAt: string | null }>(
      `SELECT version, created_at::text AS "createdAt"
         FROM dossiers WHERE slug = $1 ORDER BY version DESC`,
      [slug]
    );
  } catch {
    return [];
  }
}

export async function getDossier(
  slug: string,
  version?: number
): Promise<DossierDoc | null> {
  try {
    const r = version
      ? await q1<Record<string, unknown>>(
          `SELECT slug, version, topic, question, report_md, model,
                  created_at::text AS created_at
             FROM dossiers WHERE slug = $1 AND version = $2`,
          [slug, version]
        )
      : await q1<Record<string, unknown>>(
          `SELECT slug, version, topic, question, report_md, model,
                  created_at::text AS created_at
             FROM dossiers WHERE slug = $1
            ORDER BY version DESC LIMIT 1`,
          [slug]
        );
    if (!r) return null;
    return {
      slug: String(r.slug),
      version: Number(r.version),
      topic: r.topic ? String(r.topic) : null,
      question: String(r.question ?? ""),
      reportMd: String(r.report_md ?? ""),
      createdAt: r.created_at ? String(r.created_at) : null,
      model: r.model ? String(r.model) : null,
    };
  } catch {
    return null;
  }
}

/** Mirror of pipeline.dossier_orders.slugify — one series per topic. */
export function slugifyTopic(text: string): string {
  const ascii = text
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    // eslint-disable-next-line no-control-regex
    .replace(/[^\x00-\x7F]/g, "");
  const slug = ascii
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
  return slug || "dossier";
}

const ORDERABLE = /^[\s\S]{1,500}$/;

export async function createDossierOrder(input: {
  topic: string;
  slug?: string;
  question?: string;
  quant: boolean;
}): Promise<number | null> {
  const topic = input.topic.trim();
  if (!topic || !ORDERABLE.test(topic)) return null;
  const slug = slugifyTopic(input.slug?.trim() || topic);
  const question = input.question?.trim() || null;
  const params = JSON.stringify(input.quant ? {} : { quant: false });
  const row = await q1<{ id: number }>(
    `INSERT INTO dossier_orders (slug, topic, question, params_json)
     VALUES ($1, $2, $3, $4) RETURNING id`,
    [slug, topic, question, params]
  );
  return row?.id ?? null;
}

async function transition(
  id: number,
  from: string[],
  to: string,
  extraSet = ""
): Promise<boolean> {
  const rows = await q<{ id: number }>(
    `UPDATE dossier_orders SET status = $1${extraSet}
      WHERE id = $2 AND status = ANY($3) RETURNING id`,
    [to, id, from]
  );
  return rows.length === 1;
}

/** Owner sign-off after the final read — the ONLY path to 'done'. */
export async function approveDossierOrder(id: number): Promise<boolean> {
  return transition(id, ["review"], "done", ", reviewed_at = now()");
}

export async function cancelDossierOrder(id: number): Promise<boolean> {
  return transition(id, ["queued"], "cancelled");
}

export async function requeueDossierOrder(id: number): Promise<boolean> {
  return transition(id, ["failed"], "queued");
}
