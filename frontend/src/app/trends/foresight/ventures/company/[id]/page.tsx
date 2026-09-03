import Link from "next/link";
import { notFound } from "next/navigation";
import VentureAttribution from "@/components/VentureAttribution";
import WipBadge from "@/components/WipBadge";
import { getVenture, VENTURE_EVENT_TYPES, type VentureEvent } from "@/lib/ventures";
import { safeHref } from "@/lib/safeHref";

export const dynamic = "force-dynamic";

const EVENT_LABEL = new Map(VENTURE_EVENT_TYPES);

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

function fmtMoney(v: number | null, currency: string | null): string | null {
  if (!v) return null;
  const sym = currency === "EUR" ? "€" : "$";
  if (v >= 1e9) return `${sym}${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `${sym}${(v / 1e6).toFixed(1)}M`;
  return `${sym}${Math.round(v / 1e3)}k`;
}

function EventRow({ e }: { e: VentureEvent }) {
  const money = fmtMoney(e.amount, e.currency);
  const meta = e.meta ?? {};
  const detail = [
    e.round_label,
    typeof meta.phase === "string" && typeof meta.program === "string"
      ? `${meta.program} Phase ${meta.phase}` : null,
    typeof meta.agency === "string" ? meta.agency : null,
    typeof meta.programme === "string" ? meta.programme : null,
    typeof meta.device === "string" ? meta.device : null,
    Array.isArray(meta.phases) && meta.phases.length ? meta.phases.join("/") : null,
    typeof meta.yc_batch === "string" ? meta.yc_batch : null,
  ].filter(Boolean).join(" · ");
  return (
    <li className="py-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
      <span className="font-mono text-[10px] uppercase tracking-wide text-muted w-24 shrink-0">
        {fmtDate(e.event_date)}
      </span>
      <span className="font-mono text-[10px] uppercase tracking-wide text-accent">
        {EVENT_LABEL.get(e.event_type) ?? e.event_type}
      </span>
      {money && <span className="font-display text-paper">{money}</span>}
      {detail && <span className="font-sans text-sm text-text">{detail}</span>}
      {e.investors?.length > 0 && (
        <span className="font-sans text-sm text-muted">
          Investors: {e.investors.join(", ")}
        </span>
      )}
      {safeHref(e.source_url) ? (
        <a href={safeHref(e.source_url)!} target="_blank" rel="noopener noreferrer"
          className="font-mono text-[10px] uppercase tracking-wide text-muted underline hover:text-paper">
          {e.source}
        </a>
      ) : (
        <span className="font-mono text-[10px] uppercase tracking-wide text-muted">{e.source}</span>
      )}
    </li>
  );
}

export default async function VentureCompanyPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const numId = parseInt(id, 10);
  if (!Number.isFinite(numId)) notFound();
  const data = await getVenture(numId);
  if (!data) notFound();
  const { company: c, events, patents, patentTotal, researchInstitutions } = data;
  const loc = [c.city, c.region, c.country].filter(Boolean).join(", ");
  const money = fmtMoney(c.total_funding_usd, "USD");
  const ids: [string, string | null][] = [
    ["CIK", c.cik], ["LEI", c.lei], ["Companies House", c.ch_number],
    ["Wikidata", c.wikidata_qid],
  ];

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-muted">
        <Link href="/trends/foresight/ventures" className="text-accent hover:underline">
          Startup Explorer
        </Link>
        {" "}—— company profile <WipBadge />
      </div>
      <h1 className="font-display text-4xl leading-[1.05] tracking-tight text-paper mb-3">
        {c.name}
      </h1>
      <p className="font-sans text-text text-base leading-relaxed max-w-2xl mb-1">
        {(c.verticals ?? []).join(" · ")}
        {c.sector && <span> · {c.sector}</span>}
        {loc && <span> · {loc}</span>}
        {c.founded_date && <span> · founded {fmtDate(c.founded_date)}</span>}
        {c.employees != null && c.employees > 0 && <span> · {c.employees} employees</span>}
      </p>
      {c.founders?.length > 0 && (
        <p className="font-sans text-sm text-muted mb-1">
          Founders: {c.founders.join(", ")}
        </p>
      )}
      <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted mb-6">
        {c.event_count} dated events
        {money && <span> · {money} documented funding</span>}
        {safeHref(c.website) && (
          <span>
            {" · "}
            <a href={safeHref(c.website)!} target="_blank" rel="noopener noreferrer"
              className="underline hover:text-paper">website</a>
          </span>
        )}
        {ids.filter(([, v]) => v).map(([k, v]) => (
          <span key={k}> · {k} {v}</span>
        ))}
      </p>

        <section className="mb-8">
          <h2 className="font-mono text-[11px] uppercase tracking-[0.18em] text-accent mb-2">
            Evidence timeline
          </h2>
          <ul className="divide-y divide-border border-t border-b border-border">
            {events.map((e, i) => <EventRow key={i} e={e} />)}
          </ul>
        </section>

        {patents.length > 0 && (
          <section className="mb-8">
            <h2 className="font-mono text-[11px] uppercase tracking-[0.18em] text-accent mb-2">
              Patent substance — {patentTotal} technology-confirmed
            </h2>
            <ul className="divide-y divide-border border-t border-b border-border">
              {patents.map((p) => (
                <li key={p.pub_number} className="py-3">
                  <Link
                    href={`/trends/foresight/patents?q=${encodeURIComponent(p.pub_number)}`}
                    className="font-mono text-[11px] text-accent hover:underline mr-3">
                    {p.pub_number}
                  </Link>
                  <span className="font-sans text-sm text-text">{p.title ?? "—"}</span>
                  <span className="font-mono text-[10px] uppercase text-muted ml-2">
                    {fmtDate(p.published)}
                  </span>
                </li>
              ))}
            </ul>
            <p className="mt-2 font-mono text-[9px] uppercase tracking-[0.14em] text-muted">
              Matched by normalized assignee name and confirmed by CPC↔vertical
              overlap — name-only candidates are not shown.
            </p>
          </section>
        )}

        {researchInstitutions.length > 0 && (
          <section className="mb-8">
            <h2 className="font-mono text-[11px] uppercase tracking-[0.18em] text-accent mb-2">
              Research footprint
            </h2>
            <p className="font-sans text-sm text-text">
              Publishes as{" "}
              {researchInstitutions.map((inst, i) => (
                <span key={inst}>
                  {i > 0 && ", "}
                  <Link
                    href={`/trends/foresight/research?q=${encodeURIComponent(`institution:"${inst}"`)}`}
                    className="text-accent hover:underline">
                    {inst}
                  </Link>
                </span>
              ))}{" "}
              in the 45M-paper research corpus.
            </p>
          </section>
        )}

      <VentureAttribution />
    </div>
  );
}
