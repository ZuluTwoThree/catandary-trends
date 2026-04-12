"use client";

import { useState, useEffect } from "react";
import Link from "next/link";

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

const VERTICAL_INFO: Record<string, { label: string; icon: string }> = {
  FOOD: { label: "Food & Beverage", icon: "\u{1F37D}" },
  TECH: { label: "Technology & AI", icon: "\u{1F4BB}" },
  HEALTH: { label: "Health & Wellness", icon: "\u{1F3E5}" },
  ECO: { label: "Sustainability", icon: "\u{1F331}" },
  DESIGN: { label: "Design & Architecture", icon: "\u{1F3A8}" },
  FASHION: { label: "Fashion & Beauty", icon: "\u{1F457}" },
  BIZ: { label: "Business & Retail", icon: "\u{1F4CA}" },
  LIFESTYLE: { label: "Lifestyle & Culture", icon: "\u{1F3AD}" },
};

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

const MOMENTUM_ARROWS: Record<string, string> = {
  rising: "\u2191",
  emerging: "\u2191\u2191",
  declining: "\u2193",
  stable: "\u2192",
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
              className="text-accent hover:text-accent/80 transition-colors"
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
    <div className="rounded-xl border border-border bg-card p-6">
      {status === "success" ? (
        <div className="text-center">
          <div className="text-accent text-2xl mb-2">&#10003;</div>
          <p className="text-foreground font-medium text-sm">{message}</p>
        </div>
      ) : (
        <form
          className="flex flex-col sm:flex-row gap-3"
          onSubmit={handleSubmit}
        >
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="Your email address"
            className="flex-1 rounded-lg bg-background border border-border px-4 py-2.5 text-sm text-foreground placeholder:text-muted focus:outline-none focus:border-accent"
            required
            disabled={status === "loading"}
          />
          <button
            type="submit"
            disabled={status === "loading"}
            className="bg-accent text-background px-6 py-2.5 rounded-lg font-medium hover:bg-accent/90 transition-colors text-sm whitespace-nowrap disabled:opacity-50"
          >
            {status === "loading" ? "Subscribing..." : "Subscribe"}
          </button>
        </form>
      )}
      {status === "error" && (
        <p className="text-red-400 text-sm mt-2">{message}</p>
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
    <div className="mx-auto max-w-3xl px-4 py-12">
      {/* Header */}
      <h1 className="text-3xl font-bold tracking-tight mb-2">
        Weekly Trend Briefing
      </h1>
      <p className="text-muted text-lg mb-8">
        The week&apos;s most important signals — analyzed and contextualized.
      </p>

      {loading ? (
        <div className="rounded-xl border border-border bg-card p-12 text-center">
          <div className="text-muted animate-pulse">Loading...</div>
        </div>
      ) : !edition ? (
        <div className="rounded-xl border border-border bg-card p-12 text-center mb-8">
          <p className="text-muted">
            No briefing available yet. The first briefing will be published
            Monday.
          </p>
        </div>
      ) : (
        <>
          {/* Period badge */}
          <div className="flex items-center gap-3 mb-8">
            <span className="bg-accent/10 text-accent px-3 py-1 rounded-full text-sm font-medium">
              Week {edition.week}/{edition.year}
            </span>
            <span className="text-muted text-sm">
              {edition.total_signals} signals
            </span>
          </div>

          {/* Editorial */}
          <section className="mb-10">
            <h2 className="text-xl font-bold mb-4 text-foreground">
              Weekly Overview
            </h2>
            <div className="rounded-xl border border-border bg-card p-6">
              {edition.editorial?.split("\n\n").map((para, i) => (
                <p
                  key={i}
                  className="text-foreground/90 leading-relaxed mb-4 last:mb-0"
                >
                  <RichText text={para.trim()} />
                </p>
              ))}
            </div>
          </section>

          {/* Vertical summaries */}
          <section className="mb-10 space-y-4">
            {VERTICAL_ORDER.map((v) => {
              const summary = edition.vertical_summaries?.[v];
              if (!summary) return null;
              const info = VERTICAL_INFO[v] || { label: v, icon: "" };
              const trends = edition.trend_refs?.[v] || [];

              return (
                <div
                  key={v}
                  className="rounded-xl border border-border bg-card overflow-hidden"
                >
                  {/* Vertical header */}
                  <div className="px-5 py-3 bg-card-hover border-b border-border flex items-center justify-between">
                    <span className="font-bold text-foreground">
                      {info.icon} {info.label}
                    </span>
                    {trends.length > 0 && (
                      <span className="text-muted text-xs">
                        {trends.length} signals
                      </span>
                    )}
                  </div>

                  {/* Summary */}
                  <div className="px-5 py-4">
                    <p className="text-foreground/90 text-sm leading-relaxed mb-3">
                      <RichText text={summary} />
                    </p>

                    {/* Top trend links */}
                    {trends.length > 0 && (
                      <div className="space-y-1.5">
                        {trends.slice(0, 3).map((tr, i) => (
                          <Link
                            key={i}
                            href={`/trends/${tr.slug}`}
                            className="block text-sm text-accent hover:text-accent/80 transition-colors"
                          >
                            &rarr; {tr.title}
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
            <section className="mb-10">
              <h2 className="text-xl font-bold mb-4 text-foreground">
                Mega-Trend Radar
              </h2>
              <div className="rounded-xl border border-border bg-card p-5">
                <div className="space-y-2.5">
                  {edition.mega_trend_radar.map((mt) => {
                    const arrow =
                      MOMENTUM_ARROWS[mt.momentum] || MOMENTUM_ARROWS.stable;
                    return (
                      <div
                        key={mt.key}
                        className="flex items-center justify-between text-sm"
                      >
                        <span className="text-foreground/90">
                          {mt.icon} {mt.name_en}
                        </span>
                        <span className="text-muted">
                          <strong className="text-foreground">
                            {mt.signal_count}
                          </strong>{" "}
                          signals{" "}
                          <span className="ml-1">{arrow}</span>
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
      <section className="mb-8">
        <h2 className="text-lg font-bold mb-3 text-foreground">
          Subscribe to newsletter
        </h2>
        <SignupForm />
        <p className="text-xs text-muted mt-2">
          No spam. One email per week with the most important trend signals.
        </p>
      </section>
    </div>
  );
}
