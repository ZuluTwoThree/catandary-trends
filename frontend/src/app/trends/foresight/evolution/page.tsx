import Link from "next/link";
import {
  getLatestLineage,
  getLineageScopes,
  threadLineage,
  type LineageThread,
} from "@/lib/foresight";
import { VERTICALS } from "@/lib/types";
import ThreadSparkline from "@/components/foresight/ThreadSparkline";
import SnapshotRecompute from "../SnapshotRecompute";
import ForesightCta from "@/components/ForesightCta";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Trend Evolution — Catandary Trends",
  description:
    "How trends emerge, grow, split and fade over time — cross-window cluster lineage from the full signal space.",
};

function fmtWindow(iso: string): string {
  const d = new Date(iso + "T00:00:00Z");
  return d.toLocaleDateString("en-US", { month: "short", year: "numeric" });
}

function ThreadRow({ t, color }: { t: LineageThread; color: string }) {
  const first = t.points[0];
  const last = t.points[t.points.length - 1];
  const trend =
    last.share > first.share * 1.15
      ? "rising"
      : last.share < first.share * 0.85
        ? "cooling"
        : "steady";
  const vertical = t.label; // label already human-readable
  return (
    <div className="evo-row">
      <div className="evo-row-main">
        <div className="evo-row-head">
          <span className="evo-label">{t.label}</span>
          {t.kind === "emerging" && <span className="evo-badge evo-new">New</span>}
          {t.kind === "fading" && <span className="evo-badge evo-fade">Fading</span>}
        </div>
        <p className="evo-line">
          {t.kind === "emerging"
            ? `Emerged ${fmtWindow(first.window_start)}, now ${(last.share * 100).toFixed(1)}% of the field`
            : `Tracked from ${fmtWindow(first.window_start)} to ${fmtWindow(last.window_start)} · ${trend} (${(last.share * 100).toFixed(1)}% share)`}
          {t.drift > 0.4 ? " · shifting in meaning" : ""}
        </p>
      </div>
      <ThreadSparkline points={t.points} color={color} />
    </div>
  );
}

/**
 * Low-threshold UX: readable "what's emerging / fading" framing over the raw
 * lineage graph. Each theme is one thread (followed through the strongest
 * continue/split edge), shown with a share-of-voice sparkline. The single
 * control is the vertical selector; evidence is one click away in the cluster
 * explorer. Empty state links to clusters so the page is never a dead end.
 */
export default async function EvolutionPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const raw = await searchParams;
  const requested =
    typeof raw.vertical === "string" ? raw.vertical.toUpperCase() : null;
  const scope = requested ? `vertical:${requested}` : "global";
  const notice = typeof raw.worker === "string" ? raw.worker : undefined;

  const scopes = new Set(await getLineageScopes());
  let data =
    (await getLatestLineage(scope)) ??
    (scope !== "global" ? await getLatestLineage("global") : null);

  let threads = data ? threadLineage(data) : [];

  // If the default (global) scope has no lineage yet but a vertical scope
  // does, show the richest available one instead of an empty page — with a
  // notice explaining what the visitor is looking at.
  let fallbackVertical: (typeof VERTICALS)[number] | null = null;
  if (!requested && threads.length === 0) {
    for (const v of VERTICALS) {
      if (!scopes.has(`vertical:${v.id}`)) continue;
      const candidate = await getLatestLineage(`vertical:${v.id}`);
      if (!candidate) continue;
      const candidateThreads = threadLineage(candidate);
      if (candidateThreads.length > threads.length) {
        data = candidate;
        threads = candidateThreads;
        fallbackVertical = v;
      }
    }
  }

  const activeVerticalId = requested ?? fallbackVertical?.id ?? null;
  const color = activeVerticalId
    ? VERTICALS.find((v) => v.id === activeVerticalId)?.color ?? "#94a3b8"
    : "#94a3b8";
  const emerging = threads
    .filter((t) => t.kind === "emerging")
    .sort((a, b) => b.latest_share - a.latest_share);
  const fading = threads
    .filter((t) => t.kind === "fading")
    .sort((a, b) => b.peak_share - a.peak_share);
  const ongoing = threads
    .filter((t) => t.kind === "ongoing" && t.points.length >= 3)
    .sort((a, b) => b.latest_share - a.latest_share)
    .slice(0, 12);

  const span =
    data?.first_window && data?.last_window
      ? `${fmtWindow(data.first_window)} – ${fmtWindow(data.last_window)}`
      : null;

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <div className="mb-6">
        <h1 className="text-3xl font-bold tracking-tight">Trend Evolution</h1>
        <p className="mt-2 max-w-2xl text-sm opacity-70">
          We cluster the signal space in rolling time windows and track each
          theme as it emerges, grows, splits and fades. This is how we spot a
          trend before it is obvious.{span ? ` Covering ${span}.` : ""}
        </p>
      </div>

      <SnapshotRecompute
        mode="lineage"
        asOf={span ? `windows ${span}` : null}
        back={requested ? `/trends/foresight/evolution?vertical=${requested}` : "/trends/foresight/evolution"}
        notice={notice}
      />

      <div className="mb-8 flex flex-wrap gap-2">
        <Link
          href="/trends/foresight/evolution"
          className={`rounded-full px-3 py-1 text-sm ${activeVerticalId ? "opacity-60 hover:opacity-100" : "font-semibold underline"}`}
        >
          All industries
        </Link>
        {VERTICALS.filter((v) => scopes.has(`vertical:${v.id}`)).map((v) => (
          <Link
            key={v.id}
            href={`/trends/foresight/evolution?vertical=${v.id}`}
            className={`rounded-full px-3 py-1 text-sm ${activeVerticalId === v.id ? "font-semibold underline" : "opacity-60 hover:opacity-100"}`}
            style={activeVerticalId === v.id ? { color: v.color } : undefined}
          >
            {v.label}
          </Link>
        ))}
      </div>

      {fallbackVertical && (
        <p className="mb-6 border-l-2 pl-3 text-sm opacity-80" style={{ borderColor: color }}>
          Currently available for {fallbackVertical.label} — more industries
          follow as snapshots build.
        </p>
      )}

      {threads.length === 0 ? (
        <div className="rounded-xl border border-current/10 p-8 text-center">
          <p className="text-lg font-semibold">No evolution snapshots yet</p>
          <p className="mx-auto mt-2 max-w-md text-sm opacity-70">
            Trend evolution is built from snapshots of the signal space that are
            computed periodically — the first ones for this view are still on
            the way. Until then, explore what&apos;s moving right now in the
            trend clusters.
          </p>
          <Link
            href="/trends/foresight/clusters"
            className="mt-4 inline-block text-sm font-semibold underline"
          >
            Open the cluster explorer →
          </Link>
        </div>
      ) : (
        <div className="space-y-10">
          {emerging.length > 0 && (
            <section>
              <h2 className="mb-3 text-lg font-semibold">Emerging now</h2>
              <div className="evo-list">
                {emerging.map((t) => (
                  <ThreadRow key={t.key} t={t} color={color} />
                ))}
              </div>
            </section>
          )}
            {ongoing.length > 0 && (
              <section>
                <h2 className="mb-3 text-lg font-semibold">Established & moving</h2>
                <div className="evo-list">
                  {ongoing.map((t) => (
                    <ThreadRow key={t.key} t={t} color={color} />
                  ))}
                </div>
              </section>
            )}
            {fading.length > 0 && (
              <section className="mt-10">
                <h2 className="mb-3 text-lg font-semibold">Fading</h2>
                <div className="evo-list">
                  {fading.map((t) => (
                    <ThreadRow key={t.key} t={t} color={color} />
                  ))}
                </div>
              </section>
            )}
        </div>
      )}

      <div className="mt-12">
        <ForesightCta />
      </div>

      <style>{`
        .evo-list { display: flex; flex-direction: column; }
        .evo-row { display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: 0.85rem 0; border-bottom: 1px solid color-mix(in srgb, currentColor 10%, transparent); }
        .evo-row-main { min-width: 0; }
        .evo-row-head { display: flex; align-items: center; gap: 0.5rem; }
        .evo-label { font-weight: 600; font-size: 0.98rem; }
        .evo-badge { font-size: 0.66rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; padding: 0.08rem 0.4rem; border-radius: 999px; }
        .evo-new { background: #16a34a22; color: #16a34a; }
        .evo-fade { background: #94a3b822; color: #94a3b8; }
        .evo-line { font-size: 0.85rem; opacity: 0.75; margin-top: 0.15rem; }
      `}</style>
    </div>
  );
}
