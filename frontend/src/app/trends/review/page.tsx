import { notFound } from "next/navigation";
import Link from "next/link";
import { canReview } from "@/lib/review-access";
import { getHeldDrafts, getReviewCounts, type ReviewItem } from "@/lib/review";
import { publishAction, rejectAction, requeueAction } from "./actions";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Review queue",
  robots: { index: false, follow: false },
};

/** Highlight the objected-to tokens inside the generated body. */
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

function Card({ item }: { item: ReviewItem }) {
  const date = new Date(item.createdAt).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
  return (
    <article className="border border-border">
      <header className="border-b border-border px-5 py-4">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
          <span>#{item.id}</span>
          {item.vertical && <span className="text-accent">{item.vertical}</span>}
          <span>{date}</span>
          {item.confidence != null && <span>conf {item.confidence.toFixed(2)}</span>}
          {item.truncated && <span className="text-warn">cut off mid-sentence</span>}
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
      </header>

      {item.flagged.length > 0 && (
        <p className="border-b border-border bg-warn/5 px-5 py-2 font-mono text-[11px] text-warn">
          Not supported by the source: {item.flagged.map((f) => `"${f}"`).join(", ")}
        </p>
      )}

      <div className="grid gap-px bg-border md:grid-cols-2">
        <div className="bg-ink px-5 py-4">
          <h3 className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
            Generated article
          </h3>
          <p className="mt-3 whitespace-pre-wrap text-[14px] leading-[1.7] text-text">
            {markFlagged(item.body, item.flagged)}
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
        {/* A body that breaks off mid-sentence is a failed generation, not a
            bad story — offer to have it written again instead of losing the
            signal. Only shown where it applies, so the default two-choice
            decision stays two choices. */}
        {item.truncated && (
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

export default async function ReviewPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  // 404 rather than 403: an unauthorised visitor learns nothing about the route.
  if (!(await canReview())) notFound();

  const sp = await searchParams;
  const scope = sp.scope === "all" ? "all" : "today";

  const [items, counts] = await Promise.all([
    getHeldDrafts(scope === "today" ? { sinceHours: 30 } : { limit: 100 }),
    getReviewCounts(),
  ]);

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
          figure or date the source does not support — or because it breaks off
          mid-sentence. Compare both columns and decide; either way the article
          leaves the queue and the nightly gate stops re-checking it. Where the
          text simply broke off, <span className="text-accent">Write again</span>{" "}
          sends the source back through tonight&rsquo;s pipeline instead, so the
          signal is not lost to a failed generation.
        </p>
        <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 font-mono text-[11px] uppercase tracking-[0.14em]">
          <span className="text-paper">{counts.today} today</span>
          <span className="text-muted">{counts.total} in total</span>
          {counts.oldest && <span className="text-muted">oldest {counts.oldest}</span>}
          <span className="ml-auto flex gap-3">
            <Link href="/trends/review"
              className={scope === "today" ? "text-accent" : "text-muted hover:text-paper"}>
              Today
            </Link>
            <Link href="/trends/review?scope=all"
              className={scope === "all" ? "text-accent" : "text-muted hover:text-paper"}>
              Backlog
            </Link>
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
        </p>
      ) : (
        <div className="mt-8 space-y-8">
          {items.map((i) => (
            <Card key={i.id} item={i} />
          ))}
        </div>
      )}
    </div>
  );
}
