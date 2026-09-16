import Link from "next/link";
import { getClusterScopes, getLatestClusterRun } from "@/lib/foresight";
import { VERTICALS } from "@/lib/types";
import ClusterCard from "@/components/foresight/ClusterCard";
import { runProvenance } from "@/lib/clusterCard";
import SnapshotRecompute from "../SnapshotRecompute";
import ForesightCta from "@/components/ForesightCta";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Trend Clusters — Catandary Trends",
  description:
    "What's moving right now: data-driven trend clusters from the recent signal space, with share-of-attention momentum measured on a fixed source panel.",
};

/**
 * Low-threshold UX: the page loads with a finished editorial default view
 * ("what's moving now" — clusters sorted rising-first across all verticals).
 * The vertical tab row is the only visible control; everything else is
 * plain-language cards with evidence one click away.
 */
export default async function ClustersExplorerPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const raw = await searchParams;
  const requested = typeof raw.vertical === "string" ? raw.vertical.toUpperCase() : null;
  const scope = requested ? `vertical:${requested}` : "global";
  const notice = typeof raw.worker === "string" ? raw.worker : undefined;

  const available = new Set(await getClusterScopes());
  const data =
    (await getLatestClusterRun(scope)) ??
    (scope !== "global" ? await getLatestClusterRun("global") : null);

  // Default sort: what's moving — rising first (by SoV delta), then size.
  const clusters = (data?.clusters ?? [])
    .slice()
    .sort((a, b) => b.sov_delta_pp - a.sov_delta_pp || b.size - a.size);

  const asOf = data?.run.created_at
    ? new Date(data.run.created_at + "Z").toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
      })
    : null;

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <div className="mb-10">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-4">
          —— Signal Space
        </div>
        <h1 className="font-display text-4xl md:text-[52px] leading-[1.05] tracking-tight text-paper mb-4">
          What&apos;s <span className="italic">moving</span> now
        </h1>
        <p className="font-sans text-text text-lg leading-relaxed max-w-2xl">
          Trend clusters discovered directly in{" "}
          {data ? (
            <span className="text-paper tabular-nums">
              {data.run.signals.toLocaleString("en-US")}
            </span>
          ) : (
            "our"
          )}{" "}
          analyzed signals of the{" "}
          {data?.run.window_months ? `last ${data.run.window_months} months` : "archive"} —
          grouped by meaning, ranked by how their share of attention moved.
          {asOf && <span className="text-muted"> Computed {asOf}.</span>}
        </p>
        {data && (
          <p className="font-sans text-sm text-muted leading-relaxed max-w-2xl mt-3">
            {runProvenance(data.run)}
          </p>
        )}
      </div>

      {/* Radar rule (Owner 2026-09-15): a document with a date and a button, no cron. */}
      <SnapshotRecompute
        mode="clusters"
        asOf={asOf}
        back={requested ? `/trends/foresight/clusters?vertical=${requested}` : "/trends/foresight/clusters"}
        notice={notice}
      />

      {/* Single visible control: vertical tabs (only scopes that exist) */}
      <div className="flex items-center gap-1 flex-wrap mb-8">
        <Link
          href="/trends/foresight/clusters"
          className={`font-mono text-[10px] uppercase tracking-[0.14em] px-3 py-1.5 border transition-colors ${
            scope === "global"
              ? "text-accent border-accent bg-accent/10"
              : "text-muted border-border hover:text-paper"
          }`}
        >
          All industries
        </Link>
        {VERTICALS.filter((v) => available.has(`vertical:${v.id}`)).map((v) => (
          <Link
            key={v.id}
            href={`/trends/foresight/clusters?vertical=${v.id}`}
            className={`font-mono text-[10px] uppercase tracking-[0.14em] px-3 py-1.5 border transition-colors ${
              scope === `vertical:${v.id}`
                ? "text-accent border-accent bg-accent/10"
                : "text-muted border-border hover:text-paper"
            }`}
          >
            {v.label}
          </Link>
        ))}
      </div>

      {clusters.length === 0 ? (
        <div className="border border-border bg-card/40 p-10 text-center">
          <p className="font-sans text-text mb-2">
            Cluster snapshots are being computed.
          </p>
          <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
            The first analysis run over the signal space has not been persisted
            yet — check back shortly.
          </p>
        </div>
      ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {clusters.map((c) => (
              <ClusterCard key={c.id} cluster={c} showVerticals={scope === "global"} />
            ))}
          </div>
      )}

      <div className="mt-12">
        <ForesightCta />
      </div>
    </div>
  );
}
