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
 *   running → awaiting_confirmation → queued   (stage 1 checkpoint, 2026-09-19:
 *     the worker's intake parks the order with brief/profile/plan on the slip;
 *     the owner confirms or corrects in one sentence — confirmDossierOrder)
 */

/** Structured order brief (pipeline/dossier_brief.Brief) — written by the
 *  worker's intake before the first search step. */
export interface DossierBrief {
  questionType: "technology" | "landscape" | "regulatory" | "market" | "evidence";
  decision: string;
  reader: string;
  constraints: string[];
  mustAnswer: string[];
  artefact: "dossier" | "dossier+advisor";
  isQuestion: boolean;
  rejectionReason: string;
}

/** Field profile (corpus_research.TopicProfile) — the search directions. */
/** Who publishes the authoritative facts of the field (Stufe 2, 2026-09-19). */
export interface DossierSourceClass {
  kind: string;
  name: string;
  hosts: string[];
}

export interface DossierFieldProfile {
  field: string;
  regulators: string[];
  eventTypes: string[];
  actorTypes: string[];
  actorSeeds: string[];
  sourceClasses: DossierSourceClass[];
}

export interface DossierPlan {
  title: string;
  steps: { title: string; query: string }[];
  /** Landscape mode: sub-fields with corpus counts (empty otherwise). */
  landscape: { name: string; signals?: number }[];
}

export interface DossierOrder {
  id: number;
  slug: string;
  topic: string;
  question: string | null;
  status:
    | "queued"
    | "running"
    | "awaiting_confirmation"
    | "review"
    | "done"
    | "failed"
    | "cancelled";
  error: string | null;
  check: DossierCheck | null;
  dossierVersion: number | null;
  createdAt: string | null;
  finishedAt: string | null;
  /** Stage 1 intake artefacts (null on orders that predate it). */
  brief: DossierBrief | null;
  profile: DossierFieldProfile | null;
  plan: DossierPlan | null;
  confirmedAt: string | null;
  ownerNote: string | null;
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
  /** The reader's verdict (same model, adversarial system prompt): null = not run. */
  reader_ok?: boolean | null;
  seconds?: number;
}

export interface DossierSeries {
  slug: string;
  topic: string | null;
  versions: number;
  latestVersion: number;
  latestAt: string | null;
}

/** Evidence mix of one run, as scripts/corpus_research.py counts it. */
/** "legal" = regulatory/IP sweep, "market" = market/reimbursement sweep,
 * "entity" = second wave (<actor> <event type>, 2026-09-07), "funding" = the
 * funding sweep (R10-4, 2026-09-07: jury_16 scored coverage 5:9 because the
 * funding level of the innovation chain had no query direction of its own).
 * All four are fixed query patterns, fetched in full. */
export type EvidenceKind =
  | "article"
  | "signal"
  | "paper"
  | "patent"
  | "web"
  | "legal"
  | "market"
  | "entity"
  | "funding";

/** Provenance header of a run — what the report is a snapshot OF. */
export interface DossierProvenance {
  finishedAt: string | null;
  kinds: Record<EvidenceKind, number>;
  sources: number;
  cited: number;
  stripped: number;
  retrieval: string | null;
  scope: string | null;
  seconds: number | null;
  lang: string | null;
  /** pipeline/dossier_quant.py summary (null: run without measurement). */
  quant: Record<string, unknown> | null;
}

/** One swept item and where the run looked for it (coverage ledger).
 *
 * `kind` since 2026-09-07: the sweep no longer runs only on audit gaps —
 * "plan" rows are plan steps the run swept regardless of the audit, "followup"
 * rows are gaps only the re-audit could name, "legal" rows are the fixed
 * regulatory/IP query patterns and "market" rows the fixed market/reimbursement
 * patterns (2026-09-07, jury_4.md). Older rows carry no kind and default to
 * "gap". Only "gap"/"followup" rows are open questions. */
export type DossierLedgerKind =
  | "gap"
  | "plan"
  | "followup"
  | "legal"
  | "market"
  | "entity"
  | "funding";

export interface DossierLedgerRow {
  gap: string;
  kind: DossierLedgerKind;
  papers: number;
  patents: number;
  webQueries: string[];
  webSources: number;
  webFetched: number;
  offTopicDropped: number;
  /** Usable hits the run did NOT admit because a budget was full — the
   * Askea failure ("8 hits, 0 new") made visible (2026-09-07). */
  budgetDropped: number;
  /** Why each page could not be read: robots | blocked | timeout | too_short
   * | tdm | budget. Only non-"fetched" statuses are kept. */
  unreadable: string[];
}

/**
 * Corpus evidence of a run (pipeline/dossier_corpus_evidence.py, scouting
 * rebuild 2026-09-19): our own deterministic pass over the corpus BEFORE any
 * model hop — signals per tier and quarter (count + share per 10,000 of that
 * tier), actors, outlets, representative catalog ids and the areas that were
 * thin (the only ones the web stage ran for). Null: run before the rebuild or
 * the pass was not measured.
 */
export interface DossierCorpusCell {
  n: number;
  per10k: number | null;
}

export interface DossierCorpusEvidence {
  ok: boolean;
  reason: string | null;
  terms: string[];
  since: string;
  measuredOn: string;
  nSignals: number;
  nSignals12m: number;
  quarters: string[];
  /** tier → quarter → cell, tiers in innovation-chain order */
  tiers: { tier: string; cells: DossierCorpusCell[]; total12m: number }[];
  actors: { name: string; n: number; first: string | null; last: string | null }[];
  sources: { name: string; n: number }[];
  representative: { id: string; kind: string; tier: string | null; title: string; date: string; outlet: string; why: string }[];
  regulatory12m: number;
  /** Runde 28: erweiterter Satz — ein Themenbegriff plus Produkt-/Akteursname (Profil, Pflichtpunkte). */
  extraTerms: string[];
  nSignalsExtended: number;
  nSignalsExtended12m: number;
  extendedHits: { name: string; n: number }[];
  thinAreas: { area: string; kind: string; reason: string }[];
}

export interface DossierWebGating {
  corpusEvidenceOk: boolean;
  webGaps: number;
  corpusOnlyGaps: number;
  sweeps: { name: string; ran: boolean }[];
  webBudget: number;
  webSteps: number;
}

export interface DossierDoc {
  slug: string;
  version: number;
  topic: string | null;
  question: string;
  /** The report's own `# Title` line, if it has one. */
  reportTitle: string | null;
  /** Report Markdown without that title line (the page renders the h1). */
  reportMd: string;
  /** Run record below the separator — shown in the desk, never delivered. */
  auditAnnex: string;
  createdAt: string | null;
  model: string | null;
  provenance: DossierProvenance;
  ledger: DossierLedgerRow[];
  /** Scouting rebuild (2026-09-19): corpus-first evidence block + web gating. */
  corpusEvidence: DossierCorpusEvidence | null;
  webGating: DossierWebGating | null;
  outline: string | null;
}

const TIER_ORDER = ["science", "patent", "funding", "market"];

export function parseCorpusEvidence(raw: unknown): DossierCorpusEvidence | null {
  if (!raw || typeof raw !== "object") return null;
  const r = raw as Record<string, unknown>;
  const quarters = Array.isArray(r.quarters) ? r.quarters.map(String) : [];
  const byTier = (r.signals_by_tier_quarter ?? {}) as Record<string, Record<string, Record<string, unknown>>>;
  const totals = (r.tier_totals_12m ?? {}) as Record<string, unknown>;
  const tiers = TIER_ORDER.filter((t) => t in byTier || t in totals).map((tier) => ({
    tier,
    total12m: num(totals[tier]) ?? 0,
    cells: quarters.map((q) => {
      const c = byTier[tier]?.[q] ?? {};
      return { n: num(c.n) ?? 0, per10k: num(c.per_10k) };
    }),
  }));
  const list = <T,>(v: unknown, f: (x: Record<string, unknown>) => T): T[] =>
    Array.isArray(v) ? v.filter((x) => x && typeof x === "object").map((x) => f(x as Record<string, unknown>)) : [];
  return {
    ok: Boolean(r.ok),
    reason: r.reason ? String(r.reason) : null,
    terms: Array.isArray(r.terms) ? r.terms.map(String) : [],
    since: String(r.since ?? ""),
    measuredOn: String(r.measured_on ?? ""),
    nSignals: num(r.n_signals) ?? 0,
    nSignals12m: num(r.n_signals_12m) ?? 0,
    quarters,
    tiers,
    actors: list(r.actors, (a) => ({
      name: String(a.name ?? ""), n: num(a.n) ?? 0,
      first: a.first ? String(a.first) : null, last: a.last ? String(a.last) : null,
    })),
    sources: list(r.sources, (a) => ({ name: String(a.name ?? ""), n: num(a.n) ?? 0 })),
    representative: list(r.representative, (a) => ({
      id: String(a.id ?? ""), kind: String(a.kind ?? ""), tier: a.tier ? String(a.tier) : null,
      title: String(a.title ?? ""), date: String(a.date ?? ""), outlet: String(a.outlet ?? ""),
      why: String(a.why ?? ""),
    })),
    regulatory12m: num(r.regulatory_12m) ?? 0,
    extraTerms: Array.isArray(r.extra_terms) ? r.extra_terms.map(String) : [],
    nSignalsExtended: num(r.n_signals_extended) ?? 0,
    nSignalsExtended12m: num(r.n_signals_extended_12m) ?? 0,
    extendedHits: list(r.extended_hits, (a) => ({ name: String(a.name ?? ""), n: num(a.n) ?? 0 })),
    thinAreas: list(r.thin_areas, (a) => ({
      area: String(a.area ?? ""), kind: String(a.kind ?? ""), reason: String(a.reason ?? ""),
    })),
  };
}

export function parseWebGating(raw: unknown): DossierWebGating | null {
  if (!raw || typeof raw !== "object") return null;
  const r = raw as Record<string, unknown>;
  const sweeps = (r.sweeps ?? {}) as Record<string, unknown>;
  return {
    corpusEvidenceOk: Boolean(r.corpus_evidence_ok),
    webGaps: Array.isArray(r.web_gaps) ? r.web_gaps.length : 0,
    corpusOnlyGaps: Array.isArray(r.corpus_only_gaps) ? r.corpus_only_gaps.length : 0,
    sweeps: ["regulatory", "market", "funding", "catalyst"].map((name) => ({ name, ran: Boolean(sweeps[name]) })),
    webBudget: num(r.web_budget) ?? 0,
    webSteps: num(r.web_steps) ?? 0,
  };
}

/**
 * Utility U of one run (pipeline/dossier_utility.py, plan stage 0): stored per
 * dossiers.id in dossier_run_outcomes by the worker and by
 * `scripts/dossier_eval.py --backfill`. "delivery-ready" is the third light
 * next to end-control and reader: reader answers ∧ no contradiction ∧ fact
 * density ≥ floor ∧ tables on topic. Missing row → the desk shows "—".
 */
export interface DossierOutcome {
  slug: string;
  version: number;
  utility: number | null;
  deliveryReady: boolean;
  readerAnswers: boolean | null;
  signedOff: boolean;
  densityNorm: number | null;
  primaryShare: number | null;
}

export function outcomeKey(slug: string, version: number): string {
  return `${slug}:${version}`;
}

/** All outcome rows keyed by slug:version — 50-odd rows, one query. */
export async function listDossierOutcomes(): Promise<Map<string, DossierOutcome>> {
  const map = new Map<string, DossierOutcome>();
  try {
    const t = await q1<{ t: string | null }>(
      `SELECT to_regclass('public.dossier_run_outcomes')::text AS t`
    );
    if (!t?.t) return map;
    const rows = await q<{
      slug: string;
      version: number;
      utility: number | null;
      delivery_ready: boolean;
      reader_answers: boolean | null;
      signed_off: boolean;
      density: string | null;
      primary: string | null;
    }>(
      `SELECT slug, version, utility, delivery_ready, reader_answers, signed_off,
              components->>'density_norm' AS density,
              components->>'primary_share' AS primary
         FROM dossier_run_outcomes`
    );
    for (const r of rows) {
      map.set(outcomeKey(r.slug, Number(r.version)), {
        slug: r.slug,
        version: Number(r.version),
        utility: num(r.utility),
        deliveryReady: Boolean(r.delivery_ready),
        readerAnswers: r.reader_answers === null || r.reader_answers === undefined
          ? null
          : Boolean(r.reader_answers),
        signedOff: Boolean(r.signed_off),
        densityNorm: num(r.density),
        primaryShare: num(r.primary),
      });
    }
  } catch {
    /* table missing or DB down: the desk shows "—" */
  }
  return map;
}

export async function getDossierOutcome(
  slug: string,
  version: number
): Promise<DossierOutcome | null> {
  const all = await listDossierOutcomes();
  return all.get(outcomeKey(slug, version)) ?? null;
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
      reader_ok: o.reader_ok === undefined || o.reader_ok === null ? null : Boolean(o.reader_ok),
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
  brief_json: unknown;
  profile_json: unknown;
  plan_json: unknown;
  confirmed_at: string | null;
  owner_note: string | null;
}

function strList(v: unknown): string[] {
  return Array.isArray(v) ? v.map((x) => String(x ?? "").trim()).filter(Boolean) : [];
}

function asObject(raw: unknown): Record<string, unknown> | null {
  if (!raw) return null;
  try {
    const o = typeof raw === "string" ? JSON.parse(raw) : raw;
    return o && typeof o === "object" && !Array.isArray(o) ? (o as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

function parseBrief(raw: unknown): DossierBrief | null {
  const o = asObject(raw);
  if (!o) return null;
  const qt = String(o.question_type ?? "technology");
  const art = String(o.artefact ?? "dossier");
  return {
    questionType: (["technology", "landscape", "regulatory", "market", "evidence"].includes(qt)
      ? qt
      : "technology") as DossierBrief["questionType"],
    decision: String(o.decision ?? ""),
    reader: String(o.reader ?? ""),
    constraints: strList(o.constraints),
    mustAnswer: strList(o.must_answer),
    artefact: art === "dossier+advisor" ? "dossier+advisor" : "dossier",
    isQuestion: o.is_question === undefined ? true : Boolean(o.is_question),
    rejectionReason: String(o.rejection_reason ?? ""),
  };
}

function parseProfile(raw: unknown): DossierFieldProfile | null {
  const o = asObject(raw);
  if (!o) return null;
  return {
    field: String(o.field ?? ""),
    regulators: strList(o.regulators),
    eventTypes: strList(o.event_types),
    actorTypes: strList(o.actor_types),
    actorSeeds: strList(o.actor_seeds),
    sourceClasses: (Array.isArray(o.source_classes) ? o.source_classes : [])
      .map((x) => asObject(x))
      .filter((x): x is Record<string, unknown> => x !== null)
      .map((x) => ({
        kind: String(x.kind ?? "other"),
        name: String(x.name ?? ""),
        hosts: strList(x.hosts),
      }))
      .filter((x) => x.name.length > 0),
  };
}

function parsePlan(raw: unknown): DossierPlan | null {
  const o = asObject(raw);
  if (!o) return null;
  const steps = Array.isArray(o.steps)
    ? o.steps
        .map((st) => asObject(st))
        .filter((st): st is Record<string, unknown> => st !== null)
        .map((st) => ({ title: String(st.title ?? ""), query: String(st.query ?? "") }))
    : [];
  const landscape = Array.isArray(o.landscape)
    ? o.landscape
        .map((r) => asObject(r))
        .filter((r): r is Record<string, unknown> => r !== null)
        .map((r) => ({ name: String(r.name ?? ""), signals: num(r.signals) ?? undefined }))
    : [];
  return { title: String(o.title ?? ""), steps, landscape };
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
    brief: parseBrief(r.brief_json),
    profile: parseProfile(r.profile_json),
    plan: parsePlan(r.plan_json),
    confirmedAt: r.confirmed_at ? String(r.confirmed_at) : null,
    ownerNote: r.owner_note ?? null,
  };
}

const ORDER_SELECT = `SELECT id, slug, topic, question, status, error, check_json,
              dossier_version, created_at::text, finished_at::text,
              brief_json, profile_json, plan_json, confirmed_at::text, owner_note
         FROM dossier_orders`;

export async function listDossierOrders(limit = 60): Promise<DossierOrder[]> {
  try {
    const rows = await q<OrderRow>(`${ORDER_SELECT} ORDER BY id DESC LIMIT $1`, [limit]);
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
      `${ORDER_SELECT}
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

// Vollstaendig, in der Reihenfolge der Herkunftszeile. "entity" fehlte hier
// seit der zweiten Welle — die Zaehlung kam aus Python, wurde aber nie
// angezeigt; "funding" kam mit R10-4 dazu.
const KINDS: EvidenceKind[] = [
  "article",
  "signal",
  "paper",
  "patent",
  "web",
  "legal",
  "market",
  "entity",
  "funding",
];

function num(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function parseKinds(raw: unknown): Record<EvidenceKind, number> {
  const o = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
  return Object.fromEntries(KINDS.map((k) => [k, num(o[k]) ?? 0])) as Record<
    EvidenceKind,
    number
  >;
}

function parseLedger(raw: unknown): DossierLedgerRow[] {
  if (!Array.isArray(raw)) return [];
  return raw.map((row) => {
    const o = row && typeof row === "object" ? (row as Record<string, unknown>) : {};
    const kind = String(o.kind ?? "gap");
    return {
      gap: String(o.gap ?? ""),
      kind: (kind === "plan" || kind === "followup" || kind === "legal"
        || kind === "market" || kind === "entity"
        ? kind
        : "gap") as DossierLedgerKind,
      papers: num(o.papers) ?? 0,
      patents: num(o.patents) ?? 0,
      webQueries: Array.isArray(o.web_queries) ? o.web_queries.map(String) : [],
      webSources: num(o.web_sources) ?? 0,
      webFetched: num(o.web_fetched) ?? 0,
      offTopicDropped: num(o.off_topic_dropped) ?? 0,
      budgetDropped: num(o.budget_dropped) ?? 0,
      unreadable: Array.isArray(o.fetch_log)
        ? [
            ...new Set(
              o.fetch_log
                .map((e) =>
                  e && typeof e === "object"
                    ? String((e as Record<string, unknown>).status ?? "")
                    : "",
                )
                .filter((st) => st && st !== "fetched"),
            ),
          ].sort()
        : [],
    };
  });
}

/**
 * Separator between the DELIVERED dossier and the audit annex — textually
 * identical to `pipeline.dossier_structure.AUDIT_ANNEX_MARK`. Everything above
 * it is the document the customer gets (report + sources + measurement
 * appendix); everything below is the run record (search protocol, fetch log,
 * budget notes). Two blind reviews on 2026-09-07 measured 2,563 of 6,775 words
 * as pure protocol and called it dilution — so the desk shows it separately
 * instead of inside the report.
 */
export const AUDIT_ANNEX_MARK = "<!-- catandary:audit-annex -->";

/** Cut a stored document into the delivered part and the audit annex. */
export function splitAuditAnnex(md: string): { delivered: string; annex: string } {
  const i = md.indexOf(AUDIT_ANNEX_MARK);
  if (i < 0) return { delivered: md, annex: "" };
  return {
    delivered: md.slice(0, i).trimEnd(),
    annex: md.slice(i + AUDIT_ANNEX_MARK.length).trim(),
  };
}

/** Split a leading `# Title` off the report so the page owns the h1. */
export function splitReportTitle(md: string): { title: string | null; body: string } {
  const m = /^\s*#\s+(.+?)\s*#*\s*(?:\r?\n|$)/.exec(md);
  if (!m) return { title: null, body: md };
  return { title: m[1].trim(), body: md.slice(m[0].length).replace(/^\s*\n/, "") };
}

// The result JSON also carries the full evidence notes, the trace and the
// raw report — several hundred KB per run. Only the provenance paths are
// read here; the report body is the one big column the page needs.
const DOC_SELECT = `SELECT slug, version, topic, question, report_md, model,
         created_at::text AS created_at,
         result->'kinds'                                     AS kinds,
         jsonb_array_length(coalesce(result->'sources', '[]')) AS n_sources,
         jsonb_array_length(coalesce(result->'cited',   '[]')) AS n_cited,
         result->>'stripped_citations'                       AS stripped,
         result->>'retrieval' AS retrieval, result->>'scope' AS scope,
         result->>'seconds'   AS seconds,   result->>'finished_at' AS finished_at,
         result->>'lang'      AS lang,      result->'quant' AS quant,
         result->'ledger'     AS ledger,
         result->'corpus_evidence' AS corpus_evidence,
         result->'web_gating' AS web_gating,
         result->>'outline'   AS outline
    FROM dossiers`;

function toDoc(r: Record<string, unknown>): DossierDoc {
  const { delivered, annex } = splitAuditAnnex(String(r.report_md ?? ""));
  const { title, body } = splitReportTitle(delivered);
  const quant =
    r.quant && typeof r.quant === "object" ? (r.quant as Record<string, unknown>) : null;
  return {
    slug: String(r.slug),
    version: Number(r.version),
    topic: r.topic ? String(r.topic) : null,
    question: String(r.question ?? ""),
    reportTitle: title,
    reportMd: body,
    auditAnnex: annex,
    createdAt: r.created_at ? String(r.created_at) : null,
    model: r.model ? String(r.model) : null,
    provenance: {
      finishedAt: r.finished_at ? String(r.finished_at) : null,
      kinds: parseKinds(r.kinds),
      sources: num(r.n_sources) ?? 0,
      cited: num(r.n_cited) ?? 0,
      stripped: num(r.stripped) ?? 0,
      retrieval: r.retrieval ? String(r.retrieval) : null,
      scope: r.scope ? String(r.scope) : null,
      seconds: num(r.seconds),
      lang: r.lang ? String(r.lang) : null,
      quant,
    },
    ledger: parseLedger(r.ledger),
    corpusEvidence: parseCorpusEvidence(r.corpus_evidence),
    webGating: parseWebGating(r.web_gating),
    outline: r.outline ? String(r.outline) : null,
  };
}

export async function getDossier(
  slug: string,
  version?: number
): Promise<DossierDoc | null> {
  try {
    const r = version
      ? await q1<Record<string, unknown>>(
          `${DOC_SELECT} WHERE slug = $1 AND version = $2`,
          [slug, version]
        )
      : await q1<Record<string, unknown>>(
          `${DOC_SELECT} WHERE slug = $1 ORDER BY version DESC LIMIT 1`,
          [slug]
        );
    return r ? toDoc(r) : null;
  } catch {
    return null;
  }
}

/** Mirror of pipeline.dossier_orders.slugify — one series per topic. */
export function slugifyTopic(text: string): string {
  const ascii = text
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
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
  /** CPC anchor for the patent measurement (e.g. H01M4/5825); empty = cascade guesses. */
  cpc?: string;
}): Promise<number | null> {
  const topic = input.topic.trim();
  if (!topic || !ORDERABLE.test(topic)) return null;
  const slug = slugifyTopic(input.slug?.trim() || topic);
  const question = input.question?.trim() || null;
  const cpc = (input.cpc ?? "").replace(/\s+/g, "").toUpperCase();
  // Desk orders pause at the owner checkpoint (stage 1); CLI orders do not.
  const params = JSON.stringify({
    checkpoint: true,
    ...(input.quant ? {} : { quant: false }),
    ...(cpc && /^[A-H]\d{2}[A-Z]\d{1,4}\/\d{1,6}$/.test(cpc) ? { cpc } : {}),
  });
  const row = await q1<{ id: number }>(
    `INSERT INTO dossier_orders (slug, topic, question, params_json)
     VALUES ($1, $2, $3, $4) RETURNING id`,
    [slug, topic, question, params]
  );
  return row?.id ?? null;
}

/**
 * "Neu rechnen": a fresh order slip for an existing series — same slug, same
 * topic/question/params as its latest order, so the run lands as the next
 * version. Series that only ever ran from the CLI (no order slip) are
 * re-ordered from the stored dossier's topic and question; a company-mode
 * run (--company) is then re-run as a topic dossier on that question.
 */
export async function createRerunOrder(slug: string): Promise<number | null> {
  if (!/^[a-z0-9-]{1,80}$/.test(slug)) return null;
  const last = await q1<{ topic: string; question: string | null; params_json: string }>(
    `SELECT topic, question, params_json FROM dossier_orders
      WHERE slug = $1 ORDER BY id DESC LIMIT 1`,
    [slug]
  );
  let topic: string;
  let question: string | null;
  let params = "{}";
  if (last) {
    ({ topic, question } = last);
    params = last.params_json || "{}";
    // A recompute from the desk pauses at the checkpoint like a new desk order,
    // even if the series was first ordered from the CLI.
    try {
      params = JSON.stringify({ ...JSON.parse(params), checkpoint: true });
    } catch {
      params = JSON.stringify({ checkpoint: true });
    }
  } else {
    const d = await q1<{ topic: string | null; question: string }>(
      `SELECT topic, question FROM dossiers WHERE slug = $1
        ORDER BY version DESC LIMIT 1`,
      [slug]
    );
    if (!d) return null;
    topic = d.topic?.trim() || slug;
    question = d.question?.trim() || null;
  }
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
  return transition(id, ["queued", "awaiting_confirmation"], "cancelled");
}

/**
 * Owner checkpoint (stage 1): confirm the intake — with an optional one-sentence
 * correction. Mirrors pipeline.dossier_orders.confirm: the note is stored on the
 * slip; the worker appends it to the question as "Owner correction: …" and
 * recomputes brief/profile/plan (an empty note reuses the stored ones).
 */
export async function confirmDossierOrder(id: number, note: string): Promise<boolean> {
  const clean = note.split(/\s+/).filter(Boolean).join(" ").slice(0, 1000) || null;
  const rows = await q<{ id: number }>(
    `UPDATE dossier_orders
        SET status = 'queued', confirmed_at = now(), owner_note = $2
      WHERE id = $1 AND status = 'awaiting_confirmation' RETURNING id`,
    [id, clean]
  );
  return rows.length === 1;
}

export async function requeueDossierOrder(id: number): Promise<boolean> {
  return transition(id, ["failed"], "queued");
}
