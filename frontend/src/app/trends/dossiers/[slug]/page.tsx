import Link from "next/link";
import { notFound } from "next/navigation";
import MarkdownBody from "@/components/MarkdownBody";
import { canManageDossiers } from "@/lib/dossier-access";
import { workerStatus } from "@/lib/dossierWorker";
import {
  getDossier,
  getDossierOutcome,
  getOrderForVersion,
  listVersions,
  type DossierProvenance,
  type DossierLedgerRow,
  type DossierCorpusEvidence,
  type DossierWebGating,
} from "@/lib/dossiers";
import { approveAction, createAdvisoryAction, rerunSeriesAction, runAdvisoryAction } from "../actions";
import { listAdvisoryNotes, PROFILE_FIELDS } from "@/lib/advisory";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Dossier",
  robots: { index: false, follow: false },
};

/**
 * Owner reading view for one dossier series (#95): provenance header (what
 * the report is a snapshot OF), the agent's end-control, the report itself,
 * the coverage ledger (where the run looked for what it could not find), and
 * every earlier version one click away — "what changed since the last run"
 * is itself the signal the versioning exists for. "Recompute" writes a new
 * order slip for the series and starts the worker.
 */

const KIND_LABEL: Record<keyof DossierProvenance["kinds"], string> = {
  article: "corpus articles",
  signal: "signals",
  paper: "papers",
  patent: "patents",
  web: "web",
  legal: "regulatory/IP",
  market: "market/reimbursement",
  entity: "actor/event",
  funding: "funding",
};

function fmtDate(ts: string | null): string {
  return ts ? ts.slice(0, 16).replace("T", " ") : "—";
}

function fmtDuration(s: number | null): string {
  if (s === null) return "—";
  const m = Math.floor(s / 60);
  return m > 0 ? `${m} min ${Math.round(s - m * 60)} s` : `${Math.round(s)} s`;
}

function QuantLine({ quant }: { quant: Record<string, unknown> | null }) {
  if (!quant) return <span>no measurement block</span>;
  if (quant.off_topic) return <span>measurement: phrase resolved to no patent class</span>;
  const parts: string[] = [];
  if (typeof quant.verdict === "string") parts.push(quant.verdict);
  if (typeof quant.direction === "string") parts.push(quant.direction);
  if (typeof quant.K_median === "number") parts.push(`TIR k̃ ${quant.K_median.toFixed(3)}`);
  if (typeof quant.lead_science_market === "number")
    parts.push(`science→market ${quant.lead_science_market} y`);
  if (typeof quant.lead_patent_market === "number")
    parts.push(`patent→market ${quant.lead_patent_market} y`);
  if (quant.established) parts.push("established field");
  return <span>measurement: {parts.length ? parts.join(" · ") : "present"}</span>;
}

function Provenance({ p, question, model }: { p: DossierProvenance; question: string; model: string | null }) {
  const mix = (Object.keys(KIND_LABEL) as (keyof typeof KIND_LABEL)[])
    .filter((k) => p.kinds[k] > 0)
    .map((k) => `${p.kinds[k]} ${KIND_LABEL[k]}`)
    .join(" · ");
  return (
    <section className="mt-6 border border-border bg-card px-5 py-4">
      <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">
        Provenance
      </p>
      <dl className="mt-3 grid gap-x-6 gap-y-2 text-[13px] leading-[1.6] md:grid-cols-[max-content_1fr]">
        <dt className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">Question</dt>
        <dd className="text-text">{question}</dd>
        <dt className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">Evidence</dt>
        <dd className="text-text">
          {mix || "—"}
          <span className="text-muted">
            {" "}
            — {p.cited} of {p.sources} cited, {p.stripped} citation(s) stripped
          </span>
        </dd>
        <dt className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">Measurement</dt>
        <dd className="text-text">
          <QuantLine quant={p.quant} />
        </dd>
        <dt className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">Run</dt>
        <dd className="text-muted">
          {fmtDate(p.finishedAt)} UTC · {model ?? "local model"} · retrieval {p.retrieval ?? "—"}/
          {p.scope ?? "—"} · {fmtDuration(p.seconds)} · report {p.lang ?? "en"} · strictly local
        </dd>
      </dl>
    </section>
  );
}

/**
 * Corpus evidence (scouting rebuild, 2026-09-19): what OUR corpus holds on the
 * topic per tier and quarter, who moves in it and which outlets carry it —
 * rendered above the report, because the report is built from this block
 * first and the web only filled the areas listed as thin.
 */
function CorpusEvidence({ ev, gating }: { ev: DossierCorpusEvidence; gating: DossierWebGating | null }) {
  const label = "font-mono text-[10px] uppercase tracking-[0.14em] text-muted";
  return (
    <section className="mt-6 border border-border bg-card px-5 py-4">
      <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">
        Corpus evidence · signals matching all of {ev.terms.join(", ") || "—"} since {ev.since || "—"}
        <span className="text-paper"> · {ev.nSignals.toLocaleString("en-US")}</span>
        <span> ({ev.nSignals12m.toLocaleString("en-US")} in 12 months)</span>
      </p>
      {ev.ok ? (
        <>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full border-collapse text-left text-[12px] leading-[1.5]">
              <thead>
                <tr className="border-b border-border font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
                  <th className="py-1 pr-3 font-normal">Tier</th>
                  {ev.quarters.map((q) => (
                    <th key={q} className="px-2 py-1 font-normal">{q}</th>
                  ))}
                  <th className="px-2 py-1 font-normal">12 m</th>
                </tr>
              </thead>
              <tbody>
                {ev.tiers.map((t) => (
                  <tr key={t.tier} className="border-b border-border last:border-b-0">
                    <td className="py-1 pr-3 font-mono text-[11px] text-paper">{t.tier}</td>
                    {t.cells.map((c, i) => (
                      <td key={i} className="px-2 py-1 font-mono text-[11px] text-text" title="count (share per 10,000 of this tier in that quarter)">
                        {c.n}
                        <span className="text-muted">{c.per10k === null ? " (—)" : ` (${c.per10k}/10k)`}</span>
                      </td>
                    ))}
                    <td className="px-2 py-1 font-mono text-[11px] text-paper">{t.total12m}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <dl className="mt-3 grid gap-x-6 gap-y-2 text-[13px] leading-[1.6] md:grid-cols-[max-content_1fr]">
            <dt className={label}>Actors</dt>
            <dd className="text-text">
              {ev.actors.length > 0
                ? ev.actors.map((a) => `${a.name} ×${a.n}`).join(" · ")
                : "none extracted on these signals (extraction runs only on the article path)"}
            </dd>
            <dt className={label}>Outlets</dt>
            <dd className="text-text">{ev.sources.length > 0 ? ev.sources.map((s) => `${s.name} ×${s.n}`).join(" · ") : "—"}</dd>
            <dt className={label}>Representative</dt>
            <dd className="text-muted">
              {ev.representative.length > 0
                ? ev.representative.map((r) => `${r.id} · ${r.tier ?? "?"} · ${r.date || "—"}`).join(" · ")
                : "none"}
              {ev.regulatory12m > 0 && ` — ${ev.regulatory12m} regulation/decision signal(s) in 12 months`}
            </dd>
            <dt className={label}>Thin</dt>
            <dd className="text-text">
              {ev.thinAreas.length > 0
                ? ev.thinAreas.map((t) => (t.kind === "must" ? t.area.slice(0, 60) : t.area)).join(" · ")
                : "nothing — no web research was needed"}
              {gating && (
                <span className="text-muted">
                  {" "}
                  — web: {gating.webGaps} gap(s), {gating.corpusOnlyGaps} corpus-only, sweeps{" "}
                  {gating.sweeps.filter((s) => s.ran).map((s) => s.name).join("/") || "none"}, budget{" "}
                  {gating.webBudget}/{gating.webSteps}
                </span>
              )}
            </dd>
          </dl>
        </>
      ) : (
        <p className="mt-2 font-sans text-[13px] text-muted">
          not measured{ev.reason ? ` (${ev.reason})` : ""} — every area counted as thin, the web stage ran as before the rebuild
        </p>
      )}
    </section>
  );
}

const LEDGER_KIND_LABEL: Record<string, string> = {
  gap: "audit gap",
  plan: "plan step",
  followup: "re-audit gap",
  legal: "regulatory/IP",
  market: "market/reimbursement",
  entity: "actor/event (2nd wave)",
  funding: "funding",
};

function Ledger({ rows }: { rows: DossierLedgerRow[] }) {
  if (rows.length === 0) return null;
  // Plan steps and the fixed regulatory/IP patterns are swept regardless of
  // the audit (2026-09-07) — counting them as "audited gaps" would overstate
  // what the run left open. Same rule as pipeline/dossier_check.py.
  const gaps = rows.filter(
    (r) =>
      r.kind !== "plan" &&
      r.kind !== "legal" &&
      r.kind !== "market" &&
      r.kind !== "entity" &&
      r.kind !== "funding",
  ).length;
  const plans = rows.filter((r) => r.kind === "plan").length;
  const legal = rows.filter((r) => r.kind === "legal").length;
  const market = rows.filter((r) => r.kind === "market").length;
  const entity = rows.filter((r) => r.kind === "entity").length;
  const funding = rows.filter((r) => r.kind === "funding").length;
  return (
    <details className="mt-10 border border-border">
      <summary className="cursor-pointer px-5 py-3 font-mono text-[11px] uppercase tracking-[0.16em] text-muted hover:text-paper">
        Coverage ledger · {gaps} audited gap(s)
        {plans > 0 ? ` + ${plans} plan step(s)` : ""}
        {legal > 0 ? ` + ${legal} regulatory/IP pattern(s)` : ""}
        {market > 0 ? ` + ${market} market/reimbursement pattern(s)` : ""}
        {entity > 0 ? ` + ${entity} actor/event query(s)` : ""}
        {funding > 0 ? ` + ${funding} funding pattern(s)` : ""} —
        where the run looked
      </summary>
      <div className="overflow-x-auto border-t border-border">
        <table className="w-full border-collapse text-left text-[13px] leading-[1.55]">
          <thead>
            <tr className="border-b border-border bg-card font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
              <th className="px-4 py-2 font-normal">Gap</th>
              <th className="px-3 py-2 font-normal">Papers</th>
              <th className="px-3 py-2 font-normal">Patents</th>
              <th className="px-3 py-2 font-normal">Web hits</th>
              <th className="px-3 py-2 font-normal">Fetched</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className="border-b border-border align-top last:border-b-0">
                <td className="px-4 py-3 text-text">
                  <span className="mr-2 font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
                    [{LEDGER_KIND_LABEL[r.kind] ?? r.kind}]
                  </span>
                  {r.gap}
                  {r.offTopicDropped > 0 && (
                    <span className="ml-2 font-mono text-[11px] text-muted">
                      · {r.offTopicDropped} off-topic hit(s) dropped
                    </span>
                  )}
                  {r.budgetDropped > 0 && (
                    <span className="ml-2 font-mono text-[11px] text-muted">
                      · {r.budgetDropped} usable hit(s) not admitted (budget)
                    </span>
                  )}
                  {r.unreadable.length > 0 && (
                    <span className="ml-2 font-mono text-[11px] text-muted">
                      · unreadable: {r.unreadable.join(", ")}
                    </span>
                  )}
                  {r.webQueries.length > 0 && (
                    <ul className="mt-2 space-y-0.5 font-mono text-[11px] text-muted">
                      {r.webQueries.map((q, j) => (
                        <li key={j}>› {q}</li>
                      ))}
                    </ul>
                  )}
                </td>
                <td className="px-3 py-3 font-mono text-[12px] text-text">{r.papers}</td>
                <td className="px-3 py-3 font-mono text-[12px] text-text">{r.patents}</td>
                <td className="px-3 py-3 font-mono text-[12px] text-text">{r.webSources}</td>
                <td className="px-3 py-3 font-mono text-[12px] text-text">{r.webFetched}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

export default async function DossierPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  if (!canManageDossiers()) notFound();

  const { slug } = await params;
  if (!/^[a-z0-9-]{1,80}$/.test(slug)) notFound();
  const sp = await searchParams;
  const requested = typeof sp.v === "string" ? Number(sp.v) : NaN;
  const version = Number.isInteger(requested) && requested > 0 ? requested : undefined;

  const doc = await getDossier(slug, version);
  const advisoryNotes = await listAdvisoryNotes(slug);
  if (!doc) notFound();
  const [versions, order, outcome] = await Promise.all([
    listVersions(slug),
    getOrderForVersion(slug, doc.version),
    getDossierOutcome(slug, doc.version),
  ]);
  const check = order?.check ?? null;
  const workerBusy = workerStatus().running;
  const nextVersion = (versions[0]?.version ?? doc.version) + 1;

  const RECOMPUTE = (
    <form action={rerunSeriesAction}>
      <input type="hidden" name="slug" value={slug} />
      {workerBusy ? (
        <button
          disabled
          className="border border-border px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.16em] text-muted/60 cursor-not-allowed"
          title="a worker is running"
        >
          Recompute · v{nextVersion}
        </button>
      ) : (
        <button className="border border-border-strong px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.16em] text-muted hover:border-paper hover:text-paper">
          Recompute · v{nextVersion}
        </button>
      )}
    </form>
  );

  return (
    <div className="mx-auto max-w-3xl px-4 py-10">
      <header className="border-b border-border pb-6">
        <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-accent">
          Scouting dossier · owner desk
        </p>
        <h1 className="mt-3 font-display text-[32px] leading-[1.15] text-paper">
          {doc.reportTitle || doc.topic || doc.slug}
        </h1>
        {doc.reportTitle && doc.topic && (
          <p className="mt-2 font-mono text-[11px] uppercase tracking-[0.14em] text-muted">
            {doc.topic}
          </p>
        )}
        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 font-mono text-[11px] text-muted">
          <span className="text-paper">v{doc.version}</span>
          {doc.createdAt && <span>{fmtDate(doc.createdAt)}</span>}
          <span className="ml-auto flex items-center gap-3">
            <span className="flex gap-2">
              {versions.map((v) => (
                <Link
                  key={v.version}
                  href={`/trends/dossiers/${slug}?v=${v.version}`}
                  className={
                    v.version === doc.version ? "text-accent" : "text-muted hover:text-paper"
                  }
                >
                  v{v.version}
                </Link>
              ))}
            </span>
            {RECOMPUTE}
          </span>
        </div>
      </header>

      <Provenance p={doc.provenance} question={doc.question} model={doc.model} />

      {doc.corpusEvidence && <CorpusEvidence ev={doc.corpusEvidence} gating={doc.webGating} />}

      {check && (
        <aside className="mt-6 border border-border p-4">
          <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">
            Agent end-control{" "}
            {check.ok ? (
              <span className="text-accent">clean</span>
            ) : (
              <span className="text-warn">{check.findings.length} finding(s)</span>
            )}
            {check.reader_ok !== null && check.reader_ok !== undefined && (
              <>
                {" · reader "}
                {check.reader_ok ? (
                  <span className="text-accent">no major objection</span>
                ) : (
                  <span className="text-warn">objects</span>
                )}
              </>
            )}
            <span className="text-muted">
              {" "}
              · {check.cited}/{check.sources} sources cited · {check.words} words
              {check.open_questions > 0 && ` · ${check.open_questions} open question(s)`}
            </span>
            {/* Third light (plan stage 0): reader answers ∧ no contradiction ∧
                density ≥ floor ∧ tables on topic — pipeline/dossier_utility.py,
                stored in dossier_run_outcomes; "—" = no outcome row yet. */}
            {" · delivery "}
            {outcome ? (
              outcome.deliveryReady ? (
                <span className="text-accent">ready</span>
              ) : (
                <span className="text-warn">not ready</span>
              )
            ) : (
              <span className="text-muted">—</span>
            )}
            {outcome && (
              <span className="text-muted">
                {" "}
                · U {outcome.utility == null ? "—" : outcome.utility.toFixed(2)}
                {outcome.densityNorm != null && ` · density ${outcome.densityNorm.toFixed(2)}`}
                {outcome.primaryShare != null && ` · primary ${Math.round(outcome.primaryShare * 100)}%`}
              </span>
            )}
          </p>
          {check.findings.length > 0 && (
            <ul className="mt-2 list-disc pl-5 font-mono text-[11px] leading-[1.7] text-warn">
              {check.findings.map((f, i) => (
                <li key={i}>{f}</li>
              ))}
            </ul>
          )}
          {order?.status === "review" && (
            <form action={approveAction} className="mt-3">
              <input type="hidden" name="id" value={order.id} />
              <input type="hidden" name="slug" value={slug} />
              <button className="border border-accent px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.16em] text-accent hover:bg-accent hover:text-ink">
                Sign off this version
              </button>
            </form>
          )}
          {order?.status === "done" && (
            <p className="mt-2 font-mono text-[10px] uppercase tracking-[0.14em] text-paper">
              Signed off
            </p>
          )}
        </aside>
      )}

      {/* The Advisor (2026-09-14): options are written per client, from this
          dossier version, by a model in the consultant role with thinking on —
          and released only by a person. */}
      <aside className="mt-6 border border-border p-4">
        <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">
          Advisory notes for this dossier
        </p>
        {advisoryNotes.length > 0 ? (
          <ul className="mt-2 space-y-1 font-mono text-[11px] leading-[1.7]">
            {advisoryNotes.map((n) => (
              <li key={n.id} className="flex flex-wrap items-center gap-x-3">
                <Link href={`/trends/dossiers/${slug}/advisory/${n.id}`} className="text-paper hover:text-accent">
                  #{n.id} · v{n.dossierVersion} · {n.scope.slice(0, 70)}
                </Link>
                <span className={n.status === "approved" ? "text-accent" : n.status === "failed" ? "text-warn" : "text-muted"}>
                  {n.status}
                </span>
                {n.check && (
                  <span className="text-muted">
                    {n.check.ok ? "check clean" : "check objects"}
                    {n.check.reader_ok === true && " · reader ok"}
                    {n.check.reader_ok === false && " · reader objects"}
                  </span>
                )}
                {(n.status === "queued" || n.status === "failed") && (
                  <form action={runAdvisoryAction}>
                    <input type="hidden" name="id" value={n.id} />
                    <input type="hidden" name="slug" value={slug} />
                    <button className="text-accent hover:underline">run</button>
                  </form>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 font-sans text-[13px] text-muted">
            None yet. Describe the client and the decision on the table; the Advisor writes options from
            this dossier version only, and nothing is delivered before you approve it.
          </p>
        )}
        <details className="mt-4">
          <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-[0.16em] text-accent">
            New advisory note (v{doc.version})
          </summary>
          <form action={createAdvisoryAction} className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
            <input type="hidden" name="slug" value={slug} />
            <input type="hidden" name="version" value={doc.version} />
            {PROFILE_FIELDS.map(([k, label]) => (
              <label key={k} className={k === "notes" || k === "capabilities" ? "block md:col-span-2" : "block"}>
                <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">{label}</span>
                {k === "notes" || k === "capabilities" ? (
                  <textarea
                    name={k}
                    rows={2}
                    maxLength={1000}
                    className="mt-1 w-full border border-border-strong bg-transparent px-3 py-2 text-[13px] text-paper focus:border-accent focus:outline-none"
                  />
                ) : (
                  <input
                    name={k}
                    maxLength={300}
                    className="mt-1 w-full border border-border-strong bg-transparent px-3 py-2 text-[13px] text-paper focus:border-accent focus:outline-none"
                  />
                )}
              </label>
            ))}
            <label className="block md:col-span-2">
              <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
                Engagement scope — the decision on the table, what is in and out, budget and time (required)
              </span>
              <textarea
                name="scope"
                rows={3}
                required
                maxLength={4000}
                className="mt-1 w-full border border-border-strong bg-transparent px-3 py-2 text-[14px] text-paper focus:border-accent focus:outline-none"
              />
            </label>
            <label className="flex items-center gap-2 font-mono text-[11px] text-muted">
              <input type="checkbox" name="run" defaultChecked={!workerBusy} className="accent-current" />
              start the Advisor right away (27B, thinking on, ~10–20 min)
            </label>
            <div className="flex items-end justify-end">
              <button className="border border-accent px-4 py-2 font-mono text-[11px] uppercase tracking-[0.16em] text-accent hover:bg-accent hover:text-ink">
                Create note
              </button>
            </div>
          </form>
        </details>
      </aside>

      <article className="mt-8">
        <MarkdownBody source={doc.reportMd} />
      </article>

      <Ledger rows={doc.ledger} />

      {doc.auditAnnex && (
        <details className="mt-10 border-t border-border pt-4">
          <summary className="cursor-pointer font-mono text-[11px] uppercase tracking-[0.14em] text-muted hover:text-paper">
            Audit annex — run record, not part of the dossier
          </summary>
          <div className="mt-4 opacity-80">
            <MarkdownBody source={doc.auditAnnex} />
          </div>
        </details>
      )}

      <footer className="mt-10 flex flex-wrap items-center gap-4 border-t border-border pt-4">
        <Link
          href="/trends/dossiers"
          className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted hover:text-paper"
        >
          ← Dossier desk
        </Link>
        <span className="ml-auto">{RECOMPUTE}</span>
      </footer>
    </div>
  );
}
