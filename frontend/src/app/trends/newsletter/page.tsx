"use client";

import { useState } from "react";

export default function NewsletterPage() {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
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
      setMessage("Verbindungsfehler. Bitte versuche es erneut.");
    }
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-16 text-center">
      <h1 className="text-3xl font-bold tracking-tight mb-4">
        Trends Newsletter
      </h1>
      <p className="text-muted text-lg mb-8 max-w-lg mx-auto">
        Jeden Montag die wichtigsten Trend-Signale aus 10 Branchen.
        Kuratiert, analysiert, eingeordnet.
      </p>

      <div className="rounded-xl border border-border bg-card p-8">
        {status === "success" ? (
          <div className="text-center">
            <div className="text-accent text-2xl mb-3">&#10003;</div>
            <p className="text-foreground font-medium">{message}</p>
          </div>
        ) : (
          <form className="flex flex-col sm:flex-row gap-3" onSubmit={handleSubmit}>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="deine@email.de"
              className="flex-1 rounded-lg bg-background border border-border px-4 py-2.5 text-sm text-foreground placeholder:text-muted focus:outline-none focus:border-accent"
              required
              disabled={status === "loading"}
            />
            <button
              type="submit"
              disabled={status === "loading"}
              className="bg-accent text-background px-6 py-2.5 rounded-lg font-medium hover:bg-accent/90 transition-colors text-sm whitespace-nowrap disabled:opacity-50"
            >
              {status === "loading" ? "..." : "Abonnieren"}
            </button>
          </form>
        )}
        {status === "error" && (
          <p className="text-red-400 text-sm mt-3">{message}</p>
        )}
        {status !== "success" && (
          <p className="text-xs text-muted mt-3">
            Kein Spam. Jederzeit abmeldbar.
          </p>
        )}
      </div>

      <div className="mt-12 grid grid-cols-1 sm:grid-cols-2 gap-4 text-left">
        <div className="rounded-lg border border-border bg-card p-4">
          <h3 className="font-medium mb-1">Top-Trends der Woche</h3>
          <p className="text-sm text-muted">
            Die wichtigsten Signale aus allen Vertikalen, jeden Montag.
          </p>
        </div>
        <div className="rounded-lg border border-border bg-card p-4">
          <h3 className="font-medium mb-1">Cross-Industry Insights</h3>
          <p className="text-sm text-muted">
            Trends die mehrere Branchen betreffen — dein Frühwarnsystem.
          </p>
        </div>
        <div className="rounded-lg border border-border bg-card p-4">
          <h3 className="font-medium mb-1">PESTEL-Analyse</h3>
          <p className="text-sm text-muted">
            Politische, wirtschaftliche und technologische Einordnung.
          </p>
        </div>
        <div className="rounded-lg border border-border bg-card p-4">
          <h3 className="font-medium mb-1">Foresight-Previews</h3>
          <p className="text-sm text-muted">
            Exklusive Vorschauen auf Catandary Foresight Analysen.
          </p>
        </div>
      </div>
    </div>
  );
}
