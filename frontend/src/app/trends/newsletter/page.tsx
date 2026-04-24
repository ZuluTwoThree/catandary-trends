"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { getVerticalInfo, type Vertical } from "@/lib/types";

interface MegaTrendRadar {
  key: string;
  name_en: string;
  icon: string;
  momentum: string;
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
          return (
            <Link
              key={i}
              href={match[2]}
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

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setStatus("loading");
    try {
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
    <div className="border border-border bg-card/40 p-6">
      {status === "success" ? (
        <div className="text-center py-4">
          <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-2">
            —— Subscribed
          </div>
          <p className="font-sans text-sm text-paper">{message}</p>
        </div>
      ) : (
        <form
          className="flex flex-col sm:flex-row gap-2"
          onSubmit={handleSubmit}
        >
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="Your email address"
            className="flex-1 bg-background border border-border px-4 py-3 font-sans text-sm text-paper placeholder:text-muted focus:outline-none focus:border-accent transition-colors"
            required
            disabled={status === "loading"}
          />
          <button
            type="submit"
            disabled={status === "loading"}
            className="bg-accent text-ink px-6 py-3 font-mono text-[10px] uppercase tracking-[0.18em] hover:bg-accent-deep transition-colors whitespace-nowrap disabled:opacity-50"
          >
            {status === "loading" ? "Subscribing…" : "Subscribe"}
          </button>
        </form>
      )}
      {status === "error" && (
        <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-warn mt-3">
          {message}
        </p>
      )}
    </div>
  );
}

export default function NewsletterPage() {
  const [edition, setEdition] = useState<NewsletterEdition | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/newsletter")
      .then((res) => res.json())
      .then((data) => {
        setEdition(data.edition || null);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

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

      {loading ? (
        <div className="border border-border bg-card/40 p-12 text-center">
          <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted animate-pulse">
            Loading…
          </div>
        </div>
      ) : !edition ? (
        <div className="border border-border bg-card/40 p-12 text-center mb-10">
          <p className="font-sans text-text">
            No briefing available yet. The first briefing will be published
            Monday.
          </p>
        </div>
      ) : (
        <>
          {/* Period bar */}
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
                03 — Mega-Trend Radar
              </div>
              <div className="border border-border bg-card/40 p-5">
                <div className="space-y-3">
                  {edition.mega_trend_radar.map((mt) => {
                    const glyph =
                      MOMENTUM_GLYPHS[mt.momentum] || MOMENTUM_GLYPHS.stable;
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
                          <span className="text-accent">{glyph}</span>
                        </span>
                      </div>
                    );
                  })}
                </div>
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
        <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted mt-3">
          No spam. One email per week with the most important trend signals.
        </p>
      </section>
    </div>
  );
}
