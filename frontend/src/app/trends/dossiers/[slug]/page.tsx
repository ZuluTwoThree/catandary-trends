import Link from "next/link";
import { notFound } from "next/navigation";
import MarkdownBody from "@/components/MarkdownBody";
import { canManageDossiers } from "@/lib/dossier-access";
import { workerStatus } from "@/lib/dossierWorker";
import {
  getDossier,
  getOrderForVersion,
  listVersions,
  type DossierProvenance,
  type DossierLedgerRow,
} from "@/lib/dossiers";
import { approveAction, rerunSeriesAction } from "../actions";

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

const LEDGER_KIND_LABEL: Record<string, string> = {
  gap: "audit gap",
  plan: "plan step",
  followup: "re-audit gap",
};

function Ledger({ rows }: { rows: DossierLedgerRow[] }) {
  if (rows.length === 0) return null;
  // Plan steps are swept regardless of the audit (2026-09-07) — counting them
  // as "audited gaps" would overstate what the run left open.
  const gaps = rows.filter((r) => r.kind !== "plan").length;
  const plans = rows.length - gaps;
  return (
    <details className="mt-10 border border-border">
      <summary className="cursor-pointer px-5 py-3 font-mono text-[11px] uppercase tracking-[0.16em] text-muted hover:text-paper">
        Coverage ledger · {gaps} audited gap(s)
        {plans > 0 ? ` + ${plans} plan step(s)` : ""} — where the run looked
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
  if (!doc) notFound();
  const [versions, order] = await Promise.all([
    listVersions(slug),
    getOrderForVersion(slug, doc.version),
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

      {check && (
        <aside className="mt-6 border border-border p-4">
          <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">
            Agent end-control{" "}
            {check.ok ? (
              <span className="text-accent">clean</span>
            ) : (
              <span className="text-warn">{check.findings.length} finding(s)</span>
            )}
            <span className="text-muted">
              {" "}
              · {check.cited}/{check.sources} sources cited · {check.words} words
              {check.open_questions > 0 && ` · ${check.open_questions} open question(s)`}
            </span>
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

      <article className="mt-8">
        <MarkdownBody source={doc.reportMd} />
      </article>

      <Ledger rows={doc.ledger} />

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
