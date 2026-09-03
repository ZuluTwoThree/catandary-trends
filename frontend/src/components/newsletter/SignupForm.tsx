"use client";

import { useState, useId } from "react";
import Link from "next/link";
import { isStaticExport, linkPrefetch } from "@/lib/renderMode";
import { sitePath } from "@/lib/sitePaths";

/**
 * Newsletter signup (shared by the workstation page and the static export).
 *
 * Static hosting (design 4.2): the form posts form-encoded to the PHP
 * double-opt-in backend that already serves the landing page
 * (docs/launch/newsletter-doi-php/subscribe.php — fields email, consent,
 * honeypot `website`; JSON {ok, message} back). Consent is a real checkbox
 * there because the backend refuses without it (Art. 7 DSGVO evidence), and
 * the value sent mirrors the checkbox — never a hard-coded "1". No /api/*
 * request is made in the export; the workstation instance keeps its
 * /api/newsletter route.
 */
const PHP_SUBSCRIBE_ENDPOINT = "/newsletter/subscribe.php";

export default function SignupForm() {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
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
        const body = new URLSearchParams({
          email,
          consent: consent ? "1" : "",
          website: "", // honeypot: must stay empty (subscribe.php)
        });
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
          <form className="flex flex-col gap-3" onSubmit={handleSubmit}>
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
          prefetch={linkPrefetch()}
          href={sitePath("/privacy")}
          className="underline hover:text-accent transition-colors"
        >
          Privacy
        </Link>
      </p>
    </div>
  );
}
