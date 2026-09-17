import Link from "next/link";
import { MAX_QUERY_CHARS, parseTiers, runTopicReport } from "@/lib/topicReport";
import { getTopicSuggestions } from "@/lib/topicSuggestions";
import { TIER_LABEL } from "@/lib/topicView";
import { TIERS } from "@/lib/tiers";
import TopicReportView from "@/components/foresight/TopicReportView";
import TopicSuggestions from "@/components/foresight/TopicSuggestions";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Topic — Catandary Trends",
  description: "A term in, the data situation out: per conversation tier, dated, with its earlier vocabulary.",
};

/**
 * Topic search (stage 2 of docs/plan_topic_search_2026-09-16.md). Owner decision
 * 2026-09-16: the user names the topic; the cluster and pocket discovery
 * supplies suggestions underneath. Plain GET form — no JavaScript needed, the
 * URL is the query, a bookmark is a saved search.
 *
 * Owner-only by inheritance: everything under /trends/foresight is blocked under
 * PUBLIC_MODE and never built into the static export.
 */
export default async function TopicPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const raw = await searchParams;
  const q = typeof raw.q === "string" ? raw.q.trim().slice(0, MAX_QUERY_CHARS) : "";
  const tiers = parseTiers(typeof raw.tiers === "string" ? raw.tiers : undefined);
  const fresh = raw.fresh === "1";

  const [result, suggestions] = await Promise.all([
    q ? runTopicReport(q, tiers, fresh) : Promise.resolve(null),
    getTopicSuggestions(),
  ]);

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <div className="mb-8">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-4">—— Signal Space</div>
        <h1 className="font-display text-4xl md:text-[52px] leading-[1.05] tracking-tight text-paper mb-4">
          What do we have on <span className="italic">{q || "a topic"}</span>?
        </h1>
        <p className="font-sans text-text text-lg leading-relaxed max-w-2xl">
          Name it in the words the field uses. Each conversation — research, patents, funding, the market — is
          searched on its own and dated on its own; a science trend is not a market trend even when the topic is
          the same.
        </p>
      </div>

      <form method="get" action="/trends/foresight/topic" className="mb-10 border border-border bg-card/40 p-5">
        <div className="flex flex-col md:flex-row gap-3 md:items-end">
          <label className="flex-1">
            <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted block mb-2">Topic</span>
            <input
              type="text"
              name="q"
              defaultValue={q}
              maxLength={MAX_QUERY_CHARS}
              placeholder="e.g. precision fermentation of dairy proteins"
              className="w-full bg-ink border border-border px-3 py-2 font-sans text-paper focus:border-accent outline-none"
              autoFocus={!q}
            />
          </label>
          <button
            type="submit"
            className="font-mono text-[11px] uppercase tracking-[0.14em] border border-accent text-accent px-5 py-2.5 hover:bg-accent/10"
          >
            Search
          </button>
        </div>
        {/* one hidden `tiers` value is built from the checkboxes: the engine takes a comma list */}
        <fieldset className="mt-4 flex flex-wrap gap-x-6 gap-y-2">
          <legend className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted mb-2">Conversations</legend>
          {TIERS.map((t) => (
            <label key={t} className="flex items-center gap-2 font-sans text-sm text-text">
              <input type="checkbox" name="tiers" value={t} defaultChecked={tiers.includes(t)} className="accent-[#d4ff3a]" />
              {TIER_LABEL[t]}
            </label>
          ))}
        </fieldset>
      </form>

      {result && !result.ok && (
        <div className="border border-border bg-card/40 p-6 mb-10">
          <p className="font-sans text-text mb-2">The engine did not answer.</p>
          <pre className="font-mono text-[11px] text-muted whitespace-pre-wrap">{result.error}</pre>
          <p className="font-mono text-[10px] text-muted mt-3">
            It needs the CPU embedder (systemctl --user start catandary-embed-cpu) and the search table
            (scripts/migrate_topic_vectors.py --indexes).
          </p>
        </div>
      )}
      {result && result.ok && <TopicReportView report={result.report} />}

      <TopicSuggestions {...suggestions} />

      <p className="font-sans text-sm text-muted mt-10 max-w-3xl">
        The pockets come from{" "}
        <Link href="/trends/foresight/emerging" className="text-accent hover:underline">
          the emerging layer
        </Link>
        , which now runs on the whole corpus and the four conversations; it is a finder, this page is the check.
      </p>
    </div>
  );
}
