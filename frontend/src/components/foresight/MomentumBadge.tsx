/**
 * Momentum chip — glyph + label + color (never color alone), matching the
 * MegaTrendsPage badge pattern. Detail numbers live in the tooltip, not the
 * primary text (low-threshold UX).
 */
const CONFIG = {
  rising: {
    label: "Rising", color: "#22c55e", glyph: "↗",
    text: "gaining share of attention",
  },
  stable: {
    label: "Stable", color: "#a3a3a3", glyph: "→",
    text: "holding steady",
  },
  declining: {
    label: "Declining", color: "#ef4444", glyph: "↘",
    text: "losing share of attention",
  },
  unknown: {
    label: "New window", color: "#a855f7", glyph: "◆",
    text: "observation window still too short to call",
  },
} as const;

export type Momentum = keyof typeof CONFIG;

export function momentumText(m: Momentum): string {
  return CONFIG[m].text;
}

export default function MomentumBadge({
  momentum,
  deltaPp,
}: {
  momentum: Momentum;
  deltaPp: number;
}) {
  const c = CONFIG[momentum] ?? CONFIG.unknown;
  const detail =
    momentum === "unknown"
      ? c.text
      : `${c.text} — share of monthly signal volume moved ${deltaPp > 0 ? "+" : ""}${deltaPp.toFixed(1)} percentage points from the early to the late observation window.`;
  return (
    <span
      className="inline-flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-[0.12em] px-2 py-0.5 border cursor-help shrink-0"
      title={detail}
      style={{
        color: c.color,
        borderColor: c.color + "55",
        backgroundColor: c.color + "10",
      }}
    >
      <span>{c.glyph}</span>
      <span>{c.label}</span>
    </span>
  );
}
