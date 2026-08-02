"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import HorizonBoard from "./HorizonBoard";
import RadarSearchHelp from "./RadarSearchHelp";
import type { RadarView } from "@/lib/radar-shared";
import {
  Q_MAX,
  Q_MIN,
  radarApiQuery,
  radarQueryString,
  type RadarDimensionSet,
} from "@/lib/radar-params";

/**
 * The query radar: a free-text field that builds a radar on demand.
 *
 * The input and the result both live in the URL, so a built radar is
 * reloadable and shareable — unlike the two existing search tools, whose
 * results vanish on navigation (issue KEY-04).
 *
 * No debounce: each run costs real server work, so it commits on submit only.
 * The response is the same RadarView the saved radars serve, which is why
 * HorizonBoard renders it with no special-casing at all.
 */

interface ApiError {
  error: string;
  message?: string;
  n_signals?: number;
}

export default function QueryRadar({
  initialQuery,
  dim,
  regulated,
}: {
  initialQuery: string;
  dim: RadarDimensionSet;
  regulated: boolean;
}) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [draft, setDraft] = useState(initialQuery);
  const [view, setView] = useState<RadarView | null>(null);
  const [err, setErr] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const run = useCallback(
    async (q: string, d: RadarDimensionSet, reg: boolean) => {
      abortRef.current?.abort();
      const ctl = new AbortController();
      abortRef.current = ctl;
      setLoading(true);
      setErr(null);
      try {
        const res = await fetch(
          `/api/foresight/radar/query?${radarApiQuery({ q, fields: [], dim: d, regulated: reg })}`,
          { signal: ctl.signal }
        );
        const data = await res.json();
        if (!res.ok || data?.error) {
          setView(null);
          setErr(data as ApiError);
        } else {
          setView(data as RadarView);
        }
      } catch (e) {
        if ((e as Error).name !== "AbortError") {
          setView(null);
          setErr({ error: "network" });
        }
      } finally {
        setLoading(false);
      }
    },
    []
  );

  // The URL is the source of truth: whenever q/dim/regulated change, rebuild.
  useEffect(() => {
    if (initialQuery.length >= Q_MIN) void run(initialQuery, dim, regulated);
    else setView(null);
  }, [initialQuery, dim, regulated, run]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const commit = (next: Partial<{ q: string; dim: RadarDimensionSet; regulated: boolean }>) => {
    const q = (next.q ?? draft).trim().replace(/\s+/g, " ");
    router.push(
      "/trends/foresight/radar" +
        radarQueryString({
          q: q.length >= Q_MIN ? q.slice(0, Q_MAX) : null,
          dim: next.dim ?? dim,
          regulated: next.regulated ?? regulated,
          region: (searchParams.get("region") as never) ?? null,
        })
    );
  };

  const tooShort = draft.trim().length < Q_MIN;

  return (
    <div className="qr">
      <form
        className="qr-bar"
        onSubmit={(e) => {
          e.preventDefault();
          if (!tooShort) commit({});
        }}
      >
        <label className="sr-only" htmlFor="qr-input">
          Build a radar for your own topic
        </label>
        <input
          id="qr-input"
          className="qr-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Build a radar for your own topic — e.g. carbon capture"
          maxLength={Q_MAX}
          autoComplete="off"
        />
        <button className="qr-go" type="submit" disabled={tooShort || loading}>
          {loading ? "Building…" : "Build"}
        </button>
      </form>

      <div className="qr-opts">
        <RadarSearchHelp />
        <button
          className={`qr-opt ${dim === "pestel" ? "is-on" : ""}`}
          onClick={() => commit({ dim: dim === "pestel" ? "strategic" : "pestel" })}
          type="button"
          aria-pressed={dim === "pestel"}
        >
          PESTEL lens
        </button>
        <button
          className={`qr-opt ${regulated ? "is-on" : ""}`}
          onClick={() => commit({ regulated: !regulated })}
          type="button"
          aria-pressed={regulated}
          title="In a regulated domain the market cannot be rated ahead of its approval."
        >
          Approval required
        </button>
        {view && (
          <span className="qr-meta">
            {view.n_signals.toLocaleString("en-US")} signals · computed just now ·
            not saved
          </span>
        )}
      </div>

      {loading && (
        <p className="qr-status" role="status">
          Reading the corpus…
        </p>
      )}

      {err && (
        <div className="qr-err" role="alert">
          <p className="qr-err-h">
            {err.error === "too_thin"
              ? "Too little evidence"
              : err.error === "too_broad"
                ? "Too broad"
                : "That didn't work"}
          </p>
          <p className="qr-err-b">
            {err.message ??
              (err.error === "network"
                ? "The request failed — try again."
                : "Try a different phrase.")}
          </p>
        </div>
      )}

      {view && !loading && view.field_check && !view.field_check.is_field && (
        <div className="qr-warn" role="note">
          <p className="qr-warn-h">Not a technology field</p>
          <p className="qr-warn-b">{view.field_check.note}</p>
        </div>
      )}

      {view && !loading && <HorizonBoard view={view} evidence={view.evidence ?? {}} />}

      <style>{`
        .qr { margin-bottom: 2rem; }
        .qr-bar { display: flex; gap: .5rem; align-items: stretch; }
        .qr-input { flex: 1; min-width: 0; background: var(--color-card); border: 1px solid var(--color-border); color: var(--color-paper); padding: .75rem .9rem; font-family: var(--font-sans); font-size: .95rem; }
        .qr-input:focus { outline: none; border-color: var(--color-accent); }
        .qr-input::placeholder { color: var(--color-muted); }
        .qr-go { font-family: var(--font-mono); font-size: 10px; letter-spacing: .18em; text-transform: uppercase; padding: 0 1.4rem; border: 1px solid var(--color-accent); background: var(--color-accent); color: var(--color-ink); font-weight: 600; cursor: pointer; }
        .qr-go:disabled { opacity: .4; cursor: not-allowed; }
        .qr-opts { display: flex; flex-wrap: wrap; align-items: center; gap: .4rem; margin-top: .6rem; }
        .qr-opt { font-family: var(--font-mono); font-size: 9px; letter-spacing: .16em; text-transform: uppercase; padding: .35rem .7rem; border: 1px solid var(--color-border); background: transparent; color: var(--color-muted); cursor: pointer; }
        .qr-opt:hover { color: var(--color-paper); border-color: var(--color-paper); }
        .qr-opt.is-on { color: var(--color-accent); border-color: var(--color-accent); }
        .qr-meta { margin-left: auto; font-family: var(--font-mono); font-size: 9px; letter-spacing: .14em; text-transform: uppercase; color: var(--color-muted); }
        .qr-status { margin: 1.2rem 0; font-family: var(--font-mono); font-size: 10px; letter-spacing: .18em; text-transform: uppercase; color: var(--color-accent); }
        .qr-err { margin: 1.4rem 0; border-left: 2px solid var(--color-border); padding-left: .9rem; }
        .qr-err-h { font-family: var(--font-mono); font-size: 10px; letter-spacing: .18em; text-transform: uppercase; color: var(--color-paper); margin: 0 0 .35rem; }
        .qr-warn { margin: 1.4rem 0; border: 1px solid color-mix(in srgb, var(--color-accent) 40%, transparent); border-left-width: 2px; padding: .8rem .9rem; background: color-mix(in srgb, var(--color-accent) 5%, transparent); }
        .qr-warn-h { font-family: var(--font-mono); font-size: 10px; letter-spacing: .18em; text-transform: uppercase; color: var(--color-accent); margin: 0 0 .35rem; }
        .qr-warn-b { font-size: .85rem; color: var(--color-text); margin: 0; max-width: 52em; line-height: 1.6; }
        .qr-err-b { font-size: .88rem; color: var(--color-muted); margin: 0; max-width: 48em; line-height: 1.55; }
      `}</style>
    </div>
  );
}
