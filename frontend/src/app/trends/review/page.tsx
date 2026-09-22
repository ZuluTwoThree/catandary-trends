import { notFound } from "next/navigation";
import Link from "next/link";
import { canReview } from "@/lib/review-access";
import {
  getHeldDrafts,
  getRecheckQueue,
  getReviewCounts,
  type ReviewItem,
} from "@/lib/review";
import { publishAction, rejectAction, requeueAction } from "./actions";
import { applyProposalAction } from "./agent-actions";
import {
  ageHours,
  getAgentReport,
  NAME_KIND_LABEL,
  PROPOSAL_LABEL,
  type AgentItem,
} from "@/lib/agentReport";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Review queue",
  robots: { index: false, follow: false },
};

/** The corpus re-check of 2026-09-05 (#11) tags its rows with this prefix. */
const RECHECK_PREFIX = "recheck_2026-09-05";

/** Highlight the objected-to tokens (figures AND person names) inside the body. */
function markFlagged(body: string, flagged: string[]) {
  if (!flagged.length) return body;
  const esc = flagged.map((f) => f.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const parts = body.split(new RegExp(`(${esc.join("|")})`, "g"));
  const set = new Set(flagged);
  return parts.map((p, i) =>
    set.has(p) ? (
      <mark key={i} className="bg-warn/25 text-warn px-0.5 font-semibold">
        {p}
      </mark>
    ) : (
      <span key={i}>{p}</span>
    )
  );
}

/**
 * What the review agent found for this article (scripts/review_agent.py).
 *
 * The gate only says WHICH token it could not find; the agent says whether the
 * source states the same thing in another form - "1 000" for "1,000",
 * "Seventy percent" for "70%", a Japanese rendering for "Hisaaki Kato" - and,
 * for names, which of several very different cases it is. The dangerous one is
 * role_only: the source names an office, the model filled in a person from its
 * training data, so a changed office-holder becomes a false attribution.
 *
 * Every line here quotes the source; the agent checked each quote verbatim.
 */
function AgentFindings({ item, agent }: { item: ReviewItem; agent: AgentItem }) {
  const names = agent.names.filter((n) => !n.ok);
  const figures = agent.figures.filter((f) => !f.ok);
  const confirmed = [
    ...agent.names.filter((n) => n.ok).map((n) => ({ label: n.name, evidence: n.evidence, form: "" })),
    ...agent.figures.filter((f) => f.ok).map((f) => ({ label: f.token, evidence: f.evidence, form: f.form })),
  ];
  if (!names.length && !figures.length && !confirmed.length && !agent.proposals.length) return null;
  return (
    <section className="border-b border-border bg-card/40 px-5 py-3">
      <h3 className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">Agent check</h3>
      <ul className="mt-2 space-y-1.5 text-[12px] leading-[1.6]">
        {names.map((n) => (
          <li key={"n-" + n.name}>
            <span className={n.kind === "role_only" ? "text-warn" : "text-paper"}>{n.name}</span>
            <span className="text-muted"> &mdash; {NAME_KIND_LABEL[n.kind] ?? n.kind}</span>
            {n.source_form && (
              <span className="text-muted">
                {" "}&middot; source writes <span className="text-paper">&ldquo;{n.source_form}&rdquo;</span>
              </span>
            )}
            {n.latin && <span className="text-muted"> &middot; romanised &ldquo;{n.latin}&rdquo;</span>}
          </li>
        ))}
        {figures.map((f) => (
          <li key={"f-" + f.token}>
            <span className="text-paper">{f.token}</span>
            <span className="text-muted"> &mdash; not supported by the source ({f.why})</span>
          </li>
        ))}
        {confirmed.map((c) => (
          <li key={"ok-" + c.label} className="text-muted">
            <span className="text-paper">{c.label}</span> &mdash; source says{" "}
            <span className="text-paper">&ldquo;{c.evidence}&rdquo;</span>
            {c.form ? " (" + c.form + ")" : ""}
          </li>
        ))}
      </ul>
      {agent.proposals.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-border pt-3">
          <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">One-click</span>
          {agent.proposals.map((p, i) => (
            <form action={applyProposalAction} key={"p-" + i}>
              <input type="hidden" name="id" value={item.id} />
              <input type="hidden" name="index" value={i} />
              <button
                type="submit"
                className="border border-accent/40 px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-accent hover:bg-accent/10 transition-colors"
                title={p.note + " \u2014 the result is checked by the same gates as auto-publish; if one objects, nothing is written."}
              >
                {PROPOSAL_LABEL[p.kind] ?? p.kind}: {p.what}
                {p.to ? " \u2192 " + p.to : ""}
              </button>
            </form>
          ))}
        </div>
      )}
    </section>
  );
}

function Card({ item, agent }: { item: ReviewItem; agent?: AgentItem }) {
  const date = new Date(item.createdAt).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
  const highlights = [...item.flagged, ...item.names];
  // A failed generation (cut off or garbled) can be written again; a story
  // problem cannot.
  const failedGeneration = item.truncated || item.garbled.length > 0;
  return (
    <article className="border border-border">
      <header className="border-b border-border px-5 py-4">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
          <span>#{item.id}</span>
          {item.vertical && <span className="text-accent">{item.vertical}</span>}
          <span>{date}</span>
          {item.confidence != null && <span>conf {item.confidence.toFixed(2)}</span>}
          {item.status === "review" && <span className="text-paper">in review</span>}
          {item.truncated && <span className="text-warn">cut off mid-sentence</span>}
          {item.garbled.length > 0 && <span className="text-warn">garbled</span>}
          {item.names.length > 0 && <span className="text-warn">ungrounded name</span>}
        </div>
        <h2 className="mt-2 font-display text-[21px] leading-[1.2] text-paper">
          {item.title}
        </h2>
        {item.sourceName && (
          <p className="mt-1 text-[13px] text-muted">
            {item.sourceUrl ? (
              <a href={item.sourceUrl} target="_blank" rel="noopener noreferrer"
                 className="text-accent hover:underline">
                {item.sourceName} ↗
              </a>
            ) : (
              item.sourceName
            )}
          </p>
        )}
        {item.reviewReason && (
          <p className="mt-2 font-mono text-[10px] tracking-[0.06em] text-muted">
            reason: {item.reviewReason}
          </p>
        )}
      </header>

      {item.garbled.length > 0 && (
        <p className="border-b border-border bg-warn/5 px-5 py-2 font-mono text-[11px] text-warn">
          Garbled text: {item.garbled.join(", ")}
        </p>
      )}
      {item.flagged.length > 0 && (
        <p className="border-b border-border bg-warn/5 px-5 py-2 font-mono text-[11px] text-warn">
          Not supported by the source: {item.flagged.map((f) => `"${f}"`).join(", ")}
        </p>
      )}
      {item.names.length > 0 && (
        <p className="border-b border-border bg-warn/5 px-5 py-2 font-mono text-[11px] text-warn">
          Person named differently than in the source: {item.names.map((n) => `"${n}"`).join(", ")}
        </p>
      )}

      {agent && <AgentFindings item={item} agent={agent} />}

      <div className="grid gap-px bg-border md:grid-cols-2">
        <div className="bg-ink px-5 py-4">
          <h3 className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
            Generated article
          </h3>
          <p className="mt-3 whitespace-pre-wrap text-[14px] leading-[1.7] text-text">
            {markFlagged(item.body, highlights)}
          </p>
        </div>
        <div className="bg-ink px-5 py-4">
          <h3 className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
            What the source actually said
          </h3>
          <p className="mt-3 whitespace-pre-wrap text-[13px] leading-[1.65] text-muted">
            {item.sourceText || "— no source text stored —"}
          </p>
        </div>
      </div>

      <footer className="flex flex-wrap items-center gap-3 border-t border-border px-5 py-4">
        <form action={publishAction}>
          <input type="hidden" name="id" value={item.id} />
          <button
            type="submit"
            className="bg-accent px-4 py-2 font-mono text-[11px] uppercase tracking-[0.14em] font-semibold text-ink hover:bg-accent-deep transition-colors"
          >
            Publish
          </button>
        </form>
        {/* A body that breaks off mid-sentence or is token soup is a failed
            generation, not a bad story — offer to have it written again
            instead of losing the signal. Only shown where it applies, so the
            default two-choice decision stays two choices. */}
        {failedGeneration && (
          <form action={requeueAction}>
            <input type="hidden" name="id" value={item.id} />
            <button
              type="submit"
              className="border border-accent/50 px-4 py-2 font-mono text-[11px] uppercase tracking-[0.14em] text-accent hover:bg-accent/10 transition-colors"
              title="Sends the source entry back through the pipeline tonight; the current model writes a new article."
            >
              Write again
            </button>
          </form>
        )}
        <form action={rejectAction}>
          <input type="hidden" name="id" value={item.id} />
          <button
            type="submit"
            className="border border-warn/50 px-4 py-2 font-mono text-[11px] uppercase tracking-[0.14em] text-warn hover:bg-warn/10 transition-colors"
          >
            Reject
          </button>
        </form>
        <span className="ml-auto font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
          Publishing marks it human-reviewed, not auto-published
        </span>
      </footer>
    </article>
  );
}

type Scope = "today" | "all" | "recheck";

export default async function ReviewPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  // 404 rather than 403: an unauthorised visitor learns nothing about the route.
  if (!canReview()) notFound();

  const sp = await searchParams;
  const scope: Scope =
    sp.scope === "all" ? "all" : sp.scope === "recheck" ? "recheck" : "today";

  const [items, counts, agentReport] = await Promise.all([
    scope === "recheck"
      ? getRecheckQueue({ limit: 100 })
      : getHeldDrafts(scope === "today" ? { sinceHours: 30 } : { limit: 100 }),
    getReviewCounts(),
    getAgentReport(),
  ]);
  const agentAge = ageHours(agentReport);

  const tab = (s: Scope, label: string) => (
    <Link
      href={s === "today" ? "/trends/review" : `/trends/review?scope=${s}`}
      className={scope === s ? "text-accent" : "text-muted hover:text-paper"}
    >
      {label}
    </Link>
  );

  return (
    <div className="mx-auto max-w-5xl px-4 py-10">
      <header className="border-b border-border pb-6">
        <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-accent">
          Quality gate
        </p>
        <h1 className="mt-3 font-display text-[34px] leading-[1.1] text-paper">
          Held for review
        </h1>
        <p className="mt-3 max-w-2xl text-[14px] leading-[1.65] text-muted">
          These articles were kept out of publication because the body states a
          figure, date or <em>person name</em> the source does not support, is
          garbled text, or breaks off mid-sentence. Compare both columns and
          decide; either way the article leaves the queue and the nightly gate
          stops re-checking it. Where the text simply broke off or came out
          garbled, <span className="text-accent">Write again</span> sends the
          source back through tonight&rsquo;s pipeline instead, so the signal
          is not lost to a failed generation. The{" "}
          <span className="text-paper">Re-check</span> tab lists articles the
          corpus sweep of 5 Sep 2026 took off the site (status{" "}
          <code>review</code>) — each card names its reason.
        </p>
        <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 font-mono text-[11px] uppercase tracking-[0.14em]">
          <span className="text-paper">{counts.today} today</span>
          <span className="text-muted">{counts.total} in total</span>
          {counts.oldest && <span className="text-muted">oldest {counts.oldest}</span>}
          <span className="text-muted">{counts.recheck} in re-check</span>
          <span className="ml-auto flex gap-3">
            {tab("today", "Today")}
            {tab("all", "Backlog")}
            {tab("recheck", `Re-check (${counts.recheck})`)}
          </span>
        </div>
      </header>

      {items.length === 0 ? (
        <p className="mt-10 text-[15px] text-muted">
          Nothing to review{scope === "today" ? " from the last run" : ""}. 🎉
          {scope === "today" && counts.total > 0 && (
            <>
              {" "}
              <Link href="/trends/review?scope=all" className="text-accent hover:underline">
                {counts.total} older item(s) are waiting.
              </Link>
            </>
          )}
          {scope !== "recheck" && counts.recheck > 0 && (
            <>
              {" "}
              <Link href="/trends/review?scope=recheck" className="text-accent hover:underline">
                {counts.recheck} item(s) in the re-check queue.
              </Link>
            </>
          )}
        </p>
      ) : (
        <div className="mt-8 space-y-8">
          {agentReport && agentAge != null && scope !== "recheck" && (
            <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
              Agent check from {agentAge < 1 ? "the last hour" : Math.round(agentAge) + " h ago"}
              {agentReport.dryRun ? " (dry run)" : ""} &middot; re-run:{" "}
              <code className="text-paper">scripts/review_agent.py</code>
            </p>
          )}
          {scope === "recheck" && (
            <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
              Showing the newest 100 of {counts.recheck}; prefix {RECHECK_PREFIX} = corpus sweep
            </p>
          )}
          {items.map((i) => (
            <Card key={i.id} item={i} agent={agentReport?.items.get(i.id)} />
          ))}
        </div>
      )}
    </div>
  );
}
