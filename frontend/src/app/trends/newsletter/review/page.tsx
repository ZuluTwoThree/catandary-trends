import Link from "next/link";
import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { canReview } from "@/lib/review-access";
import { getNewsletterEdition } from "@/lib/db";
import {
  editionState,
  getEditionApproval,
  listEditionApprovals,
  type EditionApproval,
  type EditionState,
} from "@/lib/newsletterReview";
import { renderEditionMail } from "@/lib/newsletterMail";
import {
  AI_DISCLOSURE_EN,
  EDITION_BLOCKS,
  PROVENANCE_BADGE,
  type AiProvenance,
} from "@/lib/aiDisclosure";
import { releaseAction, withdrawAction } from "./actions";

/**
 * /trends/newsletter/review — the release desk (owner mandate 2026-09-06).
 *
 * The owner reads every issue here and releases it before it may be mailed;
 * pipeline/newsletter_sender.py refuses to send an edition without
 * `approved_at` (exit 2). The preview is not a re-implementation of the mail:
 * it is the mail, rendered by the Python template through
 * lib/newsletterMail.ts, shown in a sandboxed iframe.
 *
 * Owner-only, three locks: the route is in BLOCKED_PREFIXES (404 under
 * PUBLIC_MODE, Proxy), it is excluded from the static export
 * (frontend/static-export.exclude), and canReview() guards the page and both
 * Server Actions.
 */

export const metadata: Metadata = { title: "Newsletter release", robots: { index: false } };

const NOTICES: Record<string, string> = {
  released: "Edition released — it may now be sent.",
  "release-failed": "Not released: the edition has already been sent.",
  withdrawn: "Release withdrawn — sending is blocked again.",
  "withdraw-failed": "Not withdrawn: the edition has already been sent.",
};

const STATE_STYLE: Record<EditionState, string> = {
  draft: "text-muted border-border",
  released: "text-accent border-accent/50",
  sent: "text-paper border-border",
};

const PROVENANCE_STYLE: Record<AiProvenance, string> = {
  generated: "border-accent/50 text-accent",
  computed: "border-border text-paper",
  curated: "border-border text-muted",
};

function stateLabel(e: EditionApproval): string {
  const s = editionState(e);
  if (s === "sent") {
    return `Sent ${short(e.sent_at)}${e.recipients_count != null ? ` · ${e.recipients_count} recipients` : ""}`;
  }
  if (s === "released") return `Released ${short(e.approved_at)}`;
  return "Draft — not released";
}

/** "6 Sep 2026, 09:12" from a Postgres timestamp string; "" when absent. */
function short(ts: string | null): string {
  if (!ts) return "";
  const d = new Date(ts.replace(" ", "T"));
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function intParam(v: string | string[] | undefined): number | null {
  const n = Number(Array.isArray(v) ? v[0] : v);
  return Number.isInteger(n) && n > 0 ? n : null;
}

export default async function NewsletterReviewPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  // 404 rather than 403: an unauthorised visitor learns nothing about the route.
  if (!canReview()) notFound();

  const sp = await searchParams;
  const editions = await listEditionApprovals(30);
  const year = intParam(sp.year);
  const week = intParam(sp.week);
  const selectedKey =
    year && week ? { year, week } : editions[0] ? { year: editions[0].year, week: editions[0].week } : null;

  const selected = selectedKey ? await getEditionApproval(selectedKey.year, selectedKey.week) : null;
  const [content, mail] = selected
    ? await Promise.all([
        getNewsletterEdition(selected.year, selected.week),
        renderEditionMail(selected.year, selected.week),
      ])
    : [null, null];

  const notice = typeof sp.notice === "string" ? NOTICES[sp.notice] : undefined;
  const state = selected ? editionState(selected) : null;

  // Which sections this edition actually carries — a badge for a block that
  // is not in the issue would be noise.
  const present: Record<string, string> = {
    editorial: content?.editorial ? "present" : "",
    deep_dive: selected?.has_deep_dive ? "present" : "",
    vertical_summaries: content ? `${Object.keys(content.vertical_summaries ?? {}).length} verticals` : "",
    trend_refs: content
      ? `${Object.values(content.trend_refs ?? {}).reduce((n, r) => n + r.length, 0)} signals`
      : "",
    mega_trend_radar: content ? `${(content.mega_trend_radar ?? []).length} themes` : "",
  };

  return (
    <div className="mx-auto max-w-6xl px-4 py-10">
      <header className="border-b border-border pb-6">
        <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-accent">
          Human in the loop
        </p>
        <h1 className="mt-3 font-display text-[34px] leading-[1.1] text-paper">
          Newsletter release
        </h1>
        <p className="mt-3 max-w-3xl text-[14px] leading-[1.65] text-muted">
          Read the issue exactly as a subscriber will receive it, then release
          it. Without a release the sender mails nothing:{" "}
          <code className="text-paper">newsletter_sender.py</code> exits with an
          error while <code>approved_at</code> is empty, and there is no flag to
          switch that off. A release can be withdrawn until the issue has gone
          out.
        </p>
      </header>

      {notice && (
        <p className="mt-6 border-l-[3px] border-accent bg-card/40 px-4 py-3 text-[13px] text-paper">
          {notice}
        </p>
      )}

      <div className="mt-8 grid gap-8 lg:grid-cols-[260px_1fr]">
        {/* Edition list */}
        <nav aria-label="Editions" className="lg:border-r lg:border-border lg:pr-6">
          <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted">
            Editions
          </p>
          <ul className="mt-4 space-y-1">
            {editions.map((e) => {
              const active = selected?.year === e.year && selected?.week === e.week;
              const s = editionState(e);
              return (
                <li key={e.id}>
                  <Link
                    href={`/trends/newsletter/review?year=${e.year}&week=${e.week}`}
                    className={`flex items-baseline justify-between gap-3 border-l-[3px] px-3 py-2 text-[13px] transition-colors ${
                      active
                        ? "border-accent bg-card/60 text-paper"
                        : "border-transparent text-muted hover:border-border hover:text-paper"
                    }`}
                  >
                    <span className="font-mono">
                      W{String(e.week).padStart(2, "0")}/{e.year}
                    </span>
                    <span
                      className={`font-mono text-[9px] uppercase tracking-[0.14em] ${
                        s === "released" ? "text-accent" : s === "sent" ? "text-paper" : "text-muted"
                      }`}
                    >
                      {s}
                    </span>
                  </Link>
                </li>
              );
            })}
            {editions.length === 0 && (
              <li className="px-3 py-2 text-[13px] text-muted">No editions yet.</li>
            )}
          </ul>
        </nav>

        {/* Detail */}
        <div>
          {!selected ? (
            <p className="text-[15px] text-muted">
              Nothing to release. The Monday job writes the week&rsquo;s edition at 09:00.
            </p>
          ) : (
            <>
              <div className="flex flex-wrap items-baseline justify-between gap-4 border-b border-border pb-4">
                <h2 className="font-display text-[26px] text-paper">
                  Week {selected.week}/{selected.year}
                </h2>
                <span
                  className={`border px-3 py-1 font-mono text-[10px] uppercase tracking-[0.16em] ${
                    STATE_STYLE[state ?? "draft"]
                  }`}
                >
                  {stateLabel(selected)}
                </span>
              </div>
              <p className="mt-3 font-mono text-[11px] uppercase tracking-[0.12em] text-muted">
                {selected.total_signals.toLocaleString("en-GB")} signals · generated{" "}
                {short(selected.created_at)}
                {selected.approved_by ? ` · released by ${selected.approved_by}` : ""}
              </p>
              {selected.approval_note && (
                <p className="mt-2 text-[13px] text-muted">
                  Note: <span className="text-paper">{selected.approval_note}</span>
                </p>
              )}

              {/* --- AI labelling ------------------------------------------ */}
              <section className="mt-8 border border-border bg-card/40 p-5">
                <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted">
                  What a machine made
                </p>
                <ul className="mt-4 space-y-3">
                  {EDITION_BLOCKS.map((b) => {
                    const info = present[b.key];
                    if (!info) return null;
                    return (
                      <li key={b.key} className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                        <span
                          className={`border px-2 py-[2px] font-mono text-[9px] uppercase tracking-[0.14em] ${
                            PROVENANCE_STYLE[b.provenance]
                          }`}
                        >
                          {PROVENANCE_BADGE[b.provenance]}
                        </span>
                        <span className="text-[13px] text-paper">{b.label}</span>
                        {info !== "present" && (
                          <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
                            {info}
                          </span>
                        )}
                        <span className="basis-full text-[12px] leading-[1.6] text-muted">
                          {b.detail}
                        </span>
                      </li>
                    );
                  })}
                </ul>
                <p className="mt-5 border-t border-dashed border-border pt-4 text-[12px] leading-[1.6] text-muted">
                  In the mail and on the website every issue carries this line:{" "}
                  <span className="text-paper">&ldquo;{AI_DISCLOSURE_EN}&rdquo;</span>
                </p>
              </section>

              {/* --- Release ----------------------------------------------- */}
              <section className="mt-8 border border-border bg-card/40 p-5">
                <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted">
                  Release
                </p>
                {state === "sent" ? (
                  <p className="mt-4 text-[13px] text-muted">
                    This issue was sent on {short(selected.sent_at)}
                    {selected.recipients_count != null
                      ? ` to ${selected.recipients_count} recipients`
                      : ""}
                    . A sent issue cannot be un-released.
                  </p>
                ) : state === "released" ? (
                  <>
                    <p className="mt-4 text-[13px] text-muted">
                      Released {short(selected.approved_at)} by{" "}
                      <span className="text-paper">{selected.approved_by}</span>. The sender may
                      mail it (<code>python -m pipeline.newsletter_sender --year {selected.year}{" "}
                      --week {selected.week}</code>).
                    </p>
                    <form action={withdrawAction} className="mt-4">
                      <input type="hidden" name="year" value={selected.year} />
                      <input type="hidden" name="week" value={selected.week} />
                      <button
                        type="submit"
                        className="border border-border px-4 py-2 font-mono text-[11px] uppercase tracking-[0.14em] text-muted transition-colors hover:border-paper hover:text-paper"
                      >
                        Withdraw release
                      </button>
                    </form>
                  </>
                ) : (
                  <form action={releaseAction} className="mt-4 space-y-3">
                    <input type="hidden" name="year" value={selected.year} />
                    <input type="hidden" name="week" value={selected.week} />
                    <label
                      htmlFor="note"
                      className="block font-mono text-[10px] uppercase tracking-[0.14em] text-muted"
                    >
                      Note (optional)
                    </label>
                    <textarea
                      id="note"
                      name="note"
                      rows={2}
                      maxLength={500}
                      placeholder="What you checked, what you changed by hand…"
                      className="w-full border border-border bg-background px-3 py-2 text-[13px] text-paper placeholder:text-muted/60 focus:border-accent focus:outline-none"
                    />
                    <button
                      type="submit"
                      className="border border-accent bg-accent px-4 py-2 font-mono text-[11px] uppercase tracking-[0.14em] text-background transition-opacity hover:opacity-80"
                    >
                      Release for sending
                    </button>
                  </form>
                )}
              </section>

              {/* --- The mail itself --------------------------------------- */}
              <section className="mt-8">
                <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted">
                  Preview — the mail a subscriber receives
                </p>
                <p className="mt-2 text-[12px] leading-[1.6] text-muted">
                  Rendered by the sender&rsquo;s own template
                  (<code>pipeline/newsletter_preview.py</code>), so this is the delivered HTML —
                  only the personal unsubscribe link is a placeholder. Links are inert inside the
                  preview frame.
                </p>
                {mail?.ok ? (
                  <iframe
                    title={`Newsletter week ${selected.week}/${selected.year}`}
                    srcDoc={mail.html}
                    sandbox=""
                    className="mt-4 h-[900px] w-full border border-border bg-background"
                  />
                ) : (
                  <pre className="mt-4 overflow-x-auto border border-border bg-card/40 p-4 text-[12px] text-muted">
                    Preview failed: {mail?.error ?? "no renderer"}
                  </pre>
                )}
              </section>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
