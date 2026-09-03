import Link from "next/link";
import { getLatestClusterRun } from "@/lib/foresight";
import { VERTICALS } from "@/lib/types";
import ExportButton from "@/components/foresight/ExportButton";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Foresight Dossier — Catandary Trends",
  description: "A printable one-page trend dossier: what's rising, holding and cooling in a scope.",
};

function momentumWord(m: string, pp: number): string {
  if (m === "rising") return `rising (+${pp.toFixed(1)} pts share)`;
  if (m === "declining") return `cooling (${pp.toFixed(1)} pts share)`;
  if (m === "stable") return "holding steady";
  return "—";
}

/**
 * Printable foresight dossier (Epic W3.7) — the artefact an analyst hands on.
 * Clean, dense, print-CSS optimised (no chrome when printed). Single
 * vertical selector. Reads the persisted snapshot.
 */
export default async function DossierPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  const requested = typeof sp.vertical === "string" ? sp.vertical.toUpperCase() : null;
  const scope = requested ? `vertical:${requested}` : "global";
  const data =
    (await getLatestClusterRun(scope)) ??
    (scope !== "global" ? await getLatestClusterRun("global") : null);

  const asOf = data?.run.created_at
    ? new Date(data.run.created_at + "Z").toLocaleDateString("en-US", {
        month: "long",
        day: "numeric",
        year: "numeric",
      })
    : null;

  const clusters = (data?.clusters ?? [])
    .slice()
    .sort((a, b) => b.sov_delta_pp - a.sov_delta_pp);
  const rising = clusters.filter((c) => c.momentum === "rising");
  const cooling = clusters.filter((c) => c.momentum === "declining");

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <div className="mb-6 flex items-start justify-between gap-4 print:hidden">
        <div className="flex flex-wrap gap-1">
          <Link
            href="/trends/foresight/dossier"
            className={`font-mono text-[10px] uppercase tracking-[0.14em] px-3 py-1.5 border transition-colors ${
              requested
                ? "text-muted border-border hover:text-paper"
                : "text-accent border-accent bg-accent/10"
            }`}
          >
            All
          </Link>
          {VERTICALS.map((v) => (
            <Link
              key={v.id}
              href={`/trends/foresight/dossier?vertical=${v.id}`}
              className={`font-mono text-[10px] uppercase tracking-[0.14em] px-3 py-1.5 border transition-colors ${
                requested === v.id
                  ? "text-accent border-accent bg-accent/10"
                  : "text-muted border-border hover:text-paper"
              }`}
            >
              {v.label}
            </Link>
          ))}
        </div>
      </div>

        <div className="mb-5 flex justify-end print:hidden">
          <ExportButton scope={scope} />
        </div>
        <article className="dossier">
          <header className="mb-5 border-b border-border pb-4">
            <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-accent">
              Catandary Foresight Dossier
            </div>
            <h1 className="mt-1.5 font-display text-[28px] text-paper">
              {requested ? VERTICALS.find((v) => v.id === requested)?.label : "All industries"}
            </h1>
            <p className="mt-1 text-sm text-muted">
              {data ? `${data.clusters.length} trend clusters` : "no data"}
              {asOf ? ` · as of ${asOf}` : ""}
            </p>
          </header>

          <section className="mb-6">
            <h2 className="mb-2 text-sm font-bold uppercase tracking-wide">Rising</h2>
            {rising.length ? (
              <ol className="space-y-2">
                {rising.slice(0, 10).map((c) => (
                  <li key={c.id} className="text-sm">
                    <span className="font-semibold">{c.label}</span> —{" "}
                    {momentumWord(c.momentum, c.sov_delta_pp)}, {c.size.toLocaleString("en-US")}{" "}
                    signals from {c.n_sources} sources
                    {c.top_tags.length ? (
                      <span className="opacity-60"> · {c.top_tags.slice(0, 4).join(", ")}</span>
                    ) : null}
                  </li>
                ))}
              </ol>
            ) : (
              <p className="text-sm opacity-60">No clearly rising clusters in this scope.</p>
            )}
          </section>

          {cooling.length > 0 && (
            <section className="mb-6">
              <h2 className="mb-2 text-sm font-bold uppercase tracking-wide">Cooling</h2>
              <ol className="space-y-2">
                {cooling.slice(0, 6).map((c) => (
                  <li key={c.id} className="text-sm">
                    <span className="font-semibold">{c.label}</span> —{" "}
                    {momentumWord(c.momentum, c.sov_delta_pp)}
                  </li>
                ))}
              </ol>
            </section>
          )}

          <footer className="mt-8 border-t border-current/15 pt-3 text-xs opacity-55">
            Generated by Catandary Trends · evidence-based foresight with primary
            sources · catandary.de
          </footer>
        </article>

      <style>{`
        @media print {
          .dossier { font-size: 11pt; }
          a[href]:after { content: ""; }
        }
      `}</style>
    </div>
  );
}
