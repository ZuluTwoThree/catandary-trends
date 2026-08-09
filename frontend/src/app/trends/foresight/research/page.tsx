import Link from "next/link";
import { getResearchSignals, getResearchStats } from "@/lib/db";
import { MEGA_TRENDS } from "@/lib/mega-trends.generated";
import TierGate from "@/components/TierGate";
import { canAccess } from "@/lib/entitlement";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Research Explorer — Catandary Foresight",
  description:
    "Search the citation-free research corpus — fresh papers, preprints and abstracts across all signal themes, months before market coverage.",
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

export default async function ResearchExplorerPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; theme?: string; page?: string }>;
}) {
  const sp = await searchParams;
  const qText = (sp.q ?? "").trim();
  const theme = (sp.theme ?? "").trim();
  const page = Math.max(1, parseInt(sp.page ?? "1", 10) || 1);

  // Owner-Entscheid 2026-08-09 (#72): Explorer ist Starter-gegated. Ohne
  // Zugriff wird die Suche gar nicht erst ausgefuehrt — der Teaser laedt nur
  // die drei neuesten Eintraege (Suchparameter bleiben serverseitig wirkungslos).
  const allowed = await canAccess("starter");
  const [stats, { rows, total }] = await Promise.all([
    getResearchStats(),
    allowed
      ? getResearchSignals({
          q: qText || undefined,
          mega: theme || undefined,
          limit: PAGE_SIZE,
          offset: (page - 1) * PAGE_SIZE,
        })
      : getResearchSignals({ limit: 3, offset: 0 }),
  ]);
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const qs = (p: number) => {
    const u = new URLSearchParams();
    if (qText) u.set("q", qText);
    if (theme) u.set("theme", theme);
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
          {stats.total.toLocaleString("en-US")} papers, preprints and grants —
          including a citation-free fresh corpus that surfaces work{" "}
          <span className="text-paper">before</span> it accumulates citations
          or market coverage. {stats.last30d.toLocaleString("en-US")} added in
          the last 30 days.
        </p>
      </div>

      <TierGate
        need="starter"
        feature="The searchable research corpus"
        benefit={`Starter opens full-text search across all ${stats.total.toLocaleString("en-US")} papers, preprints and grants — with theme filters and direct source links.`}
        teaser={
          <div>
            <div className="flex flex-col divide-y divide-border border-t border-b border-border">
              {rows.map((r) => (
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
              Free preview — the 3 newest of {stats.total.toLocaleString("en-US")} research signals
            </p>
          </div>
        }
      >
      {/* Suche + Theme-Filter als GET-Form — Server-gerendert, keine Client-Logik */}
      <form
        method="GET"
        action="/trends/foresight/research"
        className="mb-8 flex flex-col sm:flex-row gap-3"
      >
        <input
          type="search"
          name="q"
          defaultValue={qText}
          placeholder="Search titles and abstracts — e.g. quantum error correction"
          className="flex-1 bg-card border border-border-strong px-4 py-2.5 font-sans text-sm text-paper placeholder:text-muted focus:outline-none focus:border-accent"
          aria-label="Search research signals"
        />
        <select
          name="theme"
          defaultValue={theme}
          className="bg-card border border-border-strong px-3 py-2.5 font-mono text-[11px] uppercase tracking-[0.08em] text-text focus:outline-none focus:border-accent sm:max-w-[240px]"
          aria-label="Filter by signal theme"
        >
          <option value="">All themes</option>
          {MEGA_TRENDS.map((mt) => (
            <option key={mt.key} value={mt.key}>
              {mt.name_en}
            </option>
          ))}
        </select>
        <button
          type="submit"
          className="bg-accent text-ink font-mono text-[11px] uppercase tracking-[0.14em] px-6 py-2.5 font-bold hover:bg-accent-deep transition-colors"
        >
          Search
        </button>
      </form>

      <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted mb-5">
        {total.toLocaleString("en-US")} results
        {qText && <> for <span className="text-paper">&ldquo;{qText}&rdquo;</span></>}
        {theme && (
          <> in <span className="text-paper">
            {MEGA_TRENDS.find((m) => m.key === theme)?.name_en ?? theme}
          </span></>
        )}
        {" · "}page {page}/{pages}
      </div>

      {rows.length === 0 ? (
        <p className="font-sans text-sm text-muted border border-dashed border-border p-6">
          No results. Try fewer or broader terms — the search covers titles and
          abstracts in English.
        </p>
      ) : (
        <div className="flex flex-col divide-y divide-border border-t border-b border-border">
          {rows.map((r) => (
            <article key={r.trend_id} className="py-5">
              <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-muted mb-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className="text-paper">{fmtDate(r.published)}</span>
                {r.concept && <span>{r.concept}</span>}
                {r.mega_trend && (
                  <Link
                    href={`/trends/mega/${r.mega_trend.replace(/_/g, "-")}`}
                    className="text-accent/80 hover:text-accent"
                  >
                    {MEGA_TRENDS.find((m) => m.key === r.mega_trend)?.name_en ?? r.mega_trend}
                  </Link>
                )}
              </div>
              <h2 className="font-display text-[19px] leading-snug text-paper mb-1.5">
                <a
                  href={r.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-accent transition-colors"
                >
                  {r.title}
                </a>
              </h2>
              {r.abstract && (
                <p className="font-sans text-sm text-text leading-relaxed line-clamp-3 max-w-3xl">
                  {r.abstract}
                </p>
              )}
              <div className="mt-2 font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
                <a
                  href={r.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-accent/70 hover:text-accent"
                >
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
          <span className="text-muted">page {page}/{pages}</span>
          {page < pages ? (
            <Link href={qs(page + 1)} className="text-accent hover:underline">Older →</Link>
          ) : (
            <span className="text-muted/50">Older →</span>
          )}
        </nav>
      )}

      </TierGate>

      <p className="mt-10 font-sans text-[13px] text-muted max-w-3xl border-t border-dashed border-border pt-4">
        Corpus: OpenAlex works (incl. a citation-free 2025+ fresh sweep), arXiv /
        bioRxiv / medRxiv preprints and research-tier journal feeds. Every entry
        links to its primary source. Author names are not yet indexed — they are
        on the enrichment roadmap.
      </p>
    </div>
  );
}
