import { getMegaTrendInfo } from "@/lib/types";
import type { ForesightCluster } from "@/lib/foresight";
import MomentumBadge from "./MomentumBadge";
import Sparkline from "./Sparkline";

const SPARK_MONTHS = 36; // readability: recent window, not the 2002+ tail

export default function ClusterCard({ cluster }: { cluster: ForesightCluster }) {
  const mega = cluster.mega_trend ? getMegaTrendInfo(cluster.mega_trend) : undefined;
  const series = cluster.monthly_series.slice(-SPARK_MONTHS);
  const points = series.map((p) => p.share);
  const months = series.map((p) => p.m);

  // Plain-language summary — one statement plus corroboration, no repeated
  // momentum phrase (COPY-16); detail numbers stay in the badge tooltip.
  const corroboration = `confirmed by ${cluster.n_sources.toLocaleString("en-US")} independent source${cluster.n_sources === 1 ? "" : "s"}`;
  const deltaText = `${cluster.sov_delta_pp > 0 ? "+" : ""}${cluster.sov_delta_pp.toFixed(1)} pp share of attention`;
  const summary =
    cluster.momentum === "rising"
      ? `Gaining ground (${deltaText}) — ${corroboration}.`
      : cluster.momentum === "declining"
        ? `Cooling off (${deltaText}) — ${corroboration}.`
        : cluster.momentum === "unknown"
          ? `Newly observed (still too early to call a direction) — ${corroboration}.`
          : `Holding steady — ${corroboration}.`;

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
          <span>
            <span className="text-accent tabular-nums">{cluster.n_sources}</span>{" "}
            sources
          </span>
          {cluster.verticals.length > 0 && (
            <>
              <span className="text-border">·</span>
              <span>{cluster.verticals.join(" / ")}</span>
            </>
          )}
        </div>
        <MomentumBadge momentum={cluster.momentum} deltaPp={cluster.sov_delta_pp} />
      </div>

      <h2 className="font-display text-[22px] leading-tight text-paper">
        {cluster.label}
      </h2>

      <p className="font-sans text-sm text-text leading-relaxed">{summary}</p>

      {points.length >= 2 && (
        <Sparkline points={points} months={months} label={cluster.label} />
      )}

      {mega && (
        <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted">
          Part of <span className="text-paper">{mega.name_en}</span>
        </div>
      )}

      {cluster.reps.length > 0 && (
        <div className="border-t border-border/60 pt-3 mt-1">
          <div className="font-mono text-[9px] uppercase tracking-[0.18em] text-muted mb-2">
            Representative signals
          </div>
          <ul className="space-y-1.5">
            {cluster.reps.slice(0, 3).map((r) => (
              <li key={r.id} className="text-sm leading-snug">
                {r.source_url ? (
                  <a
                    href={r.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-text hover:text-accent transition-colors"
                  >
                    {r.title}
                    {r.source_name && (
                      <span className="text-muted"> — {r.source_name}</span>
                    )}
                  </a>
                ) : (
                  <span className="text-text">{r.title}</span>
                )}
              </li>
            ))}
          </ul>
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
