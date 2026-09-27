import Link from "next/link";
import { getEmergingScopes, getEmergingSpace } from "@/lib/emerging";
import { dominantTier, nestTitle } from "@/lib/nestCard";
import { NEIGHBOUR_K, normaliseCoords, projectToSpace } from "@/lib/clusterMap";
import { TIERS } from "@/lib/tiers";
import { VERTICALS } from "@/lib/types";
import ClusterSpace, { type SpaceNestView } from "@/components/foresight/ClusterSpace";
import { getLatestSpaceRun } from "@/lib/signalSpace";
import SnapshotRecompute from "../SnapshotRecompute";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Signal space — Catandary Trends",
  description:
    "The signal pockets in three dimensions and over time: a projected map of the embedding space, and the same pockets on measured axes of age, share and growth.",
};

/**
 * Two 3D views of the emerging-nest snapshot (2026-09-27).
 *
 * The data was already there: every pocket carries its 1024-dim centroid and,
 * from the archive scan, its lookalike count in each of 449 months. Nothing is
 * recomputed here — the page adds the two things that were missing, a set of
 * coordinates and a clock.
 *
 * Owner-only by inheritance: everything under /trends/foresight is 404 under
 * PUBLIC_MODE and never built into the static export, which is also why this
 * page may be interactive where the public pages must stay deterministic.
 */

/** Months sent to the browser, and how many of them only feed the windows. */
const TAIL_MONTHS = 204;
const WARMUP = 24; // 12 for the trailing window, 12 more for the year before it

export default async function SignalSpacePage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const raw = await searchParams;
  const requested = typeof raw.vertical === "string" ? raw.vertical.toUpperCase() : null;
  const tier = typeof raw.tier === "string" ? raw.tier.toLowerCase() : null;
  const scope = tier ? `tier:${tier}` : requested ? `vertical:${requested}` : "global";

  const notice = typeof raw.worker === "string" ? raw.worker : undefined;
  const [availableScopes, space, cloud] = await Promise.all([
    getEmergingScopes(),
    getEmergingSpace(scope),
    getLatestSpaceRun(),
  ]);
  const available = new Set(availableScopes);
  const back = `/trends/foresight/map${tier ? `?tier=${tier}` : requested ? `?vertical=${requested}` : ""}`;
  const cloudAsOf = cloud
    ? new Date(cloud.createdAt.replace(" ", "T") + "Z").toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
      })
    : null;

  const tab = (href: string, label: string, active: boolean) => (
    <Link
      key={href + label}
      href={href}
      className={`font-mono text-[10px] uppercase tracking-[0.14em] px-3 py-1.5 border transition-colors ${
        active ? "text-accent border-accent bg-accent/10" : "text-muted border-border hover:text-paper"
      }`}
    >
      {label}
    </Link>
  );

  const header = (
    <div className="mb-8">
      <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-4">
        —— Signal Space
      </div>
      <h1 className="font-display text-4xl md:text-[52px] leading-[1.05] tracking-tight text-paper mb-4">
        The space, <span className="italic">turning</span>
      </h1>
      <p className="font-sans text-text text-lg leading-relaxed max-w-2xl">
        The same pockets as the emerging layer, given coordinates and a clock. Two
        views: their place in the embedding space, and their age, loudness and
        growth on axes that mean something.
      </p>
      <div className="flex flex-wrap gap-2 mt-6">
        {tab("/trends/foresight/map", "global", scope === "global")}
        {VERTICALS.filter((v) => available.has(`vertical:${v.id}`)).map((v) =>
          tab(`/trends/foresight/map?vertical=${v.id}`, v.id, scope === `vertical:${v.id}`)
        )}
        {TIERS.filter((t) => available.has(`tier:${t}`)).map((t) =>
          tab(
            `/trends/foresight/map?tier=${t}`,
            t === "science" ? "research" : t,
            scope === `tier:${t}`
          )
        )}
      </div>
      <div className="mt-3">
        <Link
          href="/trends/foresight/emerging"
          className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted hover:text-accent"
        >
          ← the pockets as cards, with the recompute button
        </Link>
      </div>
    </div>
  );

  if (!space) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-8">
        {header}
        <div className="border border-border bg-card/30 p-6">
          <p className="font-sans text-text">
            No snapshot for this scope yet. Compute one on the{" "}
            <Link href="/trends/foresight/emerging" className="text-accent hover:underline">
              emerging page
            </Link>{" "}
            — the map reads exactly that artifact and adds no run of its own.
          </p>
        </div>
      </div>
    );
  }

  const { run, nests, centroids, months, totals, corpusRows } = space;

  // Three axes out of 1024, with the price measured rather than assumed.
  const projection = projectToSpace(centroids);
  // Framed on the bulk, not on the single most eccentric pocket — one outlier
  // would otherwise squeeze all 83 into a dot in the middle.
  const coords = normaliseCoords(projection.coords, 0.92);

  const start = Math.max(0, months.length - TAIL_MONTHS);
  const tailMonths = months.slice(start);
  const tailTotals = totals.slice(start);
  const warmup = Math.min(WARMUP, Math.max(0, tailMonths.length - 1));
  const views: SpaceNestView[] = nests.map((n) => {
    const { name, sub } = nestTitle(n);
    const abs = n.first_month ? n.history_months.indexOf(n.first_month) : -1;
    return {
      id: n.id,
      name,
      sub,
      tier: dominantTier(n),
      // Relative to the tail, so it may be NEGATIVE for a pocket that was
      // already datable before the displayed window — which keeps the age on the
      // axis correct instead of resetting it at the window edge.
      firstIndex: abs >= 0 ? abs - start : null,
      hits: n.history_hits.slice(start),
      size: n.size,
      cohesion: n.cohesion,
      nSources: n.n_sources,
      topSource: n.top_source,
      topSourceShare: n.top_source_share,
      taggedShare: n.tagged_share,
      establishedShare: n.established_share,
      firstMonth: n.first_month,
      ageMonths: n.age_months,
      noveltyLift: n.novelty_lift,
      reps: n.reps.slice(0, 3).map((r) => ({
        title: r.title,
        url: r.source_url,
        source: r.source_name,
        date: r.date,
      })),
    };
  });

  const asOf = new Date(run.created_at + "Z").toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
  const residual = run.scanned > 0 ? Math.abs(corpusRows - run.scanned) / run.scanned : 0;
  const shepardReading =
    projection.shepard >= 0.8
      ? "distances are roughly readable"
      : projection.shepard >= 0.6
        ? "neighbourhoods are readable, distances are not"
        : "only the grouping is readable, neither distances nor directions";

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      {header}

      {/* Stamp + button for the signal cloud (stage 3). The two SVG views need
          none: they read the emerging snapshot, which has its own button. */}
      <SnapshotRecompute mode="space" asOf={cloudAsOf} back={back} notice={notice} />

      <ClusterSpace
        months={tailMonths}
        totals={tailTotals}
        nests={views}
        coords={coords}
        warmup={warmup}
        projection={projection}
        cloud={cloud}
        cloudScopeNote={
          scope === "global"
            ? null
            : "The signal cloud is always the whole corpus in one projection, so positions stay comparable. Narrow it with the tier and vertical switches instead of the tabs above."
        }
      />

      <div className="mt-10 grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="border border-border bg-card/30 p-5">
          <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-accent mb-3">
            —— Where the picture comes from
          </div>
          <ul className="font-sans text-[13px] text-text space-y-2 leading-relaxed">
            <li>
              Snapshot <span className="text-paper">{run.scope}</span>, computed {asOf}:{" "}
              {nests.length} pockets out of {run.signals.toLocaleString("en-US")} signals
              in the last {run.window_days} days, each dated against{" "}
              {run.scanned.toLocaleString("en-US")} archive rows.
            </li>
            <li>
              The clock is that archive scan, not a sample: every pocket carries a
              lookalike count for each of {months.length} months. Shown here are the
              last {tailMonths.length - warmup}; the {warmup} before them are loaded
              only to fill the trailing windows.
            </li>
            <li>
              Loudness is a share, never a count —{" "}
              <span className="text-paper">
                lookalikes per 10,000 corpus signals of the same month
              </span>
              , over a trailing twelve. Raw counts would draw our own intake ramp: the
              corpus grew from a few hundred signals a month to over a hundred thousand.
            </li>
            <li>
              The corpus is reconstructed as the snapshot saw it (rows created up to
              the run): {corpusRows.toLocaleString("en-US")} dated rows against the{" "}
              {run.scanned.toLocaleString("en-US")} it scanned, a{" "}
              {(residual * 100).toFixed(2)} % residual of rows whose publication date
              was still in the future that day. Against today&apos;s corpus every
              pocket would appear to fade.
            </li>
            <li>
              Growth compares the trailing year&apos;s share with the year before it. A
              pocket with nothing before it has no ratio and is drawn at the top of the
              axis rather than at infinity.
            </li>
          </ul>
        </div>
        <div className="border border-border bg-card/30 p-5">
          <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-accent mb-3">
            —— What the map cannot do
          </div>
          <p className="font-sans text-[13px] text-text leading-relaxed">
            The map view presses 1,024 dimensions into three by classical MDS. That is
            lossy, and the loss is measured rather than glossed over:
          </p>
          <dl className="mt-3 space-y-1 font-mono text-[11px]">
            <Fact k="Shepard r" v={projection.shepard.toFixed(3)} />
            <Fact k="variance held" v={`${(projection.varShare * 100).toFixed(1)} %`} />
            <Fact
              k={`${NEIGHBOUR_K} nearest kept`}
              v={`${(projection.neighbourKeep * 100).toFixed(0)} %`}
            />
          </dl>
          <p className="font-sans text-[13px] text-text leading-relaxed mt-3">
            Read as: <span className="text-paper">{shepardReading}</span>. The map axes
            therefore carry no labels and no units — they have none. It is a way to
            navigate and to see density and gaps, not a measurement. Everything that is
            a measurement lives on the other view, where each axis has a unit.
          </p>
          <p className="font-sans text-[12px] text-muted leading-relaxed mt-3">
            A pocket can be dense, brand new and still be the artifact of a single
            mass-ingest — the panel names the largest source and the share of members
            any stage of the pipeline ever read, so that judgement stays with you.
          </p>
        </div>
      </div>
    </div>
  );
}

function Fact({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex gap-2">
      <dt className="text-muted uppercase tracking-[0.1em] w-[140px] shrink-0">{k}</dt>
      <dd className="text-paper">{v}</dd>
    </div>
  );
}
