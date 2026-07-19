/**
 * Tiny inline share-trajectory sparkline for a lineage thread. Server-safe
 * (pure SVG, no client hooks). Points are share-of-voice per window; the line
 * is normalized to its own max so the shape reads regardless of absolute size.
 */
export default function ThreadSparkline({
  points,
  color = "currentColor",
  width = 120,
  height = 28,
}: {
  points: { share: number }[];
  color?: string;
  width?: number;
  height?: number;
}) {
  if (points.length < 2) {
    return <svg width={width} height={height} aria-hidden="true" />;
  }
  const max = Math.max(...points.map((p) => p.share), 1e-9);
  const dx = width / (points.length - 1);
  const path = points
    .map((p, i) => {
      const x = i * dx;
      const y = height - 2 - (height - 4) * (p.share / max);
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const last = points[points.length - 1];
  const lastX = width;
  const lastY = height - 2 - (height - 4) * (last.share / max);
  return (
    <svg width={width} height={height} aria-hidden="true" className="thread-spark">
      <path d={path} fill="none" stroke={color} strokeWidth={1.6} strokeOpacity={0.85} />
      <circle cx={lastX - 1} cy={lastY} r={2.4} fill={color} />
    </svg>
  );
}
