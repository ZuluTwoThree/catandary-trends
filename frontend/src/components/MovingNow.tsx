import Link from "next/link";
import { getLatestClusterRun } from "@/lib/foresight";
import { getVerticalInfo } from "@/lib/types";
import type { Vertical } from "@/lib/types";

/**
 * "What's moving right now" strip for the landing page (Epic W2.6). Value-first:
 * the top rising clusters from the latest global snapshot, in plain language,
 * above the article grid — so a first-time visitor sees the product's edge in
 * ten seconds. Server component, reads the persisted snapshot (no clustering in
 * the request path). Renders nothing if no run exists yet (never an empty box).
 */
export default async function MovingNow() {
  const data = await getLatestClusterRun("global");
  if (!data) return null;
  const rising = data.clusters
    .filter((c) => c.momentum === "rising" && c.n_sources >= 3)
    .sort((a, b) => b.sov_delta_pp - a.sov_delta_pp)
    .slice(0, 5);
  if (rising.length < 3) return null;

  return (
    <section className="mb-10">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted">
          <span className="text-accent">What's moving</span>
          <span className="text-muted/70"> / rising clusters</span>
        </h2>
        <Link
          href="/trends/foresight/radar"
          className="text-[11px] uppercase tracking-wider text-muted hover:text-accent"
        >
          Open radar →
        </Link>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {rising.map((c) => {
          const v = c.verticals[0]
            ? getVerticalInfo(c.verticals[0] as Vertical)
            : null;
          return (
            <Link
              key={c.id}
              href={`/trends/foresight/clusters?vertical=${c.verticals[0] ?? ""}`}
              className="group rounded-lg border border-border p-4 transition-colors hover:border-accent/50"
            >
              <div className="flex items-center gap-2">
                {v && (
                  <span
                    className="inline-block h-2 w-2 rounded-full"
                    style={{ background: v.color }}
                  />
                )}
                <span className="text-[10px] uppercase tracking-wider text-muted">
                  {v?.label ?? "Cross-industry"}
                </span>
              </div>
              <div className="mt-1.5 font-medium leading-snug group-hover:text-accent">
                {c.label}
              </div>
              <div className="mt-1 text-xs text-muted">
                rising for months · corroborated by {c.n_sources} sources
              </div>
            </Link>
          );
        })}
      </div>
    </section>
  );
}
