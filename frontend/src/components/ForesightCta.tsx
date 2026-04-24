export default function ForesightCta({ compact }: { compact?: boolean }) {
  if (compact) {
    return (
      <div className="mt-16 border border-accent/30 bg-accent/5 p-6">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-3">
          —— Premium Forecast
        </div>
        <p className="font-sans text-text text-sm leading-relaxed mb-5 max-w-xl">
          Complete Mega/Macro/Micro classification and strategic forecasts.
        </p>
        <a
          href="https://catandary.de"
          className="inline-flex items-center gap-2 bg-accent text-ink px-4 py-2 font-mono text-[10px] uppercase tracking-[0.18em] hover:bg-accent-deep transition-colors"
        >
          Catandary Foresight →
        </a>
      </div>
    );
  }

  return (
    <div className="mt-20 border border-accent/30 bg-accent/5 p-8">
      <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent mb-4">
        —— Looking Deeper
      </div>
      <h2 className="font-display text-[30px] leading-tight text-paper mb-3">
        Strategic <span className="italic">Forecasts</span>
      </h2>
      <p className="font-sans text-text text-base leading-relaxed mb-6 max-w-xl">
        Catandary Foresight delivers the full Mega/Macro/Micro classification,
        cross-industry clusters, and strategic recommendations tailored to your
        business.
      </p>
      <a
        href="https://catandary.de"
        className="inline-flex items-center gap-2 bg-accent text-ink px-5 py-3 font-mono text-[10px] uppercase tracking-[0.18em] hover:bg-accent-deep transition-colors"
      >
        Discover Catandary Foresight →
      </a>
    </div>
  );
}
