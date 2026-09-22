/**
 * What the review agent found — read from its report, never re-computed here.
 *
 * `scripts/review_agent.py` checks the drafts a gate holds: is the flagged
 * figure the same value said differently ("1 000" vs "1,000", "Seventy percent"
 * vs "70%", 6,100万人 vs 61 million), and does the source really name the person
 * the article names? It writes one JSON file per run. This module reads that
 * file so the review desk can show the finding — the class, the verbatim quote
 * from the source, and what the agent would propose — next to the article the
 * reviewer is looking at.
 *
 * Deliberately one-way: the desk never writes to the report, and the report
 * never decides anything. A proposal the reviewer applies is taken FROM HERE by
 * index (see `proposalAt`), never from the form the browser posts — so a stale
 * page or a forged request cannot put an arbitrary string into an article.
 */
import { readFile } from "node:fs/promises";
import path from "node:path";

export const REPORT_PATH =
  process.env.REVIEW_AGENT_REPORT ||
  path.join(process.cwd(), "..", "data", "review_agent_last.json");

export interface AgentFigure {
  token: string;
  ok: boolean;
  why: string;
  evidence: string;
  form: string;
  note: string;
}

export interface AgentName {
  name: string;
  ok: boolean;
  /** named · translit_confirmed · surname_only · role_only · absent · misspelled · translit */
  kind: string;
  evidence: string;
  source_form: string;
  latin?: string;
  title_not_in_source?: string[];
  note: string;
}

export interface AgentProposal {
  /** "spelling" — adopt the source's spelling · "drop_sentence" — remove the sentence. */
  kind: string;
  what: string;
  to?: string;
  note: string;
}

export interface AgentItem {
  id: number;
  decision: string;
  why: string;
  figures: AgentFigure[];
  names: AgentName[];
  proposals: AgentProposal[];
}

export interface AgentReport {
  date: string;
  model: string;
  dryRun: boolean;
  items: Map<number, AgentItem>;
}

/** Plain-language labels — the same wording the agent's own report uses. */
export const NAME_KIND_LABEL: Record<string, string> = {
  named: "source names this person",
  translit_confirmed: "source names them in another script (romanisation confirmed)",
  surname_only: "source gives only the family name — the given name was added",
  role_only: "source gives only a role — the name comes from the model, not the source",
  absent: "person does not appear in the source",
  misspelled: "spelling differs from the source",
  translit: "another script, romanisation does not match",
};

export const PROPOSAL_LABEL: Record<string, string> = {
  spelling: "Use the source's spelling",
  drop_sentence: "Drop that sentence",
};

function asStringArray(v: unknown): string[] {
  return Array.isArray(v) ? v.map(String) : [];
}

export function parseReport(raw: string): AgentReport | null {
  let d: Record<string, unknown>;
  try {
    d = JSON.parse(raw) as Record<string, unknown>;
  } catch {
    return null;
  }
  const rows = Array.isArray(d.items) ? (d.items as Record<string, unknown>[]) : [];
  const items = new Map<number, AgentItem>();
  for (const r of rows) {
    const id = Number(r.id);
    if (!Number.isInteger(id) || id <= 0) continue;
    const figures = (Array.isArray(r.figures) ? r.figures : []).map((f) => {
      const x = f as Record<string, unknown>;
      return {
        token: String(x.token ?? ""),
        ok: Boolean(x.ok),
        why: String(x.why ?? ""),
        evidence: String(x.evidence ?? ""),
        form: String(x.form ?? ""),
        note: String(x.note ?? ""),
      };
    });
    const names = (Array.isArray(r.names) ? r.names : []).map((n) => {
      const x = n as Record<string, unknown>;
      return {
        name: String(x.name ?? ""),
        ok: Boolean(x.ok),
        kind: String(x.kind ?? ""),
        evidence: String(x.evidence ?? ""),
        source_form: String(x.source_form ?? ""),
        latin: x.latin ? String(x.latin) : undefined,
        title_not_in_source: asStringArray(x.title_not_in_source),
        note: String(x.note ?? ""),
      };
    });
    const proposals = (Array.isArray(r.proposals) ? r.proposals : []).map((p) => {
      const x = p as Record<string, unknown>;
      return {
        kind: String(x.kind ?? ""),
        what: String(x.what ?? ""),
        to: x.to ? String(x.to) : undefined,
        note: String(x.note ?? ""),
      };
    });
    items.set(id, {
      id,
      decision: String(r.decision ?? ""),
      why: String(r.why ?? ""),
      figures,
      names,
      proposals,
    });
  }
  return {
    date: String(d.date ?? ""),
    model: String(d.model ?? ""),
    dryRun: Boolean(d.dry_run),
    items,
  };
}

let cache: { at: number; report: AgentReport | null } | null = null;
const TTL_MS = 30_000;

/** The last run's report, or null when the agent has not run (or the file is gone). */
export async function getAgentReport(): Promise<AgentReport | null> {
  if (cache && Date.now() - cache.at < TTL_MS) return cache.report;
  let report: AgentReport | null = null;
  try {
    report = parseReport(await readFile(REPORT_PATH, "utf8"));
  } catch {
    report = null;
  }
  cache = { at: Date.now(), report };
  return report;
}

/** Fresh read, bypassing the cache — used by the actions that apply a proposal. */
export async function readReportUncached(): Promise<AgentReport | null> {
  try {
    return parseReport(await readFile(REPORT_PATH, "utf8"));
  } catch {
    return null;
  }
}

/**
 * The proposal at `index` for this trend — the single source of truth for what
 * an "apply" button may do. The browser posts an id and an index, nothing else.
 */
export function proposalAt(
  report: AgentReport | null,
  id: number,
  index: number
): AgentProposal | null {
  const item = report?.items.get(id);
  if (!item) return null;
  const p = item.proposals[index];
  return p ?? null;
}

/** How old the report is, in hours — the desk says so, because it may be stale. */
export function ageHours(report: AgentReport | null, now: Date = new Date()): number | null {
  if (!report?.date) return null;
  const t = Date.parse(report.date);
  if (Number.isNaN(t)) return null;
  return (now.getTime() - t) / 3_600_000;
}
