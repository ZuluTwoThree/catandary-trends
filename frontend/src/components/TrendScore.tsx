export default function TrendScore({ score }: { score: number | null }) {
  if (score === null || score === undefined) return null;

  const pct = Math.round(score * 100);
  const hue = score > 0.8 ? 142 : score > 0.6 ? 47 : 0;

  return (
    <div className="flex items-center gap-1.5">
      <div className="h-1.5 w-12 rounded-full bg-border overflow-hidden">
        <div
          className="h-full rounded-full transition-all"
          style={{
            width: `${pct}%`,
            backgroundColor: `hsl(${hue}, 70%, 50%)`,
          }}
        />
      </div>
      <span className="text-xs text-muted">{pct}%</span>
    </div>
  );
}
