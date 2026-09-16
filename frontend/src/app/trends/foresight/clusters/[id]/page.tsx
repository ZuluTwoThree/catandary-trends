import Link from "next/link";
import { notFound } from "next/navigation";
import { getClusterDetail, getClusterNeighbours } from "@/lib/foresight";
import { getMegaTrendInfo } from "@/lib/types";
import MomentumBadge from "@/components/foresight/MomentumBadge";
import Sparkline from "@/components/foresight/Sparkline";
import {
  clusterSummary,
  cohesionLabel,
  concentrationNote,
  megaAttribution,
  runProvenance,
  sharePct,
  spreadBySource,
} from "@/lib/clusterCard";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Cluster — Catandary Trends",
};

/**
 * Cluster detail (2026-09-15). Before this route a card was a dead end: it
 * stood for up to 113,000 signals and showed three of them. The centroid is
 * persisted with every cluster, so the full neighbourhood is one pgvector
 * lookup — closest first for "what is this", newest first for "what is
 * happening now" — plus the numbers the card deliberately keeps small.
 *
 * Owner-only by inheritance: everything under /trends/foresight is in
 * BLOCKED_PREFIXES and excluded from the static export.
 */
export default async function ClusterDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const clusterId = Number(id);
  if (!Number.isInteger(clusterId) || clusterId <= 0) notFound();

  const data = await getClusterDetail(clusterId);
  if (!data) notFound();
  const { run, cluster } = data;

  const neighbours = await getClusterNeighbours(clusterId, 200);
  const closest = spreadBySource(neighbours, 12);
  const newest = spreadBySource(
    [...neighbours]
      .filter((n) => n.date)
      .sort((a, b) => (b.date ?? "").localeCompare(a.date ?? "")),
    12
  );

  const series = cluster.monthly_series;
  const mega = megaAttribution(cluster) ? getMegaTrendInfo(cluster.mega_trend!) : undefined;
  const conc = concentrationNote(cluster);
  const vertical = run.scope.startsWith("vertical:") ? run.scope.slice(9) : null;
  const backHref = vertical
    ? `/trends/foresight/clusters?vertical=${vertical}`
    : "/trends/foresight/clusters";

  const stats: { label: string; value: string; title?: string }[] = [
    { label: "Signals", value: cluster.size.toLocaleString("en-US") },
    { label: "Sources", value: String(cluster.n_sources) },
    {
      label: "Largest source",
      value: cluster.top_source
        ? `${Math.round(cluster.top_source_share * 100)} %`
        : "—",
      title: cluster.top_source ?? undefined,
    },
    {
      label: "Cohesion",
      value: `${cluster.cohesion.toFixed(2)} · ${cohesionLabel(cluster.cohesion)}`,
      title: "Mean cosine of a member to the cluster centre.",
    },
    {
      label: "Share early → late",
      value:
        cluster.share_early == null || cluster.share_late == null
          ? "—"
          : `${sharePct(cluster.share_early)} → ${sharePct(cluster.share_late)}`,
      title: "Share of the fixed panel's signals in the early and late third of the window.",
    },
    {
      label: "Items, late vs early",
      value:
        cluster.vol_delta_pct == null
          ? "—"
          : `${cluster.vol_delta_pct > 0 ? "+" : ""}${Math.round(cluster.vol_delta_pct)} %`,
      title: "Raw item count. The corpus itself grew over this window, so read it as intake, not as the theme's growth.",
    },
  ];

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <Link
        href={backHref}
        className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted hover:text-accent transition-colors"
      >
        ← {vertical ? `${vertical} clusters` : "All clusters"}
      </Link>

      <div className="mt-6 mb-8">
        <div className="flex items-start justify-between gap-4 mb-4">
          <h1 className="font-display text-4xl leading-[1.08] tracking-tight text-paper">
            {cluster.label}
          </h1>
          <MomentumBadge momentum={cluster.momentum} deltaPp={cluster.sov_delta_pp} />
        </div>
        <p className="font-sans text-lg text-text leading-relaxed max-w-2xl">
          {clusterSummary(cluster)}
        </p>
        {conc.text && (
          <p className="font-sans text-sm text-muted mt-2 max-w-2xl">{conc.title}</p>
        )}
        {mega && (
          <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted mt-3">
            Mostly part of <span className="text-paper">{mega.name_en}</span>{" "}
            <span className="tabular-nums">({Math.round(cluster.mega_purity * 100)} %)</span>
          </p>
        )}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-6 gap-px bg-border border border-border mb-8">
        {stats.map((s) => (
          <div key={s.label} className="bg-card/60 p-3" title={s.title}>
            <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-muted mb-1">
              {s.label}
            </div>
            <div className="font-mono text-sm text-paper tabular-nums">{s.value}</div>
          </div>
        ))}
      </div>

      {series.length >= 2 && (
        <section className="mb-10">
          <h2 className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted mb-3">
            Share of monthly signal volume
          </h2>
          <Sparkline
            points={series.map((p) => p.share)}
            months={series.map((p) => p.m)}
            label={cluster.label}
            className="w-full h-24"
          />
          <div className="flex justify-between font-mono text-[10px] text-muted mt-1 tabular-nums">
            <span>{series[0].m}</span>
            <span>{series[series.length - 1].m}</span>
          </div>
        </section>
      )}

      <div className="grid md:grid-cols-2 gap-8 mb-10">
        <SignalList
          title="Closest to the centre"
          hint="What the cluster is about, ranked by similarity."
          rows={closest}
          showSim
        />
        <SignalList
          title="Most recent"
          hint="The same neighbourhood, newest first."
          rows={newest}
        />
      </div>

      {cluster.top_tags.length > 0 && (
        <section className="mb-10">
          <h2 className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted mb-3">
            Tags in this cluster
          </h2>
          <div className="flex flex-wrap gap-2">
            {cluster.top_tags.map((t) => (
              <span
                key={t}
                className="font-mono text-[10px] text-muted border border-border px-2 py-1"
              >
                {t}
              </span>
            ))}
          </div>
        </section>
      )}

      <section className="border-t border-border pt-6">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted mb-3">
          How this was measured
        </h2>
        <p className="font-sans text-sm text-text leading-relaxed max-w-3xl mb-2">
          {runProvenance(run)}
        </p>
        <p className="font-sans text-sm text-muted leading-relaxed max-w-3xl">
          Share of attention compares the early and late third of the observation
          window and is zero-sum across clusters: one theme surging pushes the
          others down even when they grew, which is why the item count is stated
          separately. Months in which a source delivered far above its own median
          are damped back to it, so a back-ingest cannot look like momentum. The
          running month is left out entirely. Signals listed here are the nearest
          neighbours of the cluster centre in the same scope and window, not a
          stored membership list.
        </p>
      </section>
    </div>
  );
}

function SignalList({
  title,
  hint,
  rows,
  showSim = false,
}: {
  title: string;
  hint: string;
  rows: {
    id: number;
    title: string;
    source_name: string | null;
    source_url: string | null;
    slug: string | null;
    status: string | null;
    date: string | null;
    sim: number;
  }[];
  showSim?: boolean;
}) {
  return (
    <section>
      <h2 className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted mb-1">
        {title}
      </h2>
      <p className="font-sans text-xs text-muted mb-3">{hint}</p>
      {rows.length === 0 ? (
        <p className="font-sans text-sm text-muted">No neighbours returned.</p>
      ) : (
        <ul className="space-y-2.5">
          {rows.map((r) => {
            const href =
              r.status === "published" && r.slug ? `/trends/${r.slug}` : r.source_url;
            const inner = (
              <>
                {r.title}
                {r.source_name && <span className="text-muted"> — {r.source_name}</span>}
              </>
            );
            return (
              <li key={r.id} className="text-sm leading-snug">
                <span className="font-mono text-[10px] text-muted tabular-nums mr-2">
                  {r.date ?? "—"}
                  {showSim && ` · ${r.sim.toFixed(2)}`}
                </span>
                {href ? (
                  <a
                    href={href}
                    target={href.startsWith("/") ? undefined : "_blank"}
                    rel={href.startsWith("/") ? undefined : "noopener noreferrer"}
                    className="text-text hover:text-accent transition-colors"
                  >
                    {inner}
                  </a>
                ) : (
                  <span className="text-text">{inner}</span>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
