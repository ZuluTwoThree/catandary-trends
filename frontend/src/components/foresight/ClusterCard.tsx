import Link from "next/link";
import { getMegaTrendInfo } from "@/lib/types";
import type { ForesightCluster } from "@/lib/foresight";
import MomentumBadge from "./MomentumBadge";
import Sparkline from "./Sparkline";
import { clusterSummary, concentrationNote, megaAttribution, cohesionLabel } from "@/lib/clusterCard";

const SPARK_MONTHS = 36; // readability: recent window, not the 2002+ tail

export default function ClusterCard({
  cluster,
  showVerticals = true,
}: {
  cluster: ForesightCluster;
  /** A vertical-scoped run has one vertical on every card — pointless there. */
  showVerticals?: boolean;
}) {
  const mega = megaAttribution(cluster) ? getMegaTrendInfo(cluster.mega_trend!) : undefined;
  const series = cluster.monthly_series.slice(-SPARK_MONTHS);
  const points = series.map((p) => p.share);
  const months = series.map((p) => p.m);
  const conc = concentrationNote(cluster);

  return (
    <article
      id={`cluster-${cluster.id}`}
      className="border border-border bg-card/40 p-6 hover:bg-card hover:border-accent/40 transition-colors flex flex-col gap-3"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="font-mono text-[9px] uppercase tracking-[0.18em] text-muted flex items-center gap-3 flex-wrap">
          <span>
            <span className="text-paper tabular-nums">
              {cluster.size.toLocaleString("en-US")}
            </span>{" "}
            signals
          </span>
          <span className="text-border">·</span>
          <span title={conc.title}>
            <span className="text-accent tabular-nums">{cluster.n_sources}</span> sources
            {conc.text && <span className="text-muted">, {conc.text}</span>}
          </span>
          <span className="text-border">·</span>
          <span title="Mean cosine of a member to the cluster centre — how tightly the signals actually belong together.">
            {cohesionLabel(cluster.cohesion)}
          </span>
          {showVerticals && cluster.verticals.length > 0 && (
            <>
              <span className="text-border">·</span>
              <span>{cluster.verticals.join(" / ")}</span>
            </>
          )}
        </div>
        <MomentumBadge momentum={cluster.momentum} deltaPp={cluster.sov_delta_pp} />
      </div>

      <h2 className="font-display text-[22px] leading-tight text-paper">
        <Link
          href={`/trends/foresight/clusters/${cluster.id}`}
          className="hover:text-accent transition-colors"
        >
          {cluster.label}
        </Link>
      </h2>

      <p className="font-sans text-sm text-text leading-relaxed">{clusterSummary(cluster)}</p>

      {points.length >= 2 && (
        <Sparkline points={points} months={months} label={cluster.label} />
      )}

      {mega && (
        <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted">
          Mostly part of <span className="text-paper">{mega.name_en}</span>{" "}
          <span className="tabular-nums">({Math.round(cluster.mega_purity * 100)} %)</span>
        </div>
      )}

      {cluster.reps.length > 0 && (
        <div className="border-t border-border/60 pt-3 mt-1">
          <div className="font-mono text-[9px] uppercase tracking-[0.18em] text-muted mb-2">
            Recent signals in this cluster
          </div>
          <ul className="space-y-1.5">
            {cluster.reps.slice(0, 3).map((r) => (
              <li key={r.id} className="text-sm leading-snug">
                {r.date && (
                  <span className="font-mono text-[10px] text-muted tabular-nums mr-2">
                    {r.date}
                  </span>
                )}
                {r.source_url ? (
                  <a
                    href={r.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-text hover:text-accent transition-colors"
                  >
                    {r.title}
                    {r.source_name && <span className="text-muted"> — {r.source_name}</span>}
                  </a>
                ) : (
                  <span className="text-text">{r.title}</span>
                )}
              </li>
            ))}
          </ul>
          <Link
            href={`/trends/foresight/clusters/${cluster.id}`}
            className="inline-block mt-3 font-mono text-[10px] uppercase tracking-[0.14em] text-accent hover:underline"
          >
            Open cluster
          </Link>
        </div>
      )}

      {cluster.top_tags.length > 0 && (
        <div className="font-mono text-[9px] tracking-[0.06em] text-muted truncate">
          {cluster.top_tags.slice(0, 6).join(" · ")}
        </div>
      )}
    </article>
  );
}
