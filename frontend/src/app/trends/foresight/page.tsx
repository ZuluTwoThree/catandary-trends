import Link from "next/link";
import ForesightCockpit from "@/components/ForesightCockpit";
import {
  getLatestClusterRun,
  getLeadTimeTechnologies,
  cpcDisplayName,
} from "@/lib/foresight";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Foresight Cockpit — Catandary Trends",
  description:
    "Semantic trend search with signal timeline, lead-time analysis and cross-vertical insights.",
};

export default async function ForesightRoute() {
  // Default content for the empty state: the top rising clusters, so the page
  // shows value before any query (value-first, low-threshold UX).
  const [run, leads] = await Promise.all([
    getLatestClusterRun("global"),
    getLeadTimeTechnologies(3),
  ]);
  const topClusters = (run?.clusters ?? [])
    .slice()
    .sort((a, b) => b.sov_delta_pp - a.sov_delta_pp || b.size - a.size)
    .slice(0, 4);
  const clustersAsOf = run?.run.created_at
    ? new Date(run.run.created_at + "Z").toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
    : null;

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      {/* Customer briefing (SCR-Q deck, owner-only like the whole cockpit). */}
      <div className="mb-4 flex justify-end">
        <Link
          href="/trends/foresight/pitch"
          className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted hover:text-accent"
        >
          Briefing deck for prospects →
        </Link>
      </div>
      {/* Lead-time proof strip (#23): the USP, above the fold, one click to the
          full view. Only real, reliable leads. */}
      {leads.length > 0 && (
        <Link
          href="/trends/foresight/lead-time"
          className="block mb-8 border border-border bg-card/40 hover:bg-card transition-colors px-5 py-4"
        >
          <div className="flex items-center justify-between gap-3 mb-2">
            <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent">
              —— Lead time: research ahead of the market
            </span>
            <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
              see all →
            </span>
          </div>
          <div className="flex flex-wrap gap-x-8 gap-y-2">
            {leads.map((t) => (
              <span key={t.cpc} className="font-sans text-sm text-text">
                <span className="text-paper">{cpcDisplayName(t.title, t.curated_name)}</span>
                {" — research "}
                <span className="text-accent">~{t.lead_science_vs_market}y ahead</span>
              </span>
            ))}
          </div>
        </Link>
      )}
      <ForesightCockpit topClusters={topClusters} clustersAsOf={clustersAsOf} />
    </div>
  );
}
