"use client";

import { useState } from "react";
import { useLocale } from "@/lib/locale-context";

export default function NewsletterPage() {
  const { t } = useLocale();
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
    <div className="mx-auto max-w-2xl px-4 py-16 text-center">
      <h1 className="text-3xl font-bold tracking-tight mb-4">
        {t("newsletterTitle")}
      </h1>
      <p className="text-muted text-lg mb-8 max-w-lg mx-auto">
        {t("newsletterSubtitle")}
      </p>

      <div className="rounded-xl border border-border bg-card p-8">
        {status === "success" ? (
          <div className="text-center">
            <div className="text-accent text-2xl mb-3">&#10003;</div>
            <p className="text-foreground font-medium">{message}</p>
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
              placeholder={t("newsletterPlaceholder")}
              className="flex-1 rounded-lg bg-background border border-border px-4 py-2.5 text-sm text-foreground placeholder:text-muted focus:outline-none focus:border-accent"
              required
              disabled={status === "loading"}
            />
            <button
              type="submit"
              disabled={status === "loading"}
              className="bg-accent text-background px-6 py-2.5 rounded-lg font-medium hover:bg-accent/90 transition-colors text-sm whitespace-nowrap disabled:opacity-50"
            >
              {status === "loading"
                ? t("newsletterLoading")
                : t("newsletterButton")}
            </button>
          </form>
        )}
        {status === "error" && (
          <p className="text-red-400 text-sm mt-3">{message}</p>
        )}
        {status !== "success" && (
          <p className="text-xs text-muted mt-3">{t("newsletterSpam")}</p>
        )}
      </div>

      <div className="mt-12 grid grid-cols-1 sm:grid-cols-2 gap-4 text-left">
        <div className="rounded-lg border border-border bg-card p-4">
          <h3 className="font-medium mb-1">{t("newsletterFeature1Title")}</h3>
          <p className="text-sm text-muted">{t("newsletterFeature1Text")}</p>
        </div>
        <div className="rounded-lg border border-border bg-card p-4">
          <h3 className="font-medium mb-1">{t("newsletterFeature2Title")}</h3>
          <p className="text-sm text-muted">{t("newsletterFeature2Text")}</p>
        </div>
        <div className="rounded-lg border border-border bg-card p-4">
          <h3 className="font-medium mb-1">{t("newsletterFeature3Title")}</h3>
          <p className="text-sm text-muted">{t("newsletterFeature3Text")}</p>
        </div>
        <div className="rounded-lg border border-border bg-card p-4">
          <h3 className="font-medium mb-1">{t("newsletterFeature4Title")}</h3>
          <p className="text-sm text-muted">{t("newsletterFeature4Text")}</p>
        </div>
      </div>
    </div>
  );
}
