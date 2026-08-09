import Link from "next/link";
import { getPatentSignals, getPatentStats } from "@/lib/db";
import TierGate from "@/components/TierGate";
import { canAccess } from "@/lib/entitlement";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Patent Explorer — Catandary Foresight",
  description:
    "Search 19M+ patents with abstracts, assignees, families and technology facets — the technology tier of the innovation chain.",
};

const PAGE_SIZE = 25;

// Kuratierte Technologie-Achsen (build_cpc_insights.CURATED + 2026-08-Themes)
const CPC_OPTIONS: [string, string][] = [
  ["G06N", "AI & Machine Learning"],
  ["B25J", "Robotics"],
  ["G16Y", "Internet of Things"],
  ["G06Q", "Digital Business & Fintech"],
  ["H04W", "Wireless Networks & 5G/6G"],
  ["H01L", "Semiconductor Devices"],
  ["H10K", "Organic & Hybrid Electronics"],
  ["B64G", "Spacecraft & Space Technology"],
  ["H02S", "Solar Photovoltaics"],
  ["H01M", "Batteries & Energy Storage"],
  ["C25B", "Electrolysis & Green Hydrogen"],
  ["F03D", "Wind Power"],
  ["B09B", "Recycling & Circular Economy"],
  ["A61K", "Pharmaceuticals"],
  ["C12N", "Genetic Engineering & Cell Biology"],
  ["G16H", "Digital Health"],
  ["A61B", "Diagnostics & Medical Devices"],
  ["A23L", "Functional Foods"],
  ["A23C", "Dairy & Alternatives"],
  ["A01H", "Plant Breeding"],
  ["A23J", "Alternative Proteins"],
  ["B33Y", "Additive Manufacturing"],
  ["E04B", "Construction & Modular Building"],
  ["D01F", "High-Tech Fibers & Materials"],
  ["A63F", "Gaming & Interactive Media"],
  ["G09B", "EdTech & Learning Systems"],
];

// Offices nach realer Korpus-Stärke (alle ≥200k Patente, gemessen 2026-08-09)
const COUNTRIES: [string, string][] = [
  ["US", "United States"], ["CN", "China"], ["EP", "Europe (EP)"],
  ["WO", "WIPO (PCT)"], ["KR", "South Korea"], ["JP", "Japan"],
  ["CA", "Canada"], ["AU", "Australia"], ["GB", "United Kingdom"], ["TW", "Taiwan"],
];

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

export default async function PatentExplorerPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; cpc?: string; country?: string; page?: string }>;
}) {
  const sp = await searchParams;
  const qText = (sp.q ?? "").trim();
  // Facetten gegen die kuratierten Listen validieren — der CPC-Browse-Pfad
  // läuft über die materialisierte patent_explorer_cpc, die nur diese
  // Subclasses enthält; freie Codes würden fälschlich "0 results" zeigen.
  const cpcRaw = (sp.cpc ?? "").trim().toUpperCase();
  const cpc = CPC_OPTIONS.some(([c]) => c === cpcRaw) ? cpcRaw : "";
  const countryRaw = (sp.country ?? "").trim().toUpperCase();
  const country = COUNTRIES.some(([c]) => c === countryRaw) ? countryRaw : "";
  const page = Math.max(1, parseInt(sp.page ?? "1", 10) || 1);

  // Starter-gegated wie der Research Explorer (#73/#74): ohne Tier läuft die
  // Suche serverseitig nicht — der Teaser zeigt nur die 3 neuesten Patente.
  const allowed = await canAccess("starter");
  const [stats, { rows, total, clamped }] = await Promise.all([
    getPatentStats(),
    allowed
      ? getPatentSignals({
          q: qText || undefined,
          cpc: cpc || undefined,
          country: country || undefined,
          limit: PAGE_SIZE,
          offset: (page - 1) * PAGE_SIZE,
        })
      : getPatentSignals({ limit: 3, offset: 0 }),
  ]);
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const totalLabel = `${total.toLocaleString("en-US")}${clamped ? "+" : ""}`;
  const qs = (p: number) => {
    const u = new URLSearchParams();
    if (qText) u.set("q", qText);
    if (cpc) u.set("cpc", cpc);
    if (country) u.set("country", country);
    if (p > 1) u.set("page", String(p));
    const s = u.toString();
    return `/trends/foresight/patents${s ? `?${s}` : ""}`;
  };

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <div className="mb-8">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-4">
          —— The technology tier
        </div>
        <h1 className="font-display text-4xl md:text-[44px] leading-[1.05] tracking-tight text-paper mb-4">
          Patent <span className="italic">Explorer</span>
        </h1>
        <p className="font-sans text-text text-lg leading-relaxed max-w-2xl">
          {stats.total.toLocaleString("en-US")} patents with abstracts, weekly
          refreshed from the EPO&apos;s DOCDB bulk data — searchable by full
          text, technology class and patent office.{" "}
          {stats.assignees.toLocaleString("en-US")} already carry assignee names.
        </p>
      </div>

      <TierGate
        need="starter"
        feature="The searchable patent corpus"
        benefit={`Starter opens full-text search across all ${stats.total.toLocaleString("en-US")} patents — with technology facets, assignees, family sizes and Espacenet links.`}
        teaser={
          <div>
            <div className="flex flex-col divide-y divide-border border-t border-b border-border">
              {rows.map((r) => (
                <article key={r.pub_number} className="py-5">
                  <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-muted mb-1.5">
                    <span className="text-paper">{fmtDate(r.published)}</span>
                    <span> · {r.pub_number}</span>
                  </div>
                  <h2 className="font-display text-[19px] leading-snug text-paper mb-1.5">{r.title}</h2>
                  {r.abstract && (
                    <p className="font-sans text-sm text-text leading-relaxed line-clamp-2 max-w-3xl">{r.abstract}</p>
                  )}
                </article>
              ))}
            </div>
            <p className="mt-4 font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
              Free preview — the 3 newest of {stats.total.toLocaleString("en-US")} patents
            </p>
          </div>
        }
      >
      <form
        method="GET"
        action="/trends/foresight/patents"
        className="mb-8 flex flex-col sm:flex-row gap-3 flex-wrap"
      >
        <input
          type="search"
          name="q"
          defaultValue={qText}
          placeholder="Search titles and abstracts — e.g. solid state battery"
          className="flex-1 min-w-[220px] bg-card border border-border-strong px-4 py-2.5 font-sans text-sm text-paper placeholder:text-muted focus:outline-none focus:border-accent"
          aria-label="Search patents"
        />
        <select
          name="cpc"
          defaultValue={cpc}
          className="bg-card border border-border-strong px-3 py-2.5 font-mono text-[11px] uppercase tracking-[0.08em] text-text focus:outline-none focus:border-accent"
          aria-label="Filter by technology"
        >
          <option value="">All technologies</option>
          {CPC_OPTIONS.map(([code, name]) => (
            <option key={code} value={code}>{name} ({code})</option>
          ))}
        </select>
        <select
          name="country"
          defaultValue={country}
          className="bg-card border border-border-strong px-3 py-2.5 font-mono text-[11px] uppercase tracking-[0.08em] text-text focus:outline-none focus:border-accent"
          aria-label="Filter by patent office"
        >
          <option value="">All offices</option>
          {COUNTRIES.map(([code, name]) => (
            <option key={code} value={code}>{name}</option>
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
        {totalLabel} results
        {qText && <> for <span className="text-paper">&ldquo;{qText}&rdquo;</span></>}
        {cpc && <> in <span className="text-paper">{CPC_OPTIONS.find(([c]) => c === cpc)?.[1] ?? cpc}</span></>}
        {country && <> at <span className="text-paper">{country}</span></>}
        {" · "}page {page}/{pages}
      </div>

      {rows.length === 0 ? (
        <p className="font-sans text-sm text-muted border border-dashed border-border p-6">
          No results. Try fewer or broader terms — the search covers English
          titles and abstracts.
        </p>
      ) : (
        <div className="flex flex-col divide-y divide-border border-t border-b border-border">
          {rows.map((r) => (
            <article key={r.pub_number} className="py-5">
              <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-muted mb-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className="text-paper">{fmtDate(r.published)}</span>
                <span>{r.pub_number}</span>
                {r.assignee && <span className="text-accent/80">{r.assignee}</span>}
                {(r.family_size ?? 0) > 1 && (
                  <span title="Publications in the same DOCDB simple family (one invention, several offices)">
                    family of {r.family_size}
                  </span>
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
              <div className="mt-2 font-mono text-[10px] uppercase tracking-[0.12em] text-muted flex flex-wrap items-center gap-x-4 gap-y-1">
                {r.cpcs.slice(0, 4).map((c) =>
                  CPC_OPTIONS.some(([code]) => code === c) ? (
                    <Link
                      key={c}
                      href={`/trends/foresight/patents?cpc=${c}`}
                      className="border border-border px-1.5 py-0.5 hover:border-accent hover:text-accent transition-colors"
                      title={CPC_OPTIONS.find(([code]) => code === c)?.[1]}
                    >
                      {c}
                    </Link>
                  ) : (
                    <span key={c} className="border border-border px-1.5 py-0.5" title={`CPC ${c}`}>
                      {c}
                    </span>
                  )
                )}
                <a
                  href={r.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-accent/70 hover:text-accent"
                >
                  Espacenet →
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
          <span className="text-muted">page {page}/{pages}{clamped ? " (of 10,000+ matches)" : ""}</span>
          {page < pages ? (
            <Link href={qs(page + 1)} className="text-accent hover:underline">Older →</Link>
          ) : (
            <span className="text-muted/50">Older →</span>
          )}
        </nav>
      )}
      </TierGate>

      <p className="mt-10 font-sans text-[13px] text-muted max-w-3xl border-t border-dashed border-border pt-4">
        Corpus: EPO DOCDB bulk data (weekly Cr-Del + Amend deliveries — new
        publications plus later-arriving classifications and citations). Assignee
        names and family links are being backfilled from our archived deliveries;
        coverage grows daily. Every entry links to its Espacenet record.
      </p>
    </div>
  );
}
