import { q, q1 } from "./pg";

/**
 * Data layer for advisory notes (the Advisor, 2026-09-14): options for ONE
 * client from ONE dossier, written later by a model in the consultant role,
 * checked, read, and released only by a person.
 *
 * Mirrors pipeline/advisory_store.py exactly — every write re-checks the
 * source status in the WHERE clause:
 *
 *   queued → running → review → approved   (approval only by a person, here or --approve)
 *   queued/running → failed → queued (rerun) · approved/review → withdrawn
 *
 * The table is created by `python -m scripts.advisory` (ensure_schema, additive);
 * until then the readers return empty lists instead of crashing.
 */

export const PROFILE_FIELDS = [
  ["industry", "Industry"],
  ["size", "Size (staff, revenue)"],
  ["position", "Position in the value chain"],
  ["capabilities", "Capabilities (what they can execute)"],
  ["geography", "Geography / home market"],
  ["horizon", "Planning horizon"],
  ["risk_appetite", "Risk appetite"],
  ["notes", "Notes (free text)"],
] as const;

export type AdvisoryStatus = "queued" | "running" | "review" | "approved" | "failed" | "withdrawn";

export interface AdvisoryCheck {
  ok: boolean;
  reader_ok: boolean | null;
  findings: string[];
  stripped_citations: number;
  unfilled: string[];
  foreign_figures: string[];
  cited: number;
  words: number;
  seconds?: number;
}

export interface AdvisoryNote {
  id: number;
  dossierSlug: string;
  dossierVersion: number;
  profile: Record<string, string>;
  scope: string;
  status: AdvisoryStatus;
  noteMd: string | null;
  check: AdvisoryCheck | null;
  model: string | null;
  error: string | null;
  createdAt: string | null;
  finishedAt: string | null;
  approvedAt: string | null;
  approvedBy: string | null;
  approvalNote: string | null;
}

function parseCheck(raw: unknown): AdvisoryCheck | null {
  if (!raw) return null;
  try {
    const c = (typeof raw === "string" ? JSON.parse(raw) : raw) as Record<string, unknown>;
    if (typeof c !== "object" || c === null) return null;
    return {
      ok: Boolean(c.ok),
      reader_ok: c.reader_ok === undefined || c.reader_ok === null ? null : Boolean(c.reader_ok),
      findings: Array.isArray(c.findings) ? c.findings.map(String) : [],
      stripped_citations: Number(c.stripped_citations ?? 0),
      unfilled: Array.isArray(c.unfilled) ? c.unfilled.map(String) : [],
      foreign_figures: Array.isArray(c.foreign_figures) ? c.foreign_figures.map(String) : [],
      cited: Number(c.cited ?? 0),
      words: Number(c.words ?? 0),
      seconds: c.seconds === undefined ? undefined : Number(c.seconds),
    };
  } catch {
    return null;
  }
}

function parseProfile(raw: unknown): Record<string, string> {
  try {
    const p = (typeof raw === "string" ? JSON.parse(raw) : raw) as Record<string, unknown>;
    if (typeof p !== "object" || p === null) return {};
    const out: Record<string, string> = {};
    for (const [k, v] of Object.entries(p)) if (v != null && String(v).trim()) out[k] = String(v);
    return out;
  } catch {
    return {};
  }
}

function row(r: Record<string, unknown>): AdvisoryNote {
  const ts = (v: unknown) => (v == null ? null : v instanceof Date ? v.toISOString() : String(v));
  return {
    id: Number(r.id),
    dossierSlug: String(r.dossier_slug),
    dossierVersion: Number(r.dossier_version),
    profile: parseProfile(r.profile_json),
    scope: String(r.scope ?? ""),
    status: String(r.status) as AdvisoryStatus,
    noteMd: r.note_md == null ? null : String(r.note_md),
    check: parseCheck(r.check_json),
    model: r.model == null ? null : String(r.model),
    error: r.error == null ? null : String(r.error),
    createdAt: ts(r.created_at),
    finishedAt: ts(r.finished_at),
    approvedAt: ts(r.approved_at),
    approvedBy: r.approved_by == null ? null : String(r.approved_by),
    approvalNote: r.approval_note == null ? null : String(r.approval_note),
  };
}

export async function listAdvisoryNotes(dossierSlug: string, limit = 30): Promise<AdvisoryNote[]> {
  try {
    const rows = await q<Record<string, unknown>>(
      `SELECT * FROM advisory_notes WHERE dossier_slug = $1 ORDER BY id DESC LIMIT $2`,
      [dossierSlug, limit]
    );
    return rows.map(row);
  } catch {
    return [];
  }
}

export async function getAdvisoryNote(id: number): Promise<AdvisoryNote | null> {
  try {
    const r = await q1<Record<string, unknown>>(`SELECT * FROM advisory_notes WHERE id = $1`, [id]);
    return r ? row(r) : null;
  } catch {
    return null;
  }
}

export async function createAdvisoryNote(input: {
  dossierSlug: string;
  dossierVersion: number;
  profile: Record<string, string>;
  scope: string;
}): Promise<number | null> {
  const scope = input.scope.trim();
  if (!scope || scope.length > 4000) return null;
  const profile: Record<string, string> = {};
  for (const [k] of PROFILE_FIELDS) {
    const v = (input.profile[k] ?? "").trim();
    if (v) profile[k] = v.slice(0, 1000);
  }
  const r = await q1<{ id: number }>(
    `INSERT INTO advisory_notes (dossier_slug, dossier_version, profile_json, scope)
     VALUES ($1, $2, $3, $4) RETURNING id`,
    [input.dossierSlug, input.dossierVersion, JSON.stringify(profile), scope]
  );
  return r?.id ?? null;
}

async function transition(
  id: number,
  from: AdvisoryStatus[],
  to: AdvisoryStatus,
  extraSql = "",
  extraParams: unknown[] = []
): Promise<boolean> {
  const r = await q1<{ id: number }>(
    `UPDATE advisory_notes SET status = $1${extraSql}
     WHERE id = $2 AND status = ANY($3::text[]) RETURNING id`,
    [to, id, from, ...extraParams]
  );
  return Boolean(r);
}

/** Release by a person — only from review. Nothing leaves the house without approved_at. */
export async function approveAdvisoryNote(id: number, by: string, note: string | null): Promise<boolean> {
  return transition(id, ["review"], "approved", ", approved_at = now(), approved_by = $4, approval_note = $5", [
    by.slice(0, 120) || "owner",
    note && note.trim() ? note.trim().slice(0, 2000) : null,
  ]);
}

export async function withdrawAdvisoryNote(id: number): Promise<boolean> {
  return transition(id, ["approved", "review"], "withdrawn", ", approved_at = NULL, approved_by = NULL");
}

export async function requeueAdvisoryNote(id: number): Promise<boolean> {
  return transition(id, ["failed", "withdrawn"], "queued");
}
