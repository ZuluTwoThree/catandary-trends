"use client";

import { useState, useEffect, useCallback } from "react";
import SignupForm from "./SignupForm";
import EditionBody from "./EditionBody";
import type { NewsletterEdition, EditionSummary } from "@/lib/newsletterEditions";

/**
 * The workstation's newsletter page (unchanged behaviour): loads the latest
 * edition and the archive list from /api/newsletter, switches editions
 * client-side (?year=&week=). The static export never renders this — see
 * app/trends/newsletter/page.tsx for the build-time archive.
 */

/** Week selector for navigating between editions */
function WeekSelector({
  archive,
  currentYear,
  currentWeek,
  onSelect,
}: {
  archive: EditionSummary[];
  currentYear: number;
  currentWeek: number;
  onSelect: (year: number, week: number) => void;
}) {
  const currentIdx = archive.findIndex((a) => a.year === currentYear && a.week === currentWeek);
  const prevEdition = currentIdx < archive.length - 1 ? archive[currentIdx + 1] : null;
  const nextEdition = currentIdx > 0 ? archive[currentIdx - 1] : null;

  return (
    <div className="flex items-center justify-between gap-4 mb-10 pb-4 border-b border-border">
      {/* Prev */}
      <button
        onClick={() => prevEdition && onSelect(prevEdition.year, prevEdition.week)}
        disabled={!prevEdition}
        aria-label={
          prevEdition
            ? `Previous briefing: week ${prevEdition.week}/${prevEdition.year}`
            : "No earlier briefing"
        }
        className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted hover:text-accent disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
      >
        ← W{prevEdition ? `${prevEdition.week}` : "—"}
      </button>

      {/* Current + dropdown */}
      <div className="flex items-center gap-4 font-mono text-[10px] uppercase tracking-[0.14em]">
        <select
          value={`${currentYear}-${currentWeek}`}
          onChange={(e) => {
            const [y, w] = e.target.value.split("-").map(Number);
            onSelect(y, w);
          }}
          aria-label="Select briefing week"
          className="bg-transparent text-accent border-none font-mono text-[10px] uppercase tracking-[0.14em] cursor-pointer"
        >
          {archive.map((a) => (
            <option key={`${a.year}-${a.week}`} value={`${a.year}-${a.week}`} className="bg-card text-paper">
              Week {a.week}/{a.year} — {a.total_signals} signals
            </option>
          ))}
        </select>
      </div>

      {/* Next */}
      <button
        onClick={() => nextEdition && onSelect(nextEdition.year, nextEdition.week)}
        disabled={!nextEdition}
        aria-label={
          nextEdition ? `Next briefing: week ${nextEdition.week}/${nextEdition.year}` : "No later briefing"
        }
        className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted hover:text-accent disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
      >
        W{nextEdition ? `${nextEdition.week}` : "—"} →
      </button>
    </div>
  );
}

export default function NewsletterClient() {
  const [edition, setEdition] = useState<NewsletterEdition | null>(null);
  const [archive, setArchive] = useState<EditionSummary[]>([]);
  const [loading, setLoading] = useState(true);

  const loadEdition = useCallback(async (year?: number, week?: number) => {
    setLoading(true);
    try {
      const params = year && week ? `?year=${year}&week=${week}` : "";
      const res = await fetch(`/api/newsletter${params}`);
      const data = await res.json();
      setEdition(data.edition || null);
    } catch {
      setEdition(null);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    // Load archive list and latest edition in parallel
    Promise.all([
      fetch("/api/newsletter?list=true").then((r) => r.json()),
      fetch("/api/newsletter").then((r) => r.json()),
    ])
      .then(([archiveData, editionData]) => {
        setArchive(archiveData.archive || []);
        setEdition(editionData.edition || null);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  function handleWeekSelect(year: number, week: number) {
    loadEdition(year, week);
    // Update URL without navigation for bookmarkability
    window.history.replaceState(null, "", `?year=${year}&week=${week}`);
  }

  return (
    <div className="mx-auto max-w-3xl px-6 md:px-12 py-16">
      {/* Header */}
      <div className="mb-12">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-4">
          —— Weekly Briefing
        </div>
        <h1 className="font-display text-4xl md:text-[48px] leading-[1.05] tracking-tight text-paper mb-3">
          Trend <span className="italic">Briefing</span>
        </h1>
        <p className="font-sans text-text text-lg leading-relaxed">
          The week&apos;s most important signals — analyzed and contextualized.
        </p>
      </div>

      {/* Signup — above the fold: the email capture sits at the top, not
          buried under the full briefing. */}
      <section className="mb-14">
        <SignupForm />
      </section>

      {loading ? (
        <div className="border border-border bg-card/40 p-12 text-center" role="status">
          <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted animate-pulse">
            This week&apos;s briefing is loading…
          </div>
        </div>
      ) : !edition ? (
        <div className="border border-border bg-card/40 p-12 text-center mb-10">
          <p className="font-sans text-text">
            No briefing available yet. The first briefing will be published Monday.
          </p>
        </div>
      ) : (
        <>
          {/* Week selector */}
          {archive.length > 1 ? (
            <WeekSelector
              archive={archive}
              currentYear={edition.year}
              currentWeek={edition.week}
              onSelect={handleWeekSelect}
            />
          ) : (
            <div className="flex items-center gap-4 font-mono text-[10px] uppercase tracking-[0.14em] text-muted mb-10 pb-4 border-b border-border">
              <span className="text-accent">
                Week {edition.week}/{edition.year}
              </span>
              <span className="text-border">——</span>
              <span>
                <span className="text-paper">{edition.total_signals}</span>
                <span> signals</span>
              </span>
            </div>
          )}

          <EditionBody edition={edition} />

          {/* Archive */}
          {archive.length > 1 && (
            <section className="mb-12">
              <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted mb-4">
                —— Archive
              </div>
              <div className="border border-border bg-card/40">
                {archive.map((a, i) => {
                  const isActive = a.year === edition.year && a.week === edition.week;
                  return (
                    <button
                      key={`${a.year}-${a.week}`}
                      onClick={() => handleWeekSelect(a.year, a.week)}
                      className={`w-full flex items-center justify-between px-5 py-3 font-mono text-[10px] uppercase tracking-[0.14em] transition-colors ${
                        i < archive.length - 1 ? "border-b border-dashed border-border" : ""
                      } ${
                        isActive ? "text-accent bg-accent/5" : "text-muted hover:text-paper hover:bg-card"
                      }`}
                    >
                      <span>
                        {isActive && "→ "}Week {a.week}/{a.year}
                      </span>
                      <span>{a.total_signals} signals</span>
                    </button>
                  );
                })}
              </div>
            </section>
          )}
        </>
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
