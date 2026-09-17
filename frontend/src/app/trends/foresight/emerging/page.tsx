import Link from "next/link";
import { getEmergingScopes, getLatestEmergingRun } from "@/lib/emerging";
import { runProvenance, isYoung, TIER_LABEL } from "@/lib/nestCard";
import { TIERS } from "@/lib/tiers";
import NestCard from "@/components/foresight/NestCard";
import SnapshotRecompute from "../SnapshotRecompute";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Emerging — Catandary Trends",
  description:
    "Small, dense pockets of the recent signal space, each dated against the whole archive: what is actually new, not what is merely loud.",
};

/**
 * The emerging layer (2026-09-15), deliberately next to /clusters rather than
 * instead of it. Clusters answer "what is the room talking about" by cutting
 * everything into ~28 subject areas. This page answers "what is new" by keeping
 * only tight pockets of the last 90 days and asking the entire archive whether
 * each has been seen before.
 *
 * Owner-only by inheritance: everything under /trends/foresight is blocked
 * under PUBLIC_MODE and never built into the static export.
 */
export default async function EmergingPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const raw = await searchParams;
  const requested = typeof raw.vertical === "string" ? raw.vertical.toUpperCase() : null;
  const tier = typeof raw.tier === "string" ? raw.tier.toLowerCase() : null;
  const scope = tier ? `tier:${tier}` : requested ? `vertical:${requested}` : "global";
  const notice = typeof raw.worker === "string" ? raw.worker : undefined;
  const onlyYoung = raw.young === "1";

  const available = new Set(await getEmergingScopes());
  const data = await getLatestEmergingRun(scope);
  const all = data?.nests ?? [];
  const nests = onlyYoung ? all.filter(isYoung) : all;

  const asOf = data?.run.created_at
    ? new Date(data.run.created_at + "Z").toLocaleDateString("en-US", {
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
  const base = tier
    ? `/trends/foresight/emerging?tier=${tier}`
    : requested
      ? `/trends/foresight/emerging?vertical=${requested}`
      : "/trends/foresight/emerging";

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <div className="mb-10">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-4">
          —— Signal Space
        </div>
        <h1 className="font-display text-4xl md:text-[52px] leading-[1.05] tracking-tight text-paper mb-4">
          What is <span className="italic">new</span>
        </h1>
        <p className="font-sans text-text text-lg leading-relaxed max-w-2xl">
          Dense pockets of the recent signal space, each one dated against the
          entire archive. A pocket whose lookalikes reach back years is a subject
          area. One that starts a few months ago is a candidate.
          {asOf && <span className="text-muted"> Computed {asOf}.</span>}
        </p>
        {data && (
          <p className="font-sans text-sm text-muted leading-relaxed max-w-3xl mt-3">
            {runProvenance(data.run)}
          </p>
        )}
        <p className="font-sans text-sm text-muted leading-relaxed max-w-3xl mt-2">
          This is a finder, not a verdict. It ranks by how recent the evidence
          is, which also lifts one-off news and anything a single bulk source
          floods the corpus with. Weaknesses are printed on each card.{" "}
          <Link href="/trends/foresight/clusters" className="text-accent hover:underline">
            The cluster layer
          </Link>{" "}
          answers the other question, what the room talks about most. To check one topic across all
          four conversations,{" "}
          <Link href="/trends/foresight/topic" className="text-accent hover:underline">
            search it
          </Link>
          .
        </p>
      </div>

      <SnapshotRecompute
        mode="emerging"
        asOf={asOf}
        back={base}
        notice={notice}
      />

      {/* Stage 5 of the topic-search plan (2026-09-17): runs are global plus
          the four conversations. Per-vertical runs are no longer computed; a
          vertical question is a topic search now. */}
      <div className="flex items-center gap-1 flex-wrap mb-2">
        {tab("/trends/foresight/emerging", "All industries", scope === "global")}
        {requested && available.has(`vertical:${requested}`) &&
          tab(`/trends/foresight/emerging?vertical=${requested}`, `${requested} (old run)`, true)}
      </div>

      {/* Owner 2026-09-15: a science trend is not a market trend. Each tier is
          clustered on its own, because the embedding carries register as well
          as topic — a market pocket is only found by market vocabulary. */}
      <div className="flex items-center gap-1 flex-wrap mb-8">
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted mr-2">
          by conversation
        </span>
        {TIERS.filter((t) => available.has(`tier:${t}`)).map((t) =>
          tab(`/trends/foresight/emerging?tier=${t}`, TIER_LABEL[t], scope === `tier:${t}`)
        )}
      </div>

      {all.length > 0 && (
        <div className="flex items-center gap-3 mb-8 font-mono text-[10px] uppercase tracking-[0.14em]">
          <Link
            href={onlyYoung ? base : `${base}${base.includes("?") ? "&" : "?"}young=1`}
            className={onlyYoung ? "text-accent" : "text-muted hover:text-paper"}
          >
            {onlyYoung ? "showing only pockets under 18 months" : "show only pockets under 18 months"}
          </Link>
          <span className="text-border">·</span>
          <span className="text-muted normal-case tracking-normal font-sans">
            {nests.length} of {all.length} shown
          </span>
        </div>
      )}

      {nests.length === 0 ? (
        <div className="border border-border bg-card/40 p-10 text-center">
          <p className="font-sans text-text mb-2">No emerging run for this scope yet.</p>
          <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
            Run it with the button above, or on the workstation:
            python -m pipeline.emerging_snapshot --scope global --all-tiers
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {nests.map((n) => (
            <NestCard key={n.id} nest={n} />
          ))}
        </div>
      )}
    </div>
  );
}
