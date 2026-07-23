import Link from "next/link";
import { getRadarData } from "@/lib/foresight";
import { VERTICALS } from "@/lib/types";
import TrendRadar from "@/components/foresight/TrendRadar";
import ForesightCta from "@/components/ForesightCta";
import TierGate from "@/components/TierGate";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Trend Radar — Catandary Trends",
  description:
    "The market-standard foresight radar: trend clusters placed by innovation stage (research → market) and industry, with momentum and evidence.",
};

/** Blips shown free before the Starter gate (value teaser, ONB-03/KEY-01). */
const FREE_PREVIEW = 8;

/**
 * Low-threshold UX: loads with a finished default radar (all verticals). The
 * vertical row is the single visible control. Plain-language readout, evidence
 * one click away. Empty state links to the cluster explorer so the page is
 * never a dead end before the tier snapshots exist.
 */
export default async function RadarPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const raw = await searchParams;
  const requested =
    typeof raw.vertical === "string" ? raw.vertical.toUpperCase() : null;
  const data = await getRadarData(requested);

  const asOf = data.generated
    ? new Date(data.generated + "Z").toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
      })
    : null;

  const previewBlips = data.blips
    .slice()
    .sort((a, b) => b.sov_delta_pp - a.sov_delta_pp)
    .slice(0, FREE_PREVIEW);

  const chip = (active: boolean) =>
    `font-mono text-[10px] uppercase tracking-[0.14em] px-3 py-1.5 border transition-colors ${
      active
        ? "text-accent border-accent bg-accent/10"
        : "text-muted border-border hover:text-paper"
    }`;

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <div className="mb-8">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-4">
          —— Foresight · Radar
        </div>
        <h1 className="font-display text-4xl md:text-[52px] leading-[1.05] tracking-tight text-paper mb-4">
          The trend <span className="italic">radar</span>
        </h1>
        <p className="font-sans text-text text-lg leading-relaxed max-w-2xl">
          Every dot is a trend cluster from our full signal space. The further
          out, the earlier the stage it lives in — research on the rim, the
          market at the centre. Watch what is climbing toward the middle.
          {asOf ? (
            <span className="text-muted"> Updated {asOf}.</span>
          ) : null}
        </p>
      </div>

      {/* Single allowed control: the vertical selector */}
      <div className="mb-8 flex flex-wrap gap-1">
        <Link href="/trends/foresight/radar" className={chip(!requested)}>
          All industries
        </Link>
        {VERTICALS.map((v) => (
          <Link
            key={v.id}
            href={`/trends/foresight/radar?vertical=${v.id}`}
            className={chip(requested === v.id)}
            style={requested === v.id ? { color: v.color, borderColor: v.color } : undefined}
          >
            {v.label}
          </Link>
        ))}
      </div>

      {data.blips.length > 0 ? (
        <TierGate
          need="starter"
          feature="The full radar"
          benefit={`Starter places all ${data.blips.length} clusters of this view on the radar — every industry, every innovation stage, with the evidence one click away.`}
          teaser={
            <div>
              <TrendRadar blips={previewBlips} vertical={requested} />
              <p className="mt-3 font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
                Free preview — the {Math.min(FREE_PREVIEW, data.blips.length)} fastest-rising of{" "}
                {data.blips.length} clusters
              </p>
            </div>
          }
        >
          <TrendRadar blips={data.blips} vertical={requested} />
        </TierGate>
      ) : (
        <div className="border border-border bg-card/40 p-8 text-center">
          <p className="font-display text-[22px] text-paper">Radar is warming up</p>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted leading-relaxed">
            The tier-scoped snapshots that place clusters on the innovation-stage
            rings are still being built. In the meantime, explore the same trends
            grouped by momentum in the cluster view.
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
