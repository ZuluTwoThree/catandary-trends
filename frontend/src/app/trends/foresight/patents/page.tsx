import Link from "next/link";
import { getPatentSignals, getPatentStats, getPatentTechIntel } from "@/lib/db";
import { computeTransferSeries } from "@/lib/transfer";
import { parsePatentQuery } from "@/lib/patent-search";
import {
  nplShare, ceasedWithin, topCountries, countryShare,
  oppositionRate, emergingGroups,
} from "@/lib/patent-intel";
import TierGate from "@/components/TierGate";
import { canAccess } from "@/lib/entitlement";

const pct = (v: number | null, digits = 0) =>
  v === null ? "—" : `${(v * 100).toFixed(digits)}%`;

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
  // Smart-Router (#78): Publikationsnummern, CPC-Codes und Jahre aus dem
  // Freitext holen, bevor der Rest an die Volltextsuche geht.
  const parsed = parsePatentQuery(qText);
  // Facetten gegen die kuratierten Listen validieren — der CPC-Browse-Pfad
  // läuft über die materialisierte patent_explorer_cpc, die nur diese
  // Subclasses enthält; freie Codes würden fälschlich "0 results" zeigen.
  const cpcRaw = (sp.cpc ?? "").trim().toUpperCase();
  const dropdownCpc = CPC_OPTIONS.some(([c]) => c === cpcRaw) ? cpcRaw : "";
  const parsedCurated = !!parsed.cpc && CPC_OPTIONS.some(([c]) => c === parsed.cpc);
  // Nicht kuratierte Subclass ohne Suchtext hat keinen schnellen Pfad
  // (Stufe 2 baut den Browse-Index auf alle ~650 aus) → ehrlicher Hinweis
  // statt Timeout oder falscher Nulltreffer.
  const uncoveredCpc = parsed.cpc && !parsedCurated && !parsed.text ? parsed.cpc : "";
  const cpc = dropdownCpc || (parsed.cpc && !uncoveredCpc ? parsed.cpc : "");
  const searchText = uncoveredCpc ? qText : parsed.text;
  const countryRaw = (sp.country ?? "").trim().toUpperCase();
  const country = COUNTRIES.some(([c]) => c === countryRaw) ? countryRaw : "";
  const page = Math.max(1, parseInt(sp.page ?? "1", 10) || 1);

  // Starter-gegated wie der Research Explorer (#73/#74): ohne Tier läuft die
  // Suche serverseitig nicht — der Teaser zeigt nur die 3 neuesten Patente.
  const allowed = await canAccess("starter");
  const [stats, { rows, total, clamped }, intel] = await Promise.all([
    getPatentStats(),
    allowed
      ? getPatentSignals({
          q: searchText || undefined,
          cpc: cpc || undefined,
          country: country || undefined,
          pubExact: parsed.pubExact,
          pubPrefix: parsed.pubPrefix,
          yearFrom: parsed.yearFrom,
          yearTo: parsed.yearTo,
          limit: PAGE_SIZE,
          offset: (page - 1) * PAGE_SIZE,
        })
      : getPatentSignals({ limit: 3, offset: 0 }),
    allowed && cpc ? getPatentTechIntel(cpc) : Promise.resolve(null),
  ]);
  const transfer = intel ? computeTransferSeries(intel.sectorRows) : [];
  const maxFamilies = intel ? Math.max(...intel.applicants.map((a) => a.families)) : 0;
  const maxShare = transfer.reduce((m, p) => Math.max(m, p.uniShare ?? 0), 0);
  const firstShare = transfer.find((p) => p.uniShare !== null)?.uniShare ?? null;
  const lastShare = [...transfer].reverse().find((p) => p.uniShare !== null)?.uniShare ?? null;
  // Kennzahlen aus den Runde-2-Tabellen (#75); Jahreswahl konservativ:
  // 2023 = letztes vollständiges Anmeldejahr, Kohorte 2013 = jüngste mit
  // 10 beobachtbaren Jahren, EP-Quote 2022 (Einsprüche laufen 9 Monate).
  const iv = intel
    ? {
        nplNow: nplShare(intel.npl, 2023),
        npl2010: nplShare(intel.npl, 2010),
        nplLag: intel.npl.find((r) => r.publn_year === 2023)?.median_lag_years ?? null,
        nplLagThen: intel.npl.find((r) => r.publn_year === 2010)?.median_lag_years ?? null,
        lagSeries: intel.npl
          .filter((r) => r.median_lag_years !== null)
          .map((r) => ({ year: r.publn_year, lag: r.median_lag_years as number })),
        ceased10: ceasedWithin(intel.survival, 2013, 10),
        ceased10Old: ceasedWithin(intel.survival, 2005, 10),
        top5: topCountries(intel.countries, 2023, 5),
        top5Then: (c: string) => countryShare(intel.countries, 2015, c),
        intlNow: intel.intl.find((r) => r.filing_year === 2023) ?? null,
        intlThen: intel.intl.find((r) => r.filing_year === 2015) ?? null,
        oppNow: oppositionRate(intel.oppositions, 2022),
        oppThen: oppositionRate(intel.oppositions, 2012),
        rising: emergingGroups(intel.groups, 2018, 3),
        naceTotal: intel.nace.reduce((s, r) => s + r.weighted_applications, 0),
      }
    : null;
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
          placeholder="Topic, patent number or CPC code — e.g. solid state battery 2023"
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

      <p className="-mt-6 mb-8 font-sans text-[12px] text-muted">
        Paste a patent number (<span className="font-mono">US11734097B2</span>), a CPC class
        (<span className="font-mono">H01M</span>) or a year — they become filters automatically.
        For text: <span className="font-mono">&quot;exact phrase&quot;</span>,{" "}
        <span className="font-mono">OR</span>, and <span className="font-mono">-exclude</span> work.
      </p>

      {intel && (
        <section className="mb-8 border border-border-strong">
          <div className="border-b border-border px-4 py-2.5 font-mono text-[10px] uppercase tracking-[0.18em] text-accent">
            —— Technology intelligence · {CPC_OPTIONS.find(([c]) => c === cpc)?.[1]} ({cpc})
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-border">
            <div className="p-4">
              <h3 className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted mb-3">
                Leading applicants · patent families since 2015
              </h3>
              <ol className="space-y-1.5">
                {intel.applicants.map((a) => (
                  <li key={a.rank} className="relative">
                    <div
                      className="absolute inset-y-0 left-0 bg-accent/10"
                      style={{ width: `${(a.families / maxFamilies) * 100}%` }}
                    />
                    <div className="relative flex items-baseline gap-2 px-1.5 py-0.5">
                      <span className="font-mono text-[9px] text-muted w-4 shrink-0">{a.rank}</span>
                      <span className="font-sans text-[13px] text-paper truncate" title={a.name}>
                        {a.name}
                      </span>
                      {a.sector && a.sector !== "COMPANY" && (
                        <span className="font-mono text-[8px] uppercase tracking-[0.1em] text-accent/80 shrink-0">
                          {a.sector}
                        </span>
                      )}
                      <span className="font-mono text-[10px] text-muted ml-auto shrink-0">
                        {a.ctry?.trim() && <span>{a.ctry.trim()} · </span>}
                        {a.families.toLocaleString("en-US")}
                      </span>
                    </div>
                  </li>
                ))}
              </ol>
            </div>
            <div className="p-4">
              <h3 className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted mb-3">
                University → industry transfer · share of families with a university applicant
              </h3>
              {transfer.length > 0 && maxShare > 0 ? (
                <>
                  {/* Balkenhöhen in px statt %: der Spalten-Div hat keine feste
                      Höhe, Prozent würde dort zu 0 auflösen (Bug-Report Owner
                      2026-08-10 — Balken waren unsichtbar, nur Jahre zu sehen). */}
                  <div className="flex items-end gap-[3px]" role="img"
                       aria-label="University share of patent families per filing year">
                    {transfer.map((p) => {
                      const share = p.uniShare ?? 0;
                      const px = share > 0 ? Math.max(3, Math.round((share / maxShare) * 96)) : 0;
                      return (
                        <div key={p.year} className="flex-1 flex flex-col items-center gap-1 min-w-0">
                          <div
                            className="w-full bg-accent/60"
                            style={{ height: `${px}px` }}
                            title={`${p.year}: ${(share * 100).toFixed(1)}% of ${p.total.toLocaleString("en-US")} families`}
                          />
                          {/* Label-Slot in JEDER Spalte (meist leer), sonst schiebt
                              die Jahreszahl ihren Balken hoch — Baseline-Versatz
                              (Owner-Befund 2026-08-10) */}
                          <span className="font-mono text-[8px] text-muted h-3 leading-3">
                            {p.year % 5 === 0 ? p.year : " "}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                  {firstShare !== null && lastShare !== null && (
                    <p className="mt-3 font-sans text-[13px] text-text">
                      University share {transfer[0].year}:{" "}
                      <span className="text-paper">{(firstShare * 100).toFixed(1)}%</span>
                      {" → "}{transfer[transfer.length - 1].year}:{" "}
                      <span className="text-paper">{(lastShare * 100).toFixed(1)}%</span>
                      {lastShare < firstShare
                        ? " — the technology is moving from labs into industry."
                        : " — research institutions still drive this field."}
                    </p>
                  )}
                </>
              ) : (
                <p className="font-sans text-[13px] text-muted">No sector data for this technology.</p>
              )}
            </div>
          </div>
          {iv && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 border-t border-border divide-y sm:divide-x divide-border">
              <div className="p-4">
                <h4 className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted mb-1.5">
                  Science intensity
                </h4>
                <div className="font-display text-2xl text-paper">{pct(iv.nplNow)}</div>
                <p className="font-sans text-[12px] text-text mt-1">
                  of citations in 2023 patents point to scientific literature, not other
                  patents{iv.npl2010 !== null && <> ({pct(iv.npl2010)} in 2010)</>}.
                </p>
              </div>
              {iv.nplLag !== null && (
                <div className="p-4">
                  <h4 className="font-mono text-[9px] uppercase tracking-[0.14em] text-accent mb-1.5">
                    Research → patent lead time
                  </h4>
                  <div className="flex items-end justify-between gap-3">
                    <div>
                      <div className="font-display text-2xl text-paper">
                        {iv.nplLag} yrs
                      </div>
                      <p className="font-sans text-[12px] text-text mt-1">
                        median age of the science cited in 2023 patents.
                        {iv.nplLagThen !== null && iv.nplLag < iv.nplLagThen && (
                          <> Down from {iv.nplLagThen} in 2010 — this field is
                          absorbing research faster.</>
                        )}
                        {iv.nplLagThen !== null && iv.nplLag > iv.nplLagThen && (
                          <> Up from {iv.nplLagThen} in 2010 — patents lean on
                          ever-older science.</>
                        )}
                        {iv.nplLagThen !== null && iv.nplLag === iv.nplLagThen && (
                          <> Stable since 2010.</>
                        )}
                      </p>
                    </div>
                    {iv.lagSeries.length > 1 && (
                      <div className="flex items-end gap-[2px]" role="img"
                           aria-label="Median research age per publication year">
                        {iv.lagSeries.map((p) => (
                          <div
                            key={p.year}
                            className="w-[7px] bg-accent/60"
                            style={{ height: `${Math.max(3, Math.round((p.lag / Math.max(...iv.lagSeries.map((x) => x.lag))) * 44))}px` }}
                            title={`${p.year}: ${p.lag} years`}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}
              <div className="p-4">
                <h4 className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted mb-1.5">
                  Holding power
                </h4>
                <div className="font-display text-2xl text-paper">
                  {iv.ceased10 === null ? "—" : pct(1 - iv.ceased10)}
                </div>
                <p className="font-sans text-[12px] text-text mt-1">
                  of granted patents (2013 cohort) were still maintained after 10
                  years{iv.ceased10Old !== null && <> — 2005 cohort: {pct(1 - iv.ceased10Old)}</>}.
                  Short holding = owners losing faith.
                </p>
              </div>
              <div className="p-4">
                <h4 className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted mb-1.5">
                  Investment confidence
                </h4>
                <div className="font-display text-2xl text-paper">
                  {iv.intlNow ? pct(iv.intlNow.multi_office_families / iv.intlNow.families) : "—"}
                </div>
                <p className="font-sans text-[12px] text-text mt-1">
                  of 2023 families were filed at 2+ patent offices
                  {iv.intlThen && <> ({pct(iv.intlThen.multi_office_families / iv.intlThen.families)} in 2015)</>}
                  — international filings cost real money.
                </p>
              </div>
              <div className="p-4">
                <h4 className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted mb-1.5">
                  Country race · 2023 filings
                </h4>
                <ol className="space-y-1 mt-1.5">
                  {iv.top5.map((c) => {
                    const then = iv.top5Then(c.ctry);
                    return (
                      <li key={c.ctry} className="flex items-baseline gap-2 font-mono text-[11px]">
                        <span className="text-paper w-7">{c.ctry}</span>
                        <div className="flex-1 h-1.5 bg-accent/10">
                          <div className="h-full bg-accent/60" style={{ width: `${c.share * 100}%` }} />
                        </div>
                        <span className="text-muted">{pct(c.share)}
                          {then !== null && <span className="text-muted/60"> ({pct(then)} ’15)</span>}
                        </span>
                      </li>
                    );
                  })}
                </ol>
              </div>
              <div className="p-4">
                <h4 className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted mb-1.5">
                  Emerging subfields · avg. families/yr since 2018 vs before
                </h4>
                {iv.rising.length === 0 ? (
                  <p className="font-sans text-[12px] text-muted mt-1">No subfield data.</p>
                ) : (
                  <ol className="space-y-1 mt-1.5">
                    {iv.rising.map((g) => (
                      <li key={g.group} className="flex items-baseline gap-2 font-mono text-[11px]">
                        <span className="text-paper">{g.group}</span>
                        <span className="text-accent">+{Math.round(g.growth * 100)}%</span>
                        <span className="text-muted/70">
                          {Math.round(g.baseAvg).toLocaleString("en-US")} → {Math.round(g.recentAvg).toLocaleString("en-US")}
                        </span>
                      </li>
                    ))}
                  </ol>
                )}
              </div>
              <div className="p-4">
                <h4 className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted mb-1.5">
                  Contested at the EPO
                </h4>
                <div className="font-display text-2xl text-paper">{pct(iv.oppNow, 1)}</div>
                <p className="font-sans text-[12px] text-text mt-1">
                  of 2022 EP grants drew an opposition
                  {iv.oppThen !== null && <> ({pct(iv.oppThen, 1)} in 2012)</>} —
                  competitors spend money fighting patents they fear.
                </p>
              </div>
              {intel.collabs.length > 0 && (
                <div className="p-4 sm:col-span-2">
                  <h4 className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted mb-1.5">
                    Top lab-to-industry pairs · co-filings since 2015
                  </h4>
                  <ol className="space-y-1 mt-1.5">
                    {intel.collabs.map((c) => (
                      <li key={c.rank} className="font-sans text-[12px] text-text truncate">
                        <span className="text-paper">{c.university}</span>
                        <span className="text-muted"> × </span>
                        <span className="text-paper">{c.company}</span>
                        <span className="font-mono text-[10px] text-muted"> · {c.families} families</span>
                      </li>
                    ))}
                  </ol>
                </div>
              )}
              {intel.nace.length > 0 && iv.naceTotal > 0 && (
                <div className="p-4">
                  <h4 className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted mb-1.5">
                    Industries owning this technology
                  </h4>
                  <ol className="space-y-1 mt-1.5">
                    {intel.nace.map((s, i) => (
                      <li key={i} className="font-sans text-[12px] text-text">
                        {s.nace2_descr ?? "Other"}{" "}
                        <span className="font-mono text-[10px] text-muted">
                          {pct(s.weighted_applications / iv.naceTotal)}
                        </span>
                      </li>
                    ))}
                  </ol>
                </div>
              )}
            </div>
          )}
          <div className="border-t border-border px-4 py-2 font-mono text-[9px] uppercase tracking-[0.12em] text-muted">
            Source: PATSTAT Global (EPO), harmonized applicant names (PSN). Filing years shown
            through 2023 — younger filings are under-counted due to the 18-month publication lag.
            Industry shares are among the top-3 mapped sectors; opposition rate = oppositions
            filed vs. none within the 9-month window.
          </div>
        </section>
      )}

      {/* Was der Router aus der Eingabe gemacht hat — sichtbar, damit eine
          Fehldeutung auffällt statt stillschweigend das Ergebnis zu verzerren */}
      {(parsed.chips.length > 0 || uncoveredCpc) && (
        <div className="mb-5 flex flex-wrap items-center gap-2 font-mono text-[10px] uppercase tracking-[0.12em]">
          <span className="text-muted">Understood as</span>
          {parsed.chips.map((c) => (
            <span key={c.kind + c.label}
                  className="border border-accent/40 text-accent px-2 py-0.5">
              {c.kind === "patent" ? "Patent " : c.kind === "cpc" ? "Class " : "Year "}
              {c.label}
            </span>
          ))}
          {searchText && (
            <span className="border border-border text-text px-2 py-0.5">Text {searchText}</span>
          )}
          {uncoveredCpc && (
            <span className="text-muted normal-case tracking-normal font-sans text-[12px]">
              — {uncoveredCpc} is not one of the {CPC_OPTIONS.length} browsable technology
              classes yet, so this ran as a text search.
            </span>
          )}
        </div>
      )}

      <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted mb-5">
        {totalLabel} results
        {searchText && <> for <span className="text-paper">&ldquo;{searchText}&rdquo;</span></>}
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
