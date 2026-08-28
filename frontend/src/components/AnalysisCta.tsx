import Link from "next/link";

/**
 * The mandatory end-of-analysis CTA (#93: "CTA am Ende jeder Analyse — 'So
 * entstanden. Für Ihre Frage: Anfrage.' Das ist der Lead-Pfad, ohne ihn ist
 * die Seite Deko."). Pulled out as its own component (not inlined in
 * `/analysis/[slug]`) so every analysis renders the exact same lead path —
 * and so a future analysis format (MDX, a second content source) gets it for
 * free.
 *
 * Styling mirrors `ForesightCta`'s `compact` variant (same accent-bordered
 * card, same button treatment) so this reads as part of the same design
 * system rather than a bolted-on box — but it always renders (no
 * `isPublicMode()` gate): `/enquiry` is a public route in both modes.
 */
export default function AnalysisCta() {
  return (
    <div className="mt-16 border border-accent/30 bg-accent/5 p-8">
      <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-4">
        —— How this was made
      </div>
      <p className="font-sans text-text text-base leading-relaxed mb-6 max-w-xl">
        Built from our corpus, reviewed by a human. Have a question of your
        own?
      </p>
      <Link
        href="/enquiry"
        className="inline-flex items-center gap-2 bg-accent text-ink px-5 py-3 font-mono text-[10px] uppercase tracking-[0.18em] hover:bg-accent-deep transition-colors"
      >
        Request an analysis →
      </Link>
    </div>
  );
}
