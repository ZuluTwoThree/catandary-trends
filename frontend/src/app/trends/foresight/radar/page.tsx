import Link from "next/link";
import { getRadarData } from "@/lib/foresight";
import { getEvidence, getRadar, listRadars } from "@/lib/radar";
import { VERTICALS } from "@/lib/types";
import TrendRadar from "@/components/foresight/TrendRadar";
import HorizonBoard from "@/components/foresight/HorizonBoard";
import ForesightCta from "@/components/ForesightCta";
import TierGate from "@/components/TierGate";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Horizon Radar — Catandary Trends",
  description:
    "Technology fields placed on strategic horizons — H1 act, H2 build, H3 watch — per dimension and jurisdiction, with the evidence behind every placement.",
};

/**
 * The radar as a strategic instrument: a chosen set of technology fields, each
 * placed on H1/H2/H3 per dimension and jurisdiction, every cell carrying its
 * reasoning and sources (docs/radar_redesign_proposal.md).
 *
 * The previous lead-time radar stays reachable at ?view=evidence. Its rings
 * encode which *source pool* a cluster's signals came from, which is a corpus
 * partition rather than a maturity statement — it is kept as a corpus overview,
 * not as the default reading.
 */
export default async function RadarPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const raw = await searchParams;
  const wantEvidenceView = raw.view === "evidence";
  const radars = await listRadars();
  const requestedRadar =
    typeof raw.radar === "string" ? raw.radar : radars[0]?.slug ?? null;

  const view = !wantEvidenceView && requestedRadar ? await getRadar(requestedRadar) : null;

  // Resolve every cell's evidence once, server-side, so the client component
  // never has to fetch.
  let evidenceMap: Record<
    number,
    { id: number; title: string; source_url: string | null; source_name: string | null }
  > = {};
  if (view) {
    const ids = [...new Set(view.cells.flatMap((c) => c.evidence))];
    const items = await getEvidence(ids);
    evidenceMap = Object.fromEntries(items.map((i) => [i.id, i]));
  }

  const asOf = (iso: string | null) =>
    iso
      ? new Date(iso.replace(" ", "T") + "Z").toLocaleDateString("en-US", {
          month: "short",
          day: "numeric",
          year: "numeric",
        })
      : null;

  const chip = (active: boolean) =>
    `font-mono text-[10px] uppercase tracking-[0.14em] px-3 py-1.5 border transition-colors ${
      active
        ? "text-accent border-accent bg-accent/10"
        : "text-muted border-border hover:text-paper"
    }`;

  // ---- Horizon radar (default) --------------------------------------------
  if (view) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-8">
        <div className="mb-8">
          <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-4">
            —— Foresight · Radar
          </div>
          <h1 className="font-display text-4xl md:text-[52px] leading-[1.05] tracking-tight text-paper mb-4">
            The horizon <span className="italic">radar</span>
          </h1>
          <p className="font-sans text-text text-lg leading-relaxed max-w-2xl">
            {view.config.description ??
              "Technology fields placed on strategic horizons per dimension and jurisdiction."}{" "}
            A field rarely sits on one horizon: it can be technologically ready
            while still being blocked by regulation in one market and already on
            sale in another.
            {view.generated ? (
              <span className="text-muted"> Updated {asOf(view.generated)}.</span>
            ) : null}
          </p>
        </div>

        {radars.length > 1 && (
          <div className="mb-6 flex flex-wrap items-center gap-1">
            <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted mr-1">
              Radar
            </span>
            {radars.map((r) => (
              <Link
                key={r.slug}
                href={`/trends/foresight/radar?radar=${r.slug}`}
                className={chip(r.slug === view.config.slug)}
              >
                {r.name}
              </Link>
            ))}
          </div>
        )}

        <TierGate
          need="starter"
          feature="The full horizon radar"
          benefit={`Starter opens all ${view.scopes.length} technology fields across every dimension and jurisdiction — each placement with its reasoning and its sources.`}
          teaser={
            <div>
              <HorizonBoard
                view={{ ...view, scopes: view.scopes.slice(0, 3) }}
                evidence={evidenceMap}
              />
              <p className="mt-3 font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
                Free preview — {Math.min(3, view.scopes.length)} of{" "}
                {view.scopes.length} technology fields
              </p>
            </div>
          }
        >
          <HorizonBoard view={view} evidence={evidenceMap} />
        </TierGate>

        <p className="mt-8 font-sans text-sm text-muted leading-relaxed max-w-3xl">
          Placement is computed per dimension, not by one score: technology from
          the patent record where the lead-time is reliable, regulation from
          approval milestones attributed to the <em>named authority</em> (not the
          company&apos;s home country), market from product launches in that
          jurisdiction.{" "}
          {view.config.regulated
            ? "In this regulated domain a market cannot be rated ahead of its approval — without a licence there is no lawful market."
            : null}{" "}
          Where the evidence is too thin, the cell stays empty.{" "}
          <Link href="/trends/foresight/radar?view=evidence" className="text-accent hover:underline">
            The corpus-wide signal-source view is here →
          </Link>
        </p>

        <div className="mt-12">
          <ForesightCta />
        </div>
      </div>
    );
  }

  // ---- Legacy evidence/lead-time view -------------------------------------
  const requestedVertical =
    typeof raw.vertical === "string" ? raw.vertical.toUpperCase() : null;
  const data = await getRadarData(requestedVertical);
  const FREE_PREVIEW = 8;
  const previewBlips = data.blips
    .slice()
    .sort((a, b) => b.sov_delta_pp - a.sov_delta_pp)
    .slice(0, FREE_PREVIEW);

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <div className="mb-8">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-4">
          —— Foresight · Signal sources
        </div>
        <h1 className="font-display text-4xl md:text-[52px] leading-[1.05] tracking-tight text-paper mb-4">
          Where the <span className="italic">signals</span> come from
        </h1>
        <p className="font-sans text-text text-lg leading-relaxed max-w-2xl">
          A corpus overview: each dot is an automatically discovered cluster,
          placed by the kind of source its signals came from — research on the
          rim, trade press at the centre. This is a map of our evidence base, not
          a maturity judgement.
          {data.generated ? (
            <span className="text-muted"> Updated {asOf(data.generated)}.</span>
          ) : null}
        </p>
        {radars.length > 0 && (
          <p className="mt-3 font-mono text-[10px] uppercase tracking-[0.14em]">
            <Link href="/trends/foresight/radar" className="text-accent hover:underline">
              ← Back to the horizon radar
            </Link>
          </p>
        )}
      </div>

      <div className="mb-8 flex flex-wrap gap-1">
        <Link href="/trends/foresight/radar?view=evidence" className={chip(!requestedVertical)}>
          All industries
        </Link>
        {VERTICALS.map((v) => (
          <Link
            key={v.id}
            href={`/trends/foresight/radar?view=evidence&vertical=${v.id}`}
            className={chip(requestedVertical === v.id)}
            style={
              requestedVertical === v.id
                ? { color: v.color, borderColor: v.color }
                : undefined
            }
          >
            {v.label}
          </Link>
        ))}
      </div>

      {data.blips.length > 0 ? (
        <TierGate
          need="starter"
          feature="The full signal-source view"
          benefit={`Starter places all ${data.blips.length} clusters of this view — every industry, every source stage, with the evidence one click away.`}
          teaser={
            <div>
              <TrendRadar blips={previewBlips} vertical={requestedVertical} />
              <p className="mt-3 font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
                Free preview — the {Math.min(FREE_PREVIEW, data.blips.length)} fastest-rising of{" "}
                {data.blips.length} clusters
              </p>
            </div>
          }
        >
          <TrendRadar blips={data.blips} vertical={requestedVertical} />
        </TierGate>
      ) : (
        <div className="border border-border bg-card/40 p-8 text-center">
          <p className="font-display text-[22px] text-paper">Radar is warming up</p>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted leading-relaxed">
            The snapshots behind this view are still being built. In the meantime,
            explore the same trends grouped by momentum in the cluster view.
          </p>
          <Link
            href="/trends/foresight/clusters"
            className="mt-4 inline-block font-mono text-[11px] uppercase tracking-[0.14em] text-accent hover:underline"
          >
            Open the cluster explorer →
          </Link>
        </div>
      )}

      <div className="mt-12">
        <ForesightCta />
      </div>
    </div>
  );
}
