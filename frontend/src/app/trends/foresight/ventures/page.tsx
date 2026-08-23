import Link from "next/link";
import TierGate from "@/components/TierGate";
import VentureAttribution from "@/components/VentureAttribution";
import WipBadge from "@/components/WipBadge";
import { canAccess } from "@/lib/entitlement";
import {
  getVentureStats, searchVentures, VENTURE_EVENT_TYPES, type VentureRow,
} from "@/lib/ventures";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Startup Explorer — Catandary Foresight",
  description:
    "The venture tier of the innovation chain: companies with dated funding, grant, launch and regulatory evidence from primary sources.",
};

const PAGE_SIZE = 25;

const VERTICALS = ["TECH", "HEALTH", "BIZ", "ECO", "FOOD", "LIFESTYLE", "FASHION", "DESIGN"];
const COUNTRIES: [string, string][] = [
  ["US", "United States"], ["GB", "United Kingdom"], ["DE", "Germany"],
  ["FR", "France"], ["ES", "Spain"], ["IT", "Italy"], ["NL", "Netherlands"],
];

const fmtInt = (n: number) => n.toLocaleString("en-US");

function fmtMoney(v: number | null): string | null {
  if (!v) return null;
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  return `$${Math.round(v / 1e3)}k`;
}

function CompanyRow({ r }: { r: VentureRow }) {
  const loc = [r.city, r.region, r.country].filter(Boolean).join(", ");
  const money = fmtMoney(r.total_funding_usd);
  return (
    <article className="py-5">
      <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-muted mb-1.5">
        {(r.verticals ?? []).map((v) => (
          <span key={v} className="text-accent mr-2">{v}</span>
        ))}
        {loc && <span>{loc}</span>}
        {r.founded_date && <span> · founded {r.founded_date.slice(0, 4)}</span>}
      </div>
      <h2 className="font-display text-[19px] leading-snug text-paper mb-1.5">
        <Link href={`/trends/foresight/ventures/company/${r.id}`} className="hover:underline">
          {r.name}
        </Link>
      </h2>
      <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
        {fmtInt(r.event_count)} dated event{r.event_count === 1 ? "" : "s"}
        {r.first_event_at && r.last_event_at && (
          <span> · {r.first_event_at.slice(0, 4)}–{r.last_event_at.slice(0, 4)}</span>
        )}
        {money && <span> · {money} documented funding</span>}
        {r.has_patents && <span className="text-paper"> · patents</span>}
        {r.has_research && <span className="text-paper"> · research</span>}
      </p>
    </article>
  );
}

export default async function VenturesPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; v?: string; c?: string; e?: string; page?: string }>;
}) {
  const sp = await searchParams;
  const qText = (sp.q ?? "").trim();
  const vertical = VERTICALS.includes(sp.v ?? "") ? sp.v : undefined;
  const country = (sp.c ?? "").trim() || undefined;
  const etype = VENTURE_EVENT_TYPES.some(([k]) => k === sp.e) ? sp.e : undefined;
  const page = Math.max(1, parseInt(sp.page ?? "1", 10) || 1);

  const allowed = await canAccess("starter");
  const [stats, { rows, total }] = await Promise.all([
    getVentureStats(),
    allowed
      ? searchVentures({
          q: qText || undefined, vertical, country, etype,
          limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE,
        })
      : searchVentures({ limit: 3, offset: 0 }),
  ]);
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const qs = (p: number) => {
    const u = new URLSearchParams();
    if (qText) u.set("q", qText);
    if (vertical) u.set("v", vertical);
    if (country) u.set("c", country);
    if (etype) u.set("e", etype);
    if (p > 1) u.set("page", String(p));
    const s = u.toString();
    return `/trends/foresight/ventures${s ? `?${s}` : ""}`;
  };

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <div className="mb-8">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-4">
          —— The venture tier <WipBadge />
        </div>
        <h1 className="font-display text-4xl md:text-[44px] leading-[1.05] tracking-tight text-paper mb-4">
          Startup <span className="italic">Explorer</span>
        </h1>
        <p className="font-sans text-text text-lg leading-relaxed max-w-2xl">
          {fmtInt(stats.companies)} companies with {fmtInt(stats.events)} dated
          events from primary sources — SEC filings, SBIR &amp; EU grants,
          press-verified rounds, launches and regulatory milestones.{" "}
          {fmtInt(stats.with_patents)} companies carry patent-confirmed
          technology substance. No valuations, no scraped databases — every
          event links to its source. This explorer is a work in progress:
          sources, matching and bridges are still expanding.
        </p>
      </div>

      <TierGate
        need="starter"
        feature="The searchable venture corpus"
        benefit={`Starter opens search across all ${fmtInt(stats.companies)} companies — with funding timelines, sector and country facets, and the patent & research bridges.`}
        teaser={
          <div>
            <div className="flex flex-col divide-y divide-border border-t border-b border-border">
              {rows.map((r) => <CompanyRow key={r.id} r={r} />)}
            </div>
            <p className="mt-4 font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
              Free preview — 3 of {fmtInt(stats.companies)} companies
            </p>
          </div>
        }
      >
        <form action="/trends/foresight/ventures" method="get" className="mb-6">
          <div className="flex gap-2 flex-wrap">
            <input
              type="search" name="q" defaultValue={qText}
              placeholder="Company name — e.g. ColdQuanta, Sound Agriculture"
              className="flex-1 min-w-[240px] bg-transparent border border-border px-3 py-2 font-sans text-sm text-paper placeholder:text-muted focus:border-accent focus:outline-none"
            />
            <select name="v" defaultValue={vertical ?? ""}
              className="bg-ink border border-border px-2 py-2 font-mono text-[11px] uppercase tracking-wide text-text">
              <option value="">All verticals</option>
              {VERTICALS.map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
            <select name="c" defaultValue={country ?? ""}
              className="bg-ink border border-border px-2 py-2 font-mono text-[11px] uppercase tracking-wide text-text">
              <option value="">All countries</option>
              {COUNTRIES.map(([code, label]) => (
                <option key={code} value={code}>{label}</option>
              ))}
            </select>
            <select name="e" defaultValue={etype ?? ""}
              className="bg-ink border border-border px-2 py-2 font-mono text-[11px] uppercase tracking-wide text-text">
              <option value="">All signals</option>
              {VENTURE_EVENT_TYPES.map(([k, label]) => (
                <option key={k} value={k}>{label}</option>
              ))}
            </select>
            <button type="submit"
              className="border border-accent px-4 py-2 font-mono text-[11px] uppercase tracking-wide text-accent hover:bg-accent hover:text-ink">
              Search
            </button>
          </div>
        </form>

        <p className="mb-2 font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
          {fmtInt(total)} companies
          {qText && <span> matching “{qText}”</span>}
        </p>
        <div className="flex flex-col divide-y divide-border border-t border-b border-border">
          {rows.map((r) => <CompanyRow key={r.id} r={r} />)}
          {rows.length === 0 && (
            <p className="py-8 font-sans text-sm text-muted">
              No companies match. The corpus covers primary-source evidence —
              try a shorter name or drop a filter.
            </p>
          )}
        </div>

        {pages > 1 && (
          <div className="mt-6 flex items-center gap-4 font-mono text-[11px] uppercase tracking-wide">
            {page > 1 && <Link className="text-accent hover:underline" href={qs(page - 1)}>← Prev</Link>}
            <span className="text-muted">Page {page} / {fmtInt(pages)}</span>
            {page < pages && <Link className="text-accent hover:underline" href={qs(page + 1)}>Next →</Link>}
          </div>
        )}
      </TierGate>

      <VentureAttribution />
    </div>
  );
}
