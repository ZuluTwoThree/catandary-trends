import Link from "next/link";
import type { TopicReport, TopicRow } from "@/lib/topicReport";
import { TIERS } from "@/lib/tiers";
import { ageText, curveFor, cutText, pct, TIER_LABEL, tierStripe, weaknesses } from "@/lib/topicView";
import Sparkline from "./Sparkline";

/**
 * The answer to one term (stage 2, 2026-09-17). Order follows the plan: the
 * numbers per tier and the applied cut first, then the word generations —
 * not decoration but the result, because a topic is a sequence of words —
 * then the tier stripe, the 60-month curves, the newest evidence (one per
 * source) and, on every block, the weaknesses.
 */

function Row({ r }: { r: TopicRow }) {
  const inner = (
    <>
      <span className="font-mono text-[10px] text-muted tabular-nums shrink-0 w-[5.5rem]">{r.date ?? "—"}</span>
      <span className="font-sans text-sm text-text leading-snug">{r.title}</span>
      <span className="font-mono text-[10px] text-muted shrink-0">{r.source ?? ""}</span>
      <span className="font-mono text-[10px] text-muted tabular-nums shrink-0" title="cosine similarity to the query">
        {r.sim.toFixed(2)}
      </span>
    </>
  );
  const cls = "flex items-baseline gap-3 py-1 border-b border-border/60 last:border-0";
  if (r.slug) return <Link href={`/trends/${r.slug}`} className={`${cls} hover:text-accent`}>{inner}</Link>;
  if (r.url)
    return (
      <a href={r.url} target="_blank" rel="noopener noreferrer" className={`${cls} hover:text-accent`}>
        {inner}
      </a>
    );
  return <div className={cls}>{inner}</div>;
}

function Label({ children }: { children: React.ReactNode }) {
  return <h2 className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted mb-3">{children}</h2>;
}

export default function TopicReportView({ report }: { report: TopicReport }) {
  const tiers = TIERS.filter((t) => report.tiers[t]);
  const o = report.overall;

  if (report.status === "ambiguous" && report.ambiguity) {
    return (
      <section className="border border-border bg-card/40 p-6 mb-10">
        <Label>Which field?</Label>
        <p className="font-sans text-text mb-4">{report.ambiguity.reason}. Say more — the field, the product, the mechanism — and ask again.</p>
        <div className="grid md:grid-cols-3 gap-4">
          {report.ambiguity.fields.map((f) => (
            <div key={f.vertical} className="border border-border p-3">
              <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-accent mb-2">
                {f.vertical} · {Math.round(f.share * 100)} %
              </div>
              {f.titles.map((t) => (
                <div key={t} className="font-sans text-sm text-muted leading-snug mb-1">{t}</div>
              ))}
            </div>
          ))}
        </div>
      </section>
    );
  }

  const stripe = tierStripe(report);

  return (
    <div className="mb-12">
      {/* head: evidence per tier and the applied cut */}
      <section className="mb-8">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-px bg-border border border-border">
          {tiers.map((t) => {
            const d = report.tiers[t]!;
            return (
              <div key={t} className="bg-card/60 p-4">
                <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-muted mb-1">{TIER_LABEL[t]}</div>
                <div className="font-display text-3xl text-paper tabular-nums leading-none">
                  {d.status === "none" ? "—" : d.hits.toLocaleString("en-US")}
                  {d.capped && <span className="font-mono text-xs text-accent align-top ml-1" title="the neighbour window is full — a floor, not a total">+</span>}
                </div>
                <div className="font-mono text-[10px] text-muted mt-2 tabular-nums">
                  {d.status === "none"
                    ? `nothing close (head ${d.head.toFixed(2)} < ${d.head_min})`
                    : `head ${d.head.toFixed(2)} · cut ${d.cut.toFixed(2)}${d.status === "thin" ? " · thin" : ""}`}
                </div>
              </div>
            );
          })}
        </div>
        <p className="font-mono text-[10px] text-muted mt-2">{cutText(report)}.</p>
        {report.status === "nothing" && (
          <p className="font-sans text-text mt-4">
            Nothing close in any requested tier. Either we have too little on this, or it is phrased in a
            register the corpus does not use — try the words the field itself uses.
          </p>
        )}
      </section>

      {report.status !== "nothing" && (
        <>
          {/* word generations */}
          <section className="mb-10">
            <Label>What it was called, and when</Label>
            {report.vocabulary.length === 0 && report.fulltext_oldest.length === 0 ? (
              <p className="font-sans text-sm text-muted">No earlier vocabulary stayed close enough to the query.</p>
            ) : (
              <div className="grid md:grid-cols-2 gap-8">
                <div>
                  <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted mb-2">
                    earlier word pairs · kept only if close to the query (≥ {report.params.walk_gate})
                  </div>
                  {report.vocabulary.length === 0 ? (
                    <p className="font-sans text-sm text-muted">none</p>
                  ) : (
                    report.vocabulary.map((v) => (
                      <div key={v.term} className="flex items-baseline gap-3 py-1 border-b border-border/60 last:border-0">
                        <span className="font-mono text-[10px] text-accent tabular-nums w-[4rem] shrink-0">{v.first_month}</span>
                        <Link href={`/trends/foresight/topic?q=${encodeURIComponent(v.term)}`} className="font-sans text-sm text-paper hover:text-accent">
                          {v.term}
                        </Link>
                        <span className="font-mono text-[10px] text-muted tabular-nums">{v.hits.toLocaleString("en-US")} rows · {v.sim.toFixed(2)}</span>
                      </div>
                    ))
                  )}
                </div>
                <div>
                  <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted mb-2">
                    oldest by full text · only rows the vector also accepts (≥ {report.params.floor})
                  </div>
                  {report.fulltext_oldest.length === 0 ? (
                    <p className="font-sans text-sm text-muted">none</p>
                  ) : (
                    report.fulltext_oldest.map((r) => <Row key={r.id} r={r} />)
                  )}
                </div>
              </div>
            )}
          </section>

          {/* tier stripe */}
          <section className="mb-10">
            <Label>When each conversation began</Label>
            <div className="flex flex-wrap items-stretch gap-2">
              {stripe.map((s, i) => (
                <div key={s.tier} className="flex items-center gap-2">
                  {i > 0 && (
                    <span className="font-mono text-[10px] text-muted tabular-nums" title="months after the previous conversation">
                      {s.gap == null ? "→" : `+${s.gap} m →`}
                    </span>
                  )}
                  <div className="border border-border bg-card/40 px-4 py-3 min-w-[9rem]">
                    <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-accent">{TIER_LABEL[s.tier]}</div>
                    <div className="font-display text-xl text-paper tabular-nums">{s.sustained ?? s.first_hit ?? "—"}</div>
                    <div className="font-mono text-[10px] text-muted tabular-nums">
                      {s.sustained ? `first hit ${s.first_hit ?? "—"}` : "not sustained · first hit only"}
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <p className="font-sans text-sm text-muted mt-3 max-w-3xl">
              A conversation counts as begun in the first month with three rows above the cut; the first single hit
              is shown beside it. {o.science_to_market_months != null && (
                <>Research to market: <span className="text-paper tabular-nums">{o.science_to_market_months > 0 ? "+" : ""}{o.science_to_market_months} months</span>. </>
              )}
              Novelty lift <span className="text-paper tabular-nums">{o.novelty_lift ?? "—"}</span> (1.0 = spread like the corpus),
              acceleration <span className="text-paper tabular-nums">{o.accel ?? "—"}</span>, established-source share{" "}
              <span className="text-paper tabular-nums">{pct(o.established_share)}</span>, market actors{" "}
              <span className="text-paper tabular-nums">{o.actors_early} → {o.actors_late}</span> (early vs last 12 months).
            </p>
          </section>

          {/* curves + newest per tier */}
          <section className="mb-10">
            <Label>Last 60 months, rows above the cut per month</Label>
            <div className="grid md:grid-cols-2 gap-4">
              {tiers.map((t) => {
                const d = report.tiers[t]!;
                if (d.status === "none") return null;
                const c = curveFor(report, t, 60);
                const flags = weaknesses(d, o.established_share);
                return (
                  <article key={t} className="border border-border bg-card/40 p-5 flex flex-col gap-3">
                    <div className="flex items-baseline justify-between gap-3">
                      <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-accent">{TIER_LABEL[t]}</div>
                      <div className="font-mono text-[10px] text-muted tabular-nums">
                        {d.hits} rows · {d.sources} sources · {d.hits_recent ?? 0} in the last 6 months
                        {d.age_months != null && ` · sustained for ${ageText(d.age_months)}`}
                      </div>
                    </div>
                    {c.points.length > 1 && <Sparkline points={c.points} months={c.months} label={TIER_LABEL[t]} unit="count" className="w-full h-12" />}
                    <div>
                      <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted mb-1">newest · one per source</div>
                      {d.newest.map((r) => <Row key={r.id} r={r} />)}
                    </div>
                    {flags.length > 0 && (
                      <ul className="font-mono text-[10px] text-muted leading-relaxed">
                        {flags.map((f) => (
                          <li key={f.key}>⚠ {f.text}</li>
                        ))}
                      </ul>
                    )}
                  </article>
                );
              })}
            </div>
          </section>
        </>
      )}

      <p className="font-mono text-[10px] text-muted">
        {report.cached ? "from cache" : `computed in ${report.duration_s ?? "?"} s`} · corpus axis {report.corpus.first_month} … {report.corpus.last_month}
        {report.report_id ? ` · report ${report.report_id}` : ""} ·{" "}
        <Link href={`/trends/foresight/topic?q=${encodeURIComponent(report.query)}&tiers=${report.tiers_key}&fresh=1`} className="hover:text-accent">
          recompute
        </Link>
      </p>
    </div>
  );
}
