/**
 * Minimal share-of-voice sparkline (single series → no legend; the card names
 * it). 2px line, accent end-dot; native <title> carries the plain-language
 * summary so the information is never color-alone.
 */
export default function Sparkline({
  points,
  months,
  label,
  className = "w-full h-9",
  unit = "share",
}: {
  points: number[]; // share values 0..1, chronological
  months: string[]; // same length, YYYY-MM
  label: string;
  className?: string; // the detail view renders the same series taller
  /** What the values are. The emerging layer plots counts, not shares. */
  unit?: "share" | "count";
}) {
  if (points.length < 2) return null;
  const W = 220;
  const H = 36;
  const PAD = 3;
  const max = Math.max(...points, 0.0001);
  const x = (i: number) => PAD + (i / (points.length - 1)) * (W - 2 * PAD);
  const y = (v: number) => H - PAD - (v / max) * (H - 2 * PAD);
  const d = points.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const last = points[points.length - 1];
  const first = months[0];
  const lastM = months[months.length - 1];
  const title =
    unit === "count"
      ? `Documents per month resembling this pocket, ${first} to ${lastM}. Latest: ${Math.round(last)}.`
      : `Share of monthly signal volume, ${first} to ${lastM}. Latest: ${(last * 100).toFixed(1)}%.`;

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className={`${className} text-muted`}
      role="img"
      aria-label={title}
    >
      <title>{title}</title>
      <polyline
        points={d}
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <circle
        cx={x(points.length - 1)}
        cy={y(last)}
        r="3"
        fill="var(--color-accent)"
      />
    </svg>
  );
}
