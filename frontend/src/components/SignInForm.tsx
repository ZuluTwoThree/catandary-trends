"use client";

import { useState } from "react";
import { sitePath } from "@/lib/sitePaths";

/**
 * Email-gate sign-in: request a magic link. One field, plain language, no
 * password. Editorial styling (DS-04). The newsletter opt-in is NOT
 * pre-checked (COPY-05 — pre-ticked consent is invalid under GDPR), rate
 * limits get their own message instead of a retry-now prompt (COPY-15), and
 * status changes are announced to assistive tech (A11Y-02).
 */
export default function SignInForm({
  error,
  next,
  reason,
}: {
  error?: string;
  next?: string;
  reason?: string;
}) {
  const [email, setEmail] = useState("");
  const [newsletter, setNewsletter] = useState(false);
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error" | "ratelimited">(
    "idle"
  );
  const [devLink, setDevLink] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setState("sending");
    setDevLink(null);
    try {
      const res = await fetch("/api/auth/request", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, newsletter, ...(next ? { next } : {}) }),
      });
      if (res.status === 429) {
        setState("ratelimited");
        return;
      }
      if (!res.ok) throw new Error();
      const data = await res.json();
      setState("sent");
      if (data.devLink) setDevLink(data.devLink);
    } catch {
      setState("error");
    }
  }

  const card =
    "max-w-md mx-auto my-16 border border-border bg-card p-8";

  if (state === "sent") {
    return (
      <div className={card} role="status">
        <span className="eyebrow">Sign in</span>
        <h1 className="font-display text-[28px] leading-[1.15] text-paper mt-3 mb-3">
          Check your inbox
        </h1>
        <p className="text-[14px] leading-[1.6] text-muted">
          We sent a sign-in link to <strong className="text-foreground">{email}</strong>.
          It is valid for 15 minutes.
        </p>
        {devLink && (
          <p className="mt-4 text-[12px] leading-[1.5] text-muted break-all">
            Dev link (console transport): <a href={devLink} className="text-accent">{devLink}</a>
          </p>
        )}
      </div>
    );
  }

  return (
    <div className={card}>
      <span className="eyebrow">Sign in</span>
      <h1 className="font-display text-[28px] leading-[1.15] text-paper mt-3 mb-2">
        Sign in to Catandary Trends
      </h1>
      <p className="text-[14px] leading-[1.6] text-muted mb-5">
        Enter your email and we&apos;ll send a one-click sign-in link — no password.
      </p>
      {reason === "checkout" && (
        <p className="mb-4 border border-accent/30 bg-accent/5 px-3 py-2 text-[13px] leading-[1.5] text-foreground">
          Sign in first — we&apos;ll take you straight back to the plans to finish
          your checkout.
        </p>
      )}
      <div aria-live="assertive">
        {error === "link" && (
          <p role="alert" className="mb-3 text-[13px] text-warn">
            That link was invalid or expired. Request a new one below.
          </p>
        )}
        {state === "error" && (
          <p role="alert" className="mb-3 text-[13px] text-warn">
            We couldn&apos;t send the email right now — please try again shortly.
          </p>
        )}
        {state === "ratelimited" && (
          <p role="alert" className="mb-3 text-[13px] text-warn">
            Too many attempts — please wait a minute before trying again.
          </p>
        )}
      </div>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <div>
          <label
            htmlFor="signin-email"
            className="block font-mono text-[10px] uppercase tracking-[0.16em] text-muted mb-1.5"
          >
            Email address
          </label>
          <input
            id="signin-email"
            type="email"
            required
            autoComplete="email"
            placeholder="you@company.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full bg-background border border-border-strong px-3.5 py-2.5 text-[14px] text-foreground placeholder:text-muted focus:border-accent outline-none"
          />
        </div>
        <label className="flex items-start gap-2.5 text-[13px] leading-[1.5] text-muted cursor-pointer">
          <input
            type="checkbox"
            checked={newsletter}
            onChange={(e) => setNewsletter(e.target.checked)}
            className="mt-0.5 accent-[#d4ff3a]"
          />
          Also send me the weekly trend briefing — one email a week, unsubscribe
          anytime.
        </label>
        <button
          type="submit"
          disabled={state === "sending"}
          className="bg-accent text-ink py-2.5 font-mono text-[11px] uppercase tracking-[0.16em] font-semibold hover:bg-accent-deep transition-colors disabled:opacity-60 disabled:cursor-wait"
        >
          {state === "sending" ? "Sending…" : "Send sign-in link"}
        </button>
      </form>
      <p className="mt-4 text-[11px] leading-[1.5] text-muted">
        We use your email only for sign-in{newsletter ? " and the briefing you opted into" : ""}.{" "}
        <a href={sitePath("/privacy")} className="underline hover:text-paper">
          Privacy
        </a>
      </p>
    </div>
  );
}
