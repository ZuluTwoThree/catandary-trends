import Link from "next/link";
import { notFound } from "next/navigation";
import {
  getResearchWorkById, resolveCorpusIds, type CorpusRef,
} from "@/lib/db";
import {
  liveAccess, consumeLive, liveWorkContext, peekLiveWork,
  LIVE_DAILY_LIMIT, type LiveWork, type LiveHit,
} from "@/lib/openalex-live";
import TierGate from "@/components/TierGate";
import { splitAuthors } from "@/lib/research-authors";
import { canAccess } from "@/lib/entitlement";

export const dynamic = "force-dynamic";

/** Paper-Detailseite (#83): lokaler Korpus-Stand plus Super-Pro-Live-Block
 *  (aktuelle Zitationen, Jahres-Sparkline, wer zitiert, worauf es baut,
 *  ähnliche Arbeiten). Live-Abfragen zählen gegen das 25/Tag-Budget;
 *  Cache-Treffer (24 h) sind budgetfrei. */

const fmtInt = (n: number) => n.toLocaleString("en-US");

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const w = /^W\d{3,}$/.test(id) ? await getResearchWorkById(id) : null;
  return {
    title: w ? `${w.title.slice(0, 80)} — Research Explorer` : "Paper — Research Explorer",
  };
}

function HitRow({ h, inCorpus }: { h: LiveHit; inCorpus: Set<string> }) {
  const internal = inCorpus.has(h.id);
  const href = internal
    ? `/trends/foresight/research/paper/${h.id}`
    : h.doi ?? `https://openalex.org/${h.id}`;
  return (
    <li className="py-2 border-b border-border last:border-b-0">
      {internal ? (
        <Link href={href} className="font-sans text-[13px] text-paper hover:text-accent leading-snug">
          {h.title}
        </Link>
      ) : (
        <a href={href} target="_blank" rel="noopener noreferrer"
           className="font-sans text-[13px] text-paper hover:text-accent leading-snug">
          {h.title}
        </a>
      )}
      <div className="font-mono text-[10px] text-muted mt-0.5">
        {h.year ?? "—"}
        {h.cited_by_count !== null && <> · {fmtInt(h.cited_by_count)} citations</>}
        {!internal && <span className="text-muted/60"> · external</span>}
      </div>
    </li>
  );
}

function RefRow({ r }: { r: CorpusRef }) {
  return (
    <li className="py-2 border-b border-border last:border-b-0">
      <Link href={`/trends/foresight/research/paper/${r.id}`}
            className="font-sans text-[13px] text-paper hover:text-accent leading-snug">
        {r.title}
      </Link>
      <div className="font-mono text-[10px] text-muted mt-0.5">
        {r.year ?? "—"}
        {r.cited_by_count !== null && <> · {fmtInt(r.cited_by_count)} citations</>}
      </div>
    </li>
  );
}

export default async function PaperDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  if (!/^W\d{3,}$/.test(id)) notFound();
  const w = await getResearchWorkById(id);
  if (!w) notFound();

  const isLandmark = (w.fwci ?? 0) >= 25 && (w.cited_by_count ?? 0) >= 100;
  const searchHref = (extra: string) =>
    `/trends/foresight/research?${extra}`;

  // ---- Live-Block (Super Pro, 25/Tag) ----
  const superpro = await canAccess("superpro");
  let live: LiveWork | null = null;
  let liveState: "ok" | "budget" | "unavailable" | "gated" = "gated";
  let liveUsed = 0;
  let liveUnlimited = true;
  if (superpro) {
    const access = await liveAccess();
    liveUnlimited = access.unlimited;
    if (access.unlimited || access.remaining > 0) {
      const r = await liveWorkContext(id);
      live = r.data;
      if (r.fresh) await consumeLive(access);
      liveUsed = access.used + (r.fresh && !access.unlimited ? 1 : 0);
      liveState = live ? "ok" : "unavailable";
    } else {
      live = await peekLiveWork(id); // alter Cache ist besser als nichts
      liveUsed = access.used;
      liveState = live ? "ok" : "budget";
    }
  }

  const [citingCorpus, refs, related] = live
    ? await Promise.all([
        resolveCorpusIds(live.citing.map((c) => c.id)),
        resolveCorpusIds(live.referenced_works),
        resolveCorpusIds(live.related_works),
      ])
    : [[], [], []];
  const citingIds = new Set(citingCorpus.map((c) => c.id));
  const delta = live?.cited_by_count != null && w.cited_by_count != null
    ? live.cited_by_count - w.cited_by_count : null;
  const maxYearCites = Math.max(1, ...(live?.counts_by_year ?? []).map((c) => c.cited_by_count));

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <div className="mb-6 font-mono text-[10px] uppercase tracking-[0.14em]">
        <Link href="/trends/foresight/research" className="text-muted hover:text-accent">
          ← Research Explorer
        </Link>
      </div>

      <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-accent mb-3 flex flex-wrap gap-x-4 gap-y-1">
        {w.topic && (
          <Link href={searchHref(`topic=${encodeURIComponent(w.topic)}`)}
                className="hover:underline">{w.topic}</Link>
        )}
        <span className="text-muted">{w.year ?? "—"}</span>
        {w.type === "review" && <span className="text-paper">Review</span>}
        {isLandmark && <span className="text-paper">Landmark</span>}
        {w.is_retracted && <span className="text-red-400">Retracted</span>}
      </div>

      <h1 className="font-display text-3xl md:text-4xl leading-[1.1] tracking-tight text-paper mb-4">
        {w.title}
      </h1>

      <div className="font-sans text-[13px] text-muted mb-6 space-y-1">
        {(() => {
          const { shown, more } = splitAuthors(w.authors, 12);
          if (!shown.length) return null;
          return (
            <div className="text-text">
              {shown.map((a, i) => (
                <span key={a + i}>
                  {i > 0 && ", "}
                  <Link href={`/trends/foresight/research?q=${encodeURIComponent(`author:"${a}"`)}`}
                        className="hover:text-accent">{a}</Link>
                </span>
              ))}
              {more > 0 && <span className="text-muted"> +{more} more</span>}
            </div>
          );
        })()}
        {w.institutions && <div>{w.institutions}</div>}
        <div>
          {w.journal && <span className="text-text">{w.journal}</span>}
          {w.journal && w.published && " · "}
          {w.published && new Date(w.published).toLocaleDateString("en-US",
            { day: "numeric", month: "short", year: "numeric" })}
        </div>
      </div>

      {w.abstract && (
        <p className="font-sans text-[15px] leading-relaxed text-text mb-8 max-w-3xl">
          {w.abstract}
        </p>
      )}

      <div className="flex flex-wrap gap-x-6 gap-y-2 mb-10 font-mono text-[11px] uppercase tracking-[0.1em]">
        <span className="text-muted">
          <span className="text-paper text-sm">{fmtInt(w.cited_by_count ?? 0)}</span> citations (snapshot)
        </span>
        {w.fwci !== null && (
          <span className="text-muted" title="Field-weighted citation impact">
            FWCI <span className="text-paper text-sm">{w.fwci.toFixed(1)}</span>
          </span>
        )}
        {w.doi && (
          <a href={w.doi} target="_blank" rel="noopener noreferrer"
             className="text-accent/70 hover:text-accent">DOI →</a>
        )}
        {(live?.oa_url ?? w.oa_url) && (
          <a href={live?.oa_url ?? w.oa_url ?? "#"} target="_blank" rel="noopener noreferrer"
             className="text-accent/70 hover:text-accent">Full text (OA) →</a>
        )}
      </div>

      {/* ---------- Live signal ---------- */}
      <TierGate
        need="superpro"
        feature="Live citation intelligence"
        benefit="Super Pro checks this paper live against OpenAlex: current citation count, the citation curve, who builds on it right now, and its roots in the corpus — 25 live lookups per day."
        teaser={
          <div className="border border-border bg-card p-5">
            <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">
              Live citation intelligence — Super Pro
            </div>
          </div>
        }
      >
        <section className="border border-border-strong bg-card p-5 md:p-6">
          <div className="flex flex-wrap items-baseline justify-between gap-2 mb-5">
            <h2 className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent">
              —— Live signal
            </h2>
            <span className="font-mono text-[10px] text-muted">
              {liveState === "ok" && !liveUnlimited &&
                `live lookups today: ${liveUsed}/${LIVE_DAILY_LIMIT}`}
              {liveState === "ok" && liveUnlimited && "cached up to 24 h"}
            </span>
          </div>

          {liveState === "budget" && (
            <p className="font-sans text-sm text-muted">
              Daily live budget used ({LIVE_DAILY_LIMIT}/{LIVE_DAILY_LIMIT}) — showing
              snapshot data only. Resets at midnight.
            </p>
          )}
          {liveState === "unavailable" && (
            <p className="font-sans text-sm text-muted">
              Live source unreachable right now — snapshot data above remains valid.
            </p>
          )}

          {live && (
            <>
              <div className="flex flex-wrap gap-x-8 gap-y-3 mb-6">
                <div>
                  <div className="font-display text-3xl text-paper leading-none">
                    {live.cited_by_count !== null ? fmtInt(live.cited_by_count) : "—"}
                  </div>
                  <div className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted mt-1">
                    citations live
                    {delta !== null && delta > 0 && (
                      <span className="text-accent"> +{fmtInt(delta)} vs snapshot</span>
                    )}
                  </div>
                </div>
                {live.counts_by_year.length > 1 && (
                  <div className="flex items-end gap-[3px] h-16" aria-label="Citations per year">
                    {live.counts_by_year.map((c) => (
                      <div key={c.year} className="flex flex-col items-center gap-1"
                           title={`${c.year}: ${fmtInt(c.cited_by_count)} citations`}>
                        <div className="w-[14px] bg-accent/80"
                             style={{ height: `${Math.max(2, Math.round((c.cited_by_count / maxYearCites) * 48))}px` }} />
                        <div className="h-3 font-mono text-[8px] text-muted">
                          {c.year % 100 === 0 || c.year === live.counts_by_year[0].year ||
                           c.year === live.counts_by_year[live.counts_by_year.length - 1].year
                            ? String(c.year).slice(2) : ""}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="grid md:grid-cols-2 gap-x-8 gap-y-6">
                {live.citing.length > 0 && (
                  <div>
                    <h3 className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted mb-1">
                      Cited by — top (live)
                    </h3>
                    <ul>{live.citing.map((h) => <HitRow key={h.id} h={h} inCorpus={citingIds} />)}</ul>
                  </div>
                )}
                {refs.length > 0 && (
                  <div>
                    <h3 className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted mb-1">
                      Builds on — {fmtInt(live.referenced_works.length)} references,{" "}
                      {fmtInt(refs.length)} in corpus
                    </h3>
                    <ul>{refs.slice(0, 8).map((r) => <RefRow key={r.id} r={r} />)}</ul>
                  </div>
                )}
                {related.length > 0 && (
                  <div className="md:col-span-2">
                    <h3 className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted mb-1">
                      Related works in corpus
                    </h3>
                    <ul className="grid md:grid-cols-2 gap-x-8">
                      {related.slice(0, 6).map((r) => <RefRow key={r.id} r={r} />)}
                    </ul>
                  </div>
                )}
              </div>
            </>
          )}
        </section>
      </TierGate>

      <div className="mt-8 font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
        Source:{" "}
        <a href={`https://openalex.org/${w.id}`} target="_blank" rel="noopener noreferrer"
           className="text-accent/70 hover:text-accent">OpenAlex (CC0)</a>
        {" "}· snapshot + live API
      </div>
    </div>
  );
}
