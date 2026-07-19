"use client";

import { useState } from "react";

/**
 * Email-gate sign-in: request a magic link. Low-threshold — one field, plain
 * language, no password. In console-transport dev the API returns the link so
 * the flow is testable before DNS verification.
 */
export default function SignInForm({ error }: { error?: string }) {
  const [email, setEmail] = useState("");
  const [newsletter, setNewsletter] = useState(true);
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [devLink, setDevLink] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setState("sending");
    setDevLink(null);
    try {
      const res = await fetch("/api/auth/request", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, newsletter }),
      });
      if (!res.ok) throw new Error();
      const data = await res.json();
      setState("sent");
      if (data.devLink) setDevLink(data.devLink);
    } catch {
      setState("error");
    }
  }

  if (state === "sent") {
    return (
      <div className="signin-card">
        <h1 className="signin-title">Check your inbox</h1>
        <p className="signin-line">
          We sent a sign-in link to <strong>{email}</strong>. It is valid for 15
          minutes.
        </p>
        {devLink && (
          <p className="signin-dev">
            Dev link (console transport):{" "}
            <a href={devLink}>{devLink}</a>
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="signin-card">
      <h1 className="signin-title">Sign in to Catandary Trends</h1>
      <p className="signin-line">
        Enter your email and we&apos;ll send a one-click sign-in link — no password.
      </p>
      {error === "link" && (
        <p className="signin-error">That link was invalid or expired. Request a new one.</p>
      )}
      {state === "error" && (
        <p className="signin-error">Something went wrong. Please try again.</p>
      )}
      <form onSubmit={submit} className="signin-form">
        <input
          type="email"
          required
          placeholder="you@company.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="signin-input"
        />
        <label className="signin-check">
          <input
            type="checkbox"
            checked={newsletter}
            onChange={(e) => setNewsletter(e.target.checked)}
          />
          Also send me the weekly trend newsletter
        </label>
        <button type="submit" disabled={state === "sending"} className="signin-btn">
          {state === "sending" ? "Sending…" : "Send sign-in link"}
        </button>
      </form>
      <style>{`
        .signin-card { max-width: 420px; margin: 4rem auto; padding: 2rem; border: 1px solid color-mix(in srgb, currentColor 14%, transparent); border-radius: 16px; }
        .signin-title { font-size: 1.5rem; font-weight: 700; margin-bottom: 0.5rem; }
        .signin-line { font-size: 0.9rem; opacity: 0.75; margin-bottom: 1.2rem; }
        .signin-form { display: flex; flex-direction: column; gap: 0.9rem; }
        .signin-input { padding: 0.7rem 0.9rem; border-radius: 10px; border: 1px solid color-mix(in srgb, currentColor 20%, transparent); background: transparent; color: inherit; font-size: 0.95rem; }
        .signin-check { display: flex; align-items: center; gap: 0.5rem; font-size: 0.82rem; opacity: 0.8; }
        .signin-btn { padding: 0.7rem 1rem; border-radius: 10px; border: none; background: #16a34a; color: white; font-weight: 600; cursor: pointer; }
        .signin-btn:disabled { opacity: 0.6; cursor: default; }
        .signin-error { color: #ef4444; font-size: 0.85rem; margin-bottom: 0.8rem; }
        .signin-dev { font-size: 0.75rem; opacity: 0.7; margin-top: 1rem; word-break: break-all; }
      `}</style>
    </div>
  );
}
