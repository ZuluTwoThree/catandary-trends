export default function ForesightCta({ compact }: { compact?: boolean }) {
  if (compact) {
    return (
      <div className="mt-12 rounded-xl border border-accent/20 bg-accent/5 p-6 text-center">
        <p className="text-sm text-muted mb-3">
          Complete Mega/Macro/Micro classification and strategic forecasts
        </p>
        <a
          href="https://catandary.de"
          className="inline-flex items-center gap-2 bg-accent text-background px-4 py-2 rounded-lg text-sm font-medium hover:bg-accent/90 transition-colors"
        >
          Catandary Foresight
        </a>
      </div>
    );
  }

  return (
    <div className="mt-16 rounded-xl border border-accent/20 bg-accent/5 p-8 text-center">
      <h2 className="text-xl font-semibold mb-2">
        Looking for deeper analysis?
      </h2>
      <p className="text-muted mb-4 max-w-lg mx-auto">
        Catandary Foresight delivers the full Mega/Macro/Micro classification,
        cross-industry clusters, and strategic recommendations tailored to your
        business.
      </p>
      <a
        href="https://catandary.de"
        className="inline-flex items-center gap-2 bg-accent text-background px-5 py-2.5 rounded-lg font-medium hover:bg-accent/90 transition-colors"
      >
        Discover Catandary Foresight
      </a>
    </div>
  );
}
