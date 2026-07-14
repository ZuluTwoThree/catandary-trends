import Link from "next/link";
import { getRadarData } from "@/lib/foresight";
import { VERTICALS } from "@/lib/types";
import TrendRadar from "@/components/foresight/TrendRadar";
import ForesightCta from "@/components/ForesightCta";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Trend Radar — Catandary Trends",
  description:
    "The market-standard foresight radar: trend clusters placed by innovation stage (research → market) and industry, with momentum and evidence.",
};

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

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <div className="mb-6">
        <h1 className="text-3xl font-bold tracking-tight">Trend Radar</h1>
        <p className="mt-2 max-w-2xl text-sm opacity-70">
          Every dot is a trend cluster from our full signal space. The further
          out, the earlier the stage it lives in — research on the rim, the
          market at the centre. Watch what is climbing toward the middle.
          {asOf ? ` As of ${asOf}.` : ""}
        </p>
      </div>

      {/* Single allowed control: the vertical selector */}
      <div className="mb-8 flex flex-wrap gap-2">
        <Link
          href="/trends/foresight/radar"
          className={`rounded-full px-3 py-1 text-sm ${
            requested ? "opacity-60 hover:opacity-100" : "font-semibold underline"
          }`}
        >
          All industries
        </Link>
        {VERTICALS.map((v) => (
          <Link
            key={v.id}
            href={`/trends/foresight/radar?vertical=${v.id}`}
            className={`rounded-full px-3 py-1 text-sm ${
              requested === v.id
                ? "font-semibold underline"
                : "opacity-60 hover:opacity-100"
            }`}
            style={requested === v.id ? { color: v.color } : undefined}
          >
            {v.label}
          </Link>
        ))}
      </div>

      {data.blips.length > 0 ? (
        <TrendRadar blips={data.blips} vertical={requested} />
      ) : (
        <div className="rounded-xl border border-current/10 p-8 text-center">
          <p className="text-lg font-semibold">Radar is warming up</p>
          <p className="mx-auto mt-2 max-w-md text-sm opacity-70">
            The tier-scoped snapshots that place clusters on the innovation-stage
            rings are still being built. In the meantime, explore the same trends
            grouped by momentum in the cluster view.
          </p>
          <Link
            href="/trends/foresight/clusters"
            className="mt-4 inline-block text-sm font-semibold underline"
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
