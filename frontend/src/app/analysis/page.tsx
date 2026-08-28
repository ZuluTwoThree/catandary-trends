import Link from "next/link";
import { getAllAnalyses, formatAnalysisDate } from "@/lib/analyses";

export const metadata = {
  title: "Analyses — Catandary Trends",
  description:
    "Hand-built analyses from the Catandary corpus — dated, sourced and reviewed by a human.",
};

/**
 * `/analysis` — chronological overview, newest first (#93: "damit ein
 * Interessent Kontinuität sieht"). File-backed content (`lib/analyses.ts`),
 * so this renders at build/request time with no DB call.
 */
export default function AnalysisIndexPage() {
  const analyses = getAllAnalyses();

  return (
    <div className="mx-auto max-w-4xl px-6 md:px-10 py-14">
      <div className="mb-14">
        <span className="eyebrow">Analyses</span>
        <h1 className="font-display text-4xl md:text-[56px] leading-[1.03] tracking-tight text-paper mt-4 mb-5">
          Evidence, <span className="italic">read closely</span>.
        </h1>
        <p className="font-sans text-text text-lg leading-relaxed max-w-2xl">
          Occasional deep dives built from the corpus and reviewed by a human
          — not a feed, a series. Each one is dated, sourced and signed.
        </p>
      </div>

      {analyses.length === 0 ? (
        <div className="border border-border border-dashed px-8 py-16 text-center">
          <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted mb-4">
            —— 0 published
          </div>
          <h2 className="font-display text-[28px] leading-[1.15] text-paper mb-4">
            Analyses will be published here —{" "}
            <span className="italic text-accent">first one landing soon</span>.
          </h2>
          <p className="font-sans text-[14px] text-muted max-w-md mx-auto leading-[1.55]">
            Each analysis is hand-built from the corpus, reviewed by a human,
            and dated with the exact data it was drawn from. Want one on a
            specific question?{" "}
            <Link href="/enquiry" className="text-accent hover:underline">
              Ask us
            </Link>
            .
          </p>
        </div>
      ) : (
        <ol className="divide-y divide-border border-t border-b border-border">
          {analyses.map((a) => (
            <li key={a.slug}>
              <Link
                href={`/analysis/${a.slug}`}
                className="group flex flex-col md:flex-row md:items-baseline gap-2 md:gap-8 py-6 px-2 -mx-2 hover:bg-card/40 transition-colors"
              >
                <time
                  dateTime={a.date}
                  className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted shrink-0 md:w-32"
                >
                  {formatAnalysisDate(a.date)}
                </time>
                <div className="min-w-0">
                  <h2 className="font-display text-[20px] leading-snug text-paper group-hover:text-accent transition-colors">
                    {a.title}
                  </h2>
                  <p className="font-sans text-sm text-muted mt-1 leading-relaxed">
                    {a.teaser}
                  </p>
                </div>
              </Link>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
