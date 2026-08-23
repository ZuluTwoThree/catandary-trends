/**
 * "Work in progress"-Kennzeichnung für den Startup Explorer (Owner 2026-08-23).
 * Ehrlichkeitsregel: der Explorer ist live, aber Abdeckung und Features
 * wachsen noch — das steht sichtbar dran, bis der Owner es entfernt.
 */
export default function WipBadge() {
  return (
    <span
      className="inline-block align-middle border border-accent/60 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.16em] text-accent"
      title="Coverage and features are still expanding — sources, matching and bridges are actively being built out."
    >
      Work in progress
    </span>
  );
}
