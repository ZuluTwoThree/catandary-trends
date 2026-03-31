"use client";

export default function NewsletterPage() {
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
        <form
          className="flex flex-col sm:flex-row gap-3"
          onSubmit={(e) => e.preventDefault()}
        >
          <input
            type="email"
            placeholder="deine@email.de"
            className="flex-1 rounded-lg bg-background border border-border px-4 py-2.5 text-sm text-foreground placeholder:text-muted focus:outline-none focus:border-accent"
            required
          />
          <button
            type="submit"
            className="bg-accent text-background px-6 py-2.5 rounded-lg font-medium hover:bg-accent/90 transition-colors text-sm whitespace-nowrap"
          >
            Abonnieren
          </button>
        </form>
        <p className="text-xs text-muted mt-3">
          Kein Spam. Jederzeit abmeldbar. Newsletter-Integration folgt in Sprint 4.
        </p>
      </div>

      <div className="mt-12 grid grid-cols-1 sm:grid-cols-2 gap-4 text-left">
        <div className="rounded-lg border border-border bg-card p-4">
          <h3 className="font-medium mb-1">Wöchentliche Top-Trends</h3>
          <p className="text-sm text-muted">
            Die wichtigsten Signale aus allen Vertikalen, jeden Montag.
          </p>
        </div>
        <div className="rounded-lg border border-border bg-card p-4">
          <h3 className="font-medium mb-1">Cross-Industry Insights</h3>
          <p className="text-sm text-muted">
            Trends die mehrere Branchen betreffen — Frühwarnsystem.
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
