import Link from "next/link";
import {
  getResearchSignals, getResearchStats,
  getResearchCorpus, getResearchCorpusStats, getResearchTopics,
} from "@/lib/db";
import { MEGA_TRENDS } from "@/lib/mega-trends.generated";
import { parseResearchQuery } from "@/lib/research-search";
import TierGate from "@/components/TierGate";
import { canAccess } from "@/lib/entitlement";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Research Explorer — Catandary Foresight",
  description:
    "Search 45M+ papers across all disciplines — plus the curated research signal layer feeding the foresight engine.",
};

const PAGE_SIZE = 25;

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("en-US", {
      day: "numeric", month: "short", year: "numeric",
    });
  } catch {
    return iso;
  }
}

const fmtInt = (n: number) => n.toLocaleString("en-US");

export default async function ResearchExplorerPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; theme?: string; topic?: string; page?: string }>;
}) {
  const sp = await searchParams;
  const qText = (sp.q ?? "").trim();
  const theme = (sp.theme ?? "").trim();
  const topic = (sp.topic ?? "").trim();
  const page = Math.max(1, parseInt(sp.page ?? "1", 10) || 1);

  // Smart-Router (#80): DOI, arXiv-ID und Jahre aus dem Freitext ziehen
  const parsed = parseResearchQuery(qText);
  // Zwei Schichten: Suche/Topic → 45,9M-Korpus (research_corpus, alle
  // Disziplinen); Theme bzw. keine Eingabe → kuratierte Signal-Schicht wie
  // bisher. Nur die Signal-Schicht speist Foresight.
  const corpusMode = !!(parsed.text || parsed.doi || parsed.arxiv || topic
    || parsed.yearFrom !== undefined);

  // Owner-Entscheid (#72): Starter-gegated — ohne Tier wird keine Suche
  // ausgeführt, der Teaser lädt nur die drei neuesten Signale.
  const allowed = await canAccess("starter");
  const [stats, corpusStats, topics] = await Promise.all([
    getResearchStats(), getResearchCorpusStats(),
    allowed ? getResearchTopics() : Promise.resolve([]),
  ]);

  let corpus: Awaited<ReturnType<typeof getResearchCorpus>> = { rows: [], total: 0, clamped: false };
  let signals: Awaited<ReturnType<typeof getResearchSignals>> = { rows: [], total: 0 };
  if (!allowed) {
    signals = await getResearchSignals({ limit: 3, offset: 0 });
  } else if (corpusMode) {
    corpus = await getResearchCorpus({
      q: parsed.text || undefined,
      doi: parsed.doi,
      arxiv: parsed.arxiv,
      topic: topic || undefined,
      yearFrom: parsed.yearFrom,
      yearTo: parsed.yearTo,
      limit: PAGE_SIZE,
      offset: (page - 1) * PAGE_SIZE,
    });
  } else {
    signals = await getResearchSignals({
      mega: theme || undefined, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE,
    });
  }
  const total = corpusMode ? corpus.total : signals.total;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const totalLabel = `${fmtInt(total)}${corpusMode && corpus.clamped ? "+" : ""}`;
  const qs = (p: number) => {
    const u = new URLSearchParams();
    if (qText) u.set("q", qText);
    if (theme) u.set("theme", theme);
    if (topic) u.set("topic", topic);
    if (p > 1) u.set("page", String(p));
    const s = u.toString();
    return `/trends/foresight/research${s ? `?${s}` : ""}`;
  };

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <div className="mb-8">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-4">
          —— What your peers publish
        </div>
        <h1 className="font-display text-4xl md:text-[44px] leading-[1.05] tracking-tight text-paper mb-4">
          Research <span className="italic">Explorer</span>
        </h1>
        <p className="font-sans text-text text-lg leading-relaxed max-w-2xl">
          Search {fmtInt(corpusStats.total)} papers across{" "}
          {fmtInt(corpusStats.topics)} research topics — every discipline, not
          just our industry verticals. On top sits the curated signal layer
          ({fmtInt(stats.total)} classified research signals,{" "}
          {fmtInt(stats.last30d)} added in 30 days) that feeds the foresight
          engine.
        </p>
      </div>

      <TierGate
        need="starter"
        feature="The searchable research corpus"
        benefit={`Starter opens full-text search across ${fmtInt(corpusStats.total)} papers from all disciplines — with topic facets, citation counts, field-normalized impact and retraction flags.`}
        teaser={
          <div>
            <div className="flex flex-col divide-y divide-border border-t border-b border-border">
              {signals.rows.map((r) => (
                <article key={r.trend_id} className="py-5">
                  <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-muted mb-1.5">
                    <span className="text-paper">{fmtDate(r.published)}</span>
                    {r.concept && <span> · {r.concept}</span>}
                  </div>
                  <h2 className="font-display text-[19px] leading-snug text-paper mb-1.5">{r.title}</h2>
                  {r.abstract && (
                    <p className="font-sans text-sm text-text leading-relaxed line-clamp-2 max-w-3xl">{r.abstract}</p>
                  )}
                </article>
              ))}
            </div>
            <p className="mt-4 font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
              Free preview — the 3 newest of {fmtInt(stats.total)} curated research signals
            </p>
          </div>
        }
      >
      <form
        method="GET"
        action="/trends/foresight/research"
        className="mb-2 flex flex-col sm:flex-row gap-3 flex-wrap"
      >
        <input
          type="search"
          name="q"
          defaultValue={qText}
          placeholder="Topic, DOI or arXiv ID — e.g. processed cheese 2020-2024"
          className="flex-1 min-w-[220px] bg-card border border-border-strong px-4 py-2.5 font-sans text-sm text-paper placeholder:text-muted focus:outline-none focus:border-accent"
          aria-label="Search research papers"
        />
        <input
          type="text"
          name="topic"
          list="rc-topics"
          defaultValue={topic}
          placeholder="Research topic…"
          className="bg-card border border-border-strong px-3 py-2.5 font-sans text-sm text-text placeholder:text-muted focus:outline-none focus:border-accent sm:max-w-[220px]"
          aria-label="Filter by research topic"
        />
        <datalist id="rc-topics">
          {topics.map((t) => <option key={t} value={t} />)}
        </datalist>
        <select
          name="theme"
          defaultValue={theme}
          className="bg-card border border-border-strong px-3 py-2.5 font-mono text-[11px] uppercase tracking-[0.08em] text-text focus:outline-none focus:border-accent sm:max-w-[200px]"
          aria-label="Browse the curated signal layer by theme"
        >
          <option value="">Signal themes…</option>
          {MEGA_TRENDS.map((mt) => (
            <option key={mt.key} value={mt.key}>{mt.name_en}</option>
          ))}
        </select>
        <button
          type="submit"
          className="bg-accent text-ink font-mono text-[11px] uppercase tracking-[0.14em] px-6 py-2.5 font-bold hover:bg-accent-deep transition-colors"
        >
          Search
        </button>
      </form>
      <p className="mb-6 font-sans text-[12px] text-muted">
        Paste a DOI (<span className="font-mono">10.1038/…</span>) or arXiv ID
        (<span className="font-mono">2504.10470</span>) to jump to a paper; years
        become filters. Text supports <span className="font-mono">&quot;exact phrase&quot;</span>,{" "}
        <span className="font-mono">OR</span> and <span className="font-mono">-exclude</span>.
        Search queries all {fmtInt(corpusStats.total)} papers; the theme picker
        browses the curated signal layer.
      </p>

      {corpusMode && parsed.chips.length > 0 && (
        <div className="mb-5 flex flex-wrap items-center gap-2 font-mono text-[10px] uppercase tracking-[0.12em]">
          <span className="text-muted">Understood as</span>
          {parsed.chips.map((c) => (
            <span key={c.kind + c.label} className="border border-accent/40 text-accent px-2 py-0.5">
              {c.kind === "doi" ? "DOI " : c.kind === "arxiv" ? "" : "Year "}{c.label}
            </span>
          ))}
          {parsed.text && (
            <span className="border border-border text-text px-2 py-0.5">Text {parsed.text}</span>
          )}
        </div>
      )}

      <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted mb-5">
        {totalLabel} {corpusMode ? "papers" : "signals"}
        {parsed.text && <> for <span className="text-paper">&ldquo;{parsed.text}&rdquo;</span></>}
        {topic && <> in <span className="text-paper">{topic}</span></>}
        {!corpusMode && theme && (
          <> in <span className="text-paper">
            {MEGA_TRENDS.find((m) => m.key === theme)?.name_en ?? theme}
          </span></>
        )}
        {" · "}page {page}/{pages}
        {corpusMode
          ? <> · full corpus, all disciplines</>
          : <> · curated signal layer</>}
      </div>

      {corpusMode ? (
        corpus.rows.length === 0 ? (
          <p className="font-sans text-sm text-muted border border-dashed border-border p-6">
            No papers found. The corpus covers English works from 2010 on with
            abstracts — try broader terms.
          </p>
        ) : (
          <div className="flex flex-col divide-y divide-border border-t border-b border-border">
            {corpus.rows.map((r) => {
              const href = r.doi ?? `https://openalex.org/${r.id}`;
              return (
                <article key={r.id} className="py-5">
                  <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-muted mb-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
                    <span className="text-paper">{fmtDate(r.published)}</span>
                    {r.topic && (
                      <Link href={`/trends/foresight/research?topic=${encodeURIComponent(r.topic)}`}
                            className="hover:text-accent">{r.topic}</Link>
                    )}
                    {r.type && r.type !== "article" && <span>{r.type}</span>}
                    {r.is_retracted && (
                      <span className="border border-red-500/60 text-red-400 px-1.5 py-0.5">
                        RETRACTED
                      </span>
                    )}
                    <span className="ml-auto">
                      {fmtInt(r.cited_by_count ?? 0)} citations
                      {r.fwci !== null && r.fwci !== undefined && (
                        <span title="Field-weighted citation impact — 1.0 = average for the field">
                          {" "}· fwci {Number(r.fwci).toFixed(1)}
                        </span>
                      )}
                    </span>
                  </div>
                  <h2 className="font-display text-[19px] leading-snug text-paper mb-1.5">
                    <a href={href} target="_blank" rel="noopener noreferrer"
                       className="hover:text-accent transition-colors">
                      {r.title}
                    </a>
                  </h2>
                  <p className="font-sans text-sm text-text leading-relaxed line-clamp-3 max-w-3xl">
                    {r.abstract}
                  </p>
                  <div className="mt-2 font-mono text-[10px] uppercase tracking-[0.12em]">
                    <a href={href} target="_blank" rel="noopener noreferrer"
                       className="text-accent/70 hover:text-accent">
                      {r.doi ? "DOI →" : "OpenAlex →"}
                    </a>
                  </div>
                </article>
              );
            })}
          </div>
        )
      ) : signals.rows.length === 0 ? (
        <p className="font-sans text-sm text-muted border border-dashed border-border p-6">
          No signals in this theme yet.
        </p>
      ) : (
        <div className="flex flex-col divide-y divide-border border-t border-b border-border">
          {signals.rows.map((r) => (
            <article key={r.trend_id} className="py-5">
              <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-muted mb-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className="text-paper">{fmtDate(r.published)}</span>
                {r.concept && <span>{r.concept}</span>}
                {r.mega_trend && (
                  <Link href={`/trends/mega/${r.mega_trend.replace(/_/g, "-")}`}
                        className="text-accent/80 hover:text-accent">
                    {MEGA_TRENDS.find((m) => m.key === r.mega_trend)?.name_en ?? r.mega_trend}
                  </Link>
                )}
              </div>
              <h2 className="font-display text-[19px] leading-snug text-paper mb-1.5">
                <a href={r.url} target="_blank" rel="noopener noreferrer"
                   className="hover:text-accent transition-colors">
                  {r.title}
                </a>
              </h2>
              {r.abstract && (
                <p className="font-sans text-sm text-text leading-relaxed line-clamp-3 max-w-3xl">
                  {r.abstract}
                </p>
              )}
              <div className="mt-2 font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
                <a href={r.url} target="_blank" rel="noopener noreferrer"
                   className="text-accent/70 hover:text-accent">
                  Open source →
                </a>
              </div>
            </article>
          ))}
        </div>
      )}

      {pages > 1 && (
        <nav className="mt-8 flex items-center gap-4 font-mono text-[11px] uppercase tracking-[0.14em]" aria-label="Pagination">
          {page > 1 ? (
            <Link href={qs(page - 1)} className="text-accent hover:underline">← Newer</Link>
          ) : (
            <span className="text-muted/50">← Newer</span>
          )}
          <span className="text-muted">page {page}/{pages}{corpusMode && corpus.clamped ? " (of 10,000+ matches)" : ""}</span>
          {page < pages ? (
            <Link href={qs(page + 1)} className="text-accent hover:underline">Older →</Link>
          ) : (
            <span className="text-muted/50">Older →</span>
          )}
        </nav>
      )}

      </TierGate>

      <p className="mt-10 font-sans text-[13px] text-muted max-w-3xl border-t border-dashed border-border pt-4">
        Corpus: OpenAlex snapshot — English research articles, preprints and
        reviews from 2010 on with abstracts; works older than three years are
        included once cited at least once, younger works enter citation-free.
        Topic labels, citation counts, field-weighted impact (fwci) and
        retraction flags come from OpenAlex. The curated signal layer (papers,
        preprints and grants classified into our themes) is unchanged and feeds
        the foresight engine. Author search is on the roadmap (#80).
      </p>
    </div>
  );
}
