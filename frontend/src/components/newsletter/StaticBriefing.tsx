import Link from "next/link";
import SignupForm from "./SignupForm";
import EditionBody from "./EditionBody";
import EditionArchiveList from "./EditionArchiveList";
import { linkPrefetch } from "@/lib/renderMode";
import {
  editionNeighbours,
  editionPath,
  isoWeekMondayIso,
  isoWeekRangeLabel,
  type EditionSummary,
  type NewsletterEdition,
} from "@/lib/newsletterEditions";

/**
 * The static export's briefing page — used for /trends/newsletter (latest
 * edition + archive) and for every /trends/newsletter/<year>-w<week>.
 * Server-rendered at build time from lib/newsletterExport.ts; the only
 * client component on it is the signup form. No clock, no fetch.
 */
export default function StaticBriefing({
  edition,
  editions,
  variant,
}: {
  edition: NewsletterEdition | null;
  editions: EditionSummary[];
  /** "index" = /trends/newsletter (latest), "edition" = a permalink page. */
  variant: "index" | "edition";
}) {
  const nav = edition ? editionNeighbours(editions, edition.year, edition.week) : null;
  const NAV = "font-mono text-[10px] uppercase tracking-[0.14em] transition-colors";

  return (
    <div className="mx-auto max-w-3xl px-6 md:px-12 py-16">
      {/* Header */}
      <div className="mb-12">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-4">
          —— Weekly Briefing
          {variant === "edition" && edition ? ` · Week ${edition.week}/${edition.year}` : ""}
        </div>
        <h1 className="font-display text-4xl md:text-[48px] leading-[1.05] tracking-tight text-paper mb-3">
          Trend <span className="italic">Briefing</span>
        </h1>
        <p className="font-sans text-text text-lg leading-relaxed">
          {variant === "edition" && edition ? (
            <>
              The week of{" "}
              <time dateTime={isoWeekMondayIso(edition.year, edition.week)}>
                {isoWeekRangeLabel(edition.year, edition.week)}
              </time>{" "}
              — {edition.total_signals} signals, analyzed and contextualized.
            </>
          ) : (
            <>The week&apos;s most important signals — analyzed and contextualized.</>
          )}
        </p>
      </div>

      {/* Signup — above the fold */}
      <section className="mb-14">
        <SignupForm />
      </section>

      {!edition ? (
        <div className="border border-border bg-card/40 p-12 text-center mb-10">
          <p className="font-sans text-text">
            No briefing published yet. Subscribe above to get the first edition by email.
          </p>
        </div>
      ) : (
        <>
          {/* Edition strip: prev / current / next (static links) */}
          <nav
            aria-label="Briefing editions"
            className="flex items-center justify-between gap-4 mb-10 pb-4 border-b border-border"
          >
            {nav?.previous ? (
              <Link
                prefetch={linkPrefetch()}
                href={editionPath(nav.previous.year, nav.previous.week)}
                rel="prev"
                aria-label={`Previous briefing: week ${nav.previous.week}/${nav.previous.year}`}
                className={`${NAV} text-muted hover:text-accent`}
              >
                ← W{nav.previous.week}
              </Link>
            ) : (
              <span className={`${NAV} text-muted opacity-30`} aria-hidden="true">
                ← W—
              </span>
            )}

            <span className={`${NAV} inline-flex items-center gap-4`}>
              {variant === "index" ? (
                <Link
                  prefetch={linkPrefetch()}
                  href={editionPath(edition.year, edition.week)}
                  className="text-accent hover:underline"
                  title="Permalink of this edition"
                >
                  Week {edition.week}/{edition.year}
                </Link>
              ) : (
                <span className="text-accent">
                  Week {edition.week}/{edition.year}
                </span>
              )}
              <span className="text-border">——</span>
              <span className="text-muted">
                <span className="text-paper">{edition.total_signals}</span> signals
              </span>
            </span>

            {nav?.next ? (
              <Link
                prefetch={linkPrefetch()}
                href={editionPath(nav.next.year, nav.next.week)}
                rel="next"
                aria-label={`Next briefing: week ${nav.next.week}/${nav.next.year}`}
                className={`${NAV} text-muted hover:text-accent`}
              >
                W{nav.next.week} →
              </Link>
            ) : (
              <span className={`${NAV} text-muted opacity-30`} aria-hidden="true">
                W— →
              </span>
            )}
          </nav>

          <EditionBody edition={edition} />
        </>
      )}

      {/* Archive */}
      {editions.length > 0 && (
        <section className="mb-12">
          <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted mb-4">
            —— Archive · last {editions.length} briefings
          </div>
          <EditionArchiveList
            editions={editions}
            current={edition ? { year: edition.year, week: edition.week } : null}
          />
        </section>
      )}

      {/* Signup */}
      <section className="mt-12">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted mb-4">
          —— Subscribe
        </div>
        <SignupForm />
      </section>
    </div>
  );
}
