"use client";

import { useState, useEffect, useCallback, useId } from "react";
import Link from "next/link";
import { getVerticalInfo, type Vertical } from "@/lib/types";
import { safeHref } from "@/lib/safeHref";
import { isStaticExport } from "@/lib/renderMode";
import { sitePath } from "@/lib/sitePaths";

/**
 * Static hosting (design 4.2): the signup posts form-encoded to the PHP
 * double-opt-in backend that already serves the landing page
 * (docs/launch/newsletter-doi-php/subscribe.php — fields email, consent,
 * honeypot `website`; JSON {ok, message} back). Consent is a real checkbox
 * there because the backend refuses without it (Art. 7 DSGVO evidence).
 */
const PHP_SUBSCRIBE_ENDPOINT = "/newsletter/subscribe.php";

interface MegaTrendRadar {
  key: string;
  name_en: string;
  icon: string;
  /** Measured; null/absent = too thin for a directional claim. */
  momentum?: string | null;
  signal_count: number;
}

interface TrendRef {
  title: string;
  slug: string;
  source_name: string;
}

interface NewsletterEdition {
  id: number;
  year: number;
  week: number;
  editorial: string;
  vertical_summaries: Record<string, string>;
  mega_trend_radar: MegaTrendRadar[];
  trend_refs: Record<string, TrendRef[]>;
  total_signals: number;
  created_at: string;
}

interface ArchiveEntry {
  id: number;
  year: number;
  week: number;
  total_signals: number;
  created_at: string;
}

const VERTICAL_ORDER = [
  "TECH",
  "BIZ",
  "FOOD",
  "HEALTH",
  "ECO",
  "LIFESTYLE",
  "FASHION",
  "DESIGN",
];

const MOMENTUM_GLYPHS: Record<string, string> = {
  rising: "↑",
  emerging: "↑↑",
  declining: "↓",
  stable: "→",
};

/** Render text that may contain markdown links [text](url) as clickable elements. */
function RichText({ text, className }: { text: string; className?: string }) {
  const parts = text.split(/(\[[^\]]+\]\([^)]+\))/g);
  const linkPattern = /^\[([^\]]+)\]\(([^)]+)\)$/;

  return (
    <span className={className}>
      {parts.map((part, i) => {
        const match = linkPattern.exec(part);
        if (match) {
          // Generated edition text: only http(s)/relative targets become links (F-3).
          const href = safeHref(match[2]);
          if (!href) return <span key={i}>{match[1]}</span>;
          return (
            <Link
              key={i}
              href={href}
              className="text-accent hover:underline transition-colors"
            >
              {match[1]}
            </Link>
          );
        }
        return <span key={i}>{part}</span>;
      })}
    </span>
  );
}

function SignupForm() {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<
    "idle" | "loading" | "success" | "error"
  >("idle");
  const [message, setMessage] = useState("");
  const [consent, setConsent] = useState(false);
  const inputId = useId();
  const consentId = useId();
  const staticSite = isStaticExport();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setStatus("loading");
    try {
      if (staticSite) {
        const body = new URLSearchParams({ email, consent: "1", website: "" });
        const res = await fetch(PHP_SUBSCRIBE_ENDPOINT, {
          method: "POST",
          headers: { Accept: "application/json" },
          body,
        });
        const data = (await res.json()) as { ok?: boolean; message?: string };
        if (res.ok && data.ok) {
          setStatus("success");
          setMessage(data.message || "Check your inbox to confirm.");
          setEmail("");
        } else {
          setStatus("error");
          setMessage(data.message || "Signup failed.");
        }
        return;
      }
      const res = await fetch("/api/newsletter", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const data = await res.json();
      if (res.ok) {
        setStatus("success");
        setMessage(data.message);
        setEmail("");
      } else {
        setStatus("error");
        setMessage(data.error);
      }
    } catch {
      setStatus("error");
      setMessage("Connection error.");
    }
  }

  return (
    <div>
      <div className="border border-border bg-card/40 p-6">
        {status === "success" ? (
          <div className="text-center py-4" role="status">
            <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-2">
              —— Subscribed
            </div>
            <p className="font-sans text-sm text-paper">{message}</p>
          </div>
        ) : (
          <form
            className="flex flex-col gap-3"
            onSubmit={handleSubmit}
          >
            <div className="flex flex-col sm:flex-row gap-2">
              <label htmlFor={inputId} className="sr-only">
                Email address
              </label>
              <input
                id={inputId}
                type="email"
                name="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Your email address"
                className="flex-1 bg-background border border-border px-4 py-3 font-sans text-sm text-paper placeholder:text-muted focus:border-accent transition-colors"
                required
                disabled={status === "loading"}
              />
              <button
                type="submit"
                disabled={status === "loading" || (staticSite && !consent)}
                className="bg-accent text-ink px-6 py-3 font-mono text-[10px] uppercase tracking-[0.18em] hover:bg-accent-deep transition-colors whitespace-nowrap disabled:opacity-50"
              >
                {status === "loading" ? "Subscribing…" : "Subscribe"}
              </button>
            </div>
            {staticSite && (
              <label
                htmlFor={consentId}
                className="flex items-start gap-2 font-sans text-xs text-muted leading-relaxed cursor-pointer"
              >
                <input
                  id={consentId}
                  type="checkbox"
                  name="consent"
                  checked={consent}
                  onChange={(e) => setConsent(e.target.checked)}
                  required
                  className="mt-0.5 accent-[var(--color-accent)]"
                />
                <span>
                  I agree to receive the weekly Catandary briefing by email. A
                  confirmation link follows (double opt-in); unsubscribe anytime.
                </span>
              </label>
            )}
          </form>
        )}
        {status === "error" && (
          <p
            role="alert"
            className="font-mono text-[10px] uppercase tracking-[0.14em] text-warn mt-3"
          >
            {message}
          </p>
        )}
      </div>
      <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted mt-3">
        One email a week. Unsubscribe anytime.{" "}
        <Link
          href={sitePath("/privacy")}
          className="underline hover:text-accent transition-colors"
        >
          Privacy
        </Link>
      </p>
    </div>
  );
}

/** Week selector for navigating between editions */
function WeekSelector({
  archive,
  currentYear,
  currentWeek,
  onSelect,
}: {
  archive: ArchiveEntry[];
  currentYear: number;
  currentWeek: number;
  onSelect: (year: number, week: number) => void;
}) {
  const currentIdx = archive.findIndex(
    (a) => a.year === currentYear && a.week === currentWeek
  );
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
            <option
              key={`${a.year}-${a.week}`}
              value={`${a.year}-${a.week}`}
              className="bg-card text-paper"
            >
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
          nextEdition
            ? `Next briefing: week ${nextEdition.week}/${nextEdition.year}`
            : "No later briefing"
        }
        className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted hover:text-accent disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
      >
        W{nextEdition ? `${nextEdition.week}` : "—"} →
      </button>
    </div>
  );
}

export default function NewsletterPage() {
  const [edition, setEdition] = useState<NewsletterEdition | null>(null);
  const [archive, setArchive] = useState<ArchiveEntry[]>([]);
  // Static hosting: no /api/newsletter to fetch from — the editions get
  // materialised at build time in Schritt 6; until then the page shows the
  // signup and a plain notice instead of firing 404s.
  const staticSite = isStaticExport();
  const [loading, setLoading] = useState(!staticSite);

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
    if (staticSite) return;
    // Load archive list and latest edition in parallel
    Promise.all([
      fetch("/api/newsletter?list=true").then((r) => r.json()),
      fetch("/api/newsletter").then((r) => r.json()),
    ]).then(([archiveData, editionData]) => {
      setArchive(archiveData.archive || []);
      setEdition(editionData.edition || null);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, [staticSite]);

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
        <div
          className="border border-border bg-card/40 p-12 text-center"
          role="status"
        >
          <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted animate-pulse">
            This week&apos;s briefing is loading…
          </div>
        </div>
      ) : !edition ? (
        <div className="border border-border bg-card/40 p-12 text-center mb-10">
          <p className="font-sans text-text">
            {staticSite
              ? "The briefing archive is being prepared for this site. Subscribe above to get each edition by email."
              : "No briefing available yet. The first briefing will be published Monday."}
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

          {/* Editorial */}
          <section className="mb-12">
            <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted mb-4">
              01 — Weekly Overview
            </div>
            <div className="border-l-[3px] border-accent pl-6 py-1">
              {edition.editorial?.split("\n\n").map((para, i) => (
                <p
                  key={i}
                  className="font-sans text-text leading-[1.75] mb-4 last:mb-0"
                >
                  <RichText text={para.trim()} />
                </p>
              ))}
            </div>
          </section>

          {/* Vertical summaries */}
          <section className="mb-12 space-y-3">
            <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted mb-4">
              02 — Vertical Signals
            </div>
            {VERTICAL_ORDER.map((v) => {
              const summary = edition.vertical_summaries?.[v];
              if (!summary) return null;
              const info = getVerticalInfo(v as Vertical);
              const trends = edition.trend_refs?.[v] || [];

              return (
                <div
                  key={v}
                  className="border border-border border-l-[3px] bg-card/40"
                  style={{ borderLeftColor: info.color }}
                >
                  {/* Vertical header */}
                  <div className="px-5 py-3 border-b border-dashed border-border flex items-center justify-between">
                    <span className="inline-flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.14em]">
                      <span
                        className="inline-block w-2 h-[3px]"
                        style={{ backgroundColor: info.color }}
                        aria-hidden="true"
                      />
                      <span style={{ color: info.color }}>{info.code}</span>
                      <span className="text-muted/80 font-sans normal-case tracking-normal">
                        {info.label}
                      </span>
                    </span>
                    {trends.length > 0 && (
                      <span className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted">
                        {trends.length} signals
                      </span>
                    )}
                  </div>

                  {/* Summary */}
                  <div className="px-5 py-4">
                    <p className="font-sans text-text leading-relaxed mb-3">
                      <RichText text={summary} />
                    </p>

                    {/* Top trend links */}
                    {trends.length > 0 && (
                      <div className="space-y-1">
                        {trends.slice(0, 3).map((tr, i) => (
                          <Link
                            key={i}
                            href={`/trends/${tr.slug}`}
                            className="block font-mono text-[10px] uppercase tracking-[0.12em] text-accent hover:underline transition-colors"
                          >
                            → {tr.title}
                          </Link>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </section>

          {/* Mega-Trend Radar */}
          {edition.mega_trend_radar && edition.mega_trend_radar.length > 0 && (
            <section className="mb-12">
              <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted mb-4">
                03 — Signal Themes Radar
              </div>
              <div className="border border-border bg-card/40 p-5">
                <div className="space-y-3">
                  {edition.mega_trend_radar.map((mt) => {
                    const glyph = mt.momentum
                      ? MOMENTUM_GLYPHS[mt.momentum] ?? null
                      : null;
                    return (
                      <div
                        key={mt.key}
                        className="flex items-center justify-between gap-4 pb-2 border-b border-dashed border-border last:border-b-0 last:pb-0"
                      >
                        <span className="font-sans text-sm text-paper">
                          {mt.name_en}
                        </span>
                        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted inline-flex items-center gap-2">
                          <span className="text-paper">{mt.signal_count}</span>
                          <span>Signals</span>
                          {glyph && <span className="text-accent">{glyph}</span>}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </section>
          )}

          {/* Archive */}
          {archive.length > 1 && (
            <section className="mb-12">
              <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted mb-4">
                04 — Archive
              </div>
              <div className="border border-border bg-card/40">
                {archive.map((a, i) => {
                  const isActive =
                    a.year === edition.year && a.week === edition.week;
                  return (
                    <button
                      key={`${a.year}-${a.week}`}
                      onClick={() => handleWeekSelect(a.year, a.week)}
                      className={`w-full flex items-center justify-between px-5 py-3 font-mono text-[10px] uppercase tracking-[0.14em] transition-colors ${
                        i < archive.length - 1
                          ? "border-b border-dashed border-border"
                          : ""
                      } ${
                        isActive
                          ? "text-accent bg-accent/5"
                          : "text-muted hover:text-paper hover:bg-card"
                      }`}
                    >
                      <span>
                        {isActive && "→ "}Week {a.week}/{a.year}
                      </span>
                      <span>
                        {a.total_signals} signals
                      </span>
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
