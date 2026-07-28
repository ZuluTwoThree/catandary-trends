import type { CSSProperties } from "react";

/**
 * "What's moving now" — six clusters the engine surfaced bottom-up, ranked by
 * share-of-voice momentum. These six were hand-checked against public reality
 * in docs/foresight_validation.md (6/6 correct), so they are used verbatim.
 * Server component; sparklines are inline SVG.
 */
type Card = {
  v: string;
  vc: string;
  name: string;
  dir: "up" | "down";
  pp: string;
  spark: number[];
};

const CARDS: Card[] = [
  { v: "TECH", vc: "#a78bfa", name: "Machine Learning · Deep Learning", dir: "up", pp: "+6.3 pp", spark: [3, 3, 4, 4, 5, 6, 7, 9, 10, 12] },
  { v: "FOOD", vc: "#f97316", name: "Functional Beverages · Health", dir: "up", pp: "+4.9 pp", spark: [4, 4, 5, 5, 6, 7, 7, 8, 9, 10] },
  { v: "TECH", vc: "#a78bfa", name: "Chip Design · Semiconductor", dir: "up", pp: "+2.4 pp", spark: [6, 6, 6, 7, 7, 7, 8, 8, 9, 9] },
  { v: "HEALTH", vc: "#34d399", name: "Gut Microbiome · Nutrition", dir: "up", pp: "+1.5 pp", spark: [5, 5, 6, 6, 6, 7, 7, 7, 8, 8] },
  { v: "ECO", vc: "#22d3ee", name: "Carbon Capture · Climate Policy", dir: "up", pp: "+1.0 pp", spark: [4, 5, 5, 5, 6, 6, 6, 7, 7, 7] },
  { v: "TECH", vc: "#a78bfa", name: "Electric Vehicles · Automotive", dir: "down", pp: "−2.5 pp", spark: [9, 9, 8, 8, 8, 7, 7, 6, 6, 6] },
];

function Spark({ vals, color }: { vals: number[]; color: string }) {
  const w = 96;
  const h = 26;
  const max = Math.max(...vals);
  const min = Math.min(...vals);
  const rng = max - min || 1;
  const coords = vals.map((v, i) => {
    const x = (i / (vals.length - 1)) * (w - 4) + 2;
    const y = h - 2 - ((v - min) / rng) * (h - 6);
    return [x, y] as const;
  });
  const points = coords.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const last = coords[coords.length - 1];
  return (
    <svg className="lp-mspark" viewBox={`0 0 ${w} ${h}`} fill="none" aria-hidden="true">
      <polyline points={points} stroke={color} strokeWidth="1.6" />
      <circle cx={last[0]} cy={last[1]} r="2" fill={color} />
    </svg>
  );
}

export default function MomentumBoard() {
  return (
    <div className="lp-board lp-reveal in">
      {CARDS.map((c) => {
        const up = c.dir === "up";
        const col = up ? "#22c55e" : "#ef4444";
        return (
          <article className="lp-mcard" key={c.name} style={{ "--vc": c.vc } as CSSProperties}>
            <span className="lp-vv">{c.v}</span>
            <h3>{c.name}</h3>
            <div className="lp-mrow">
              <span className={`lp-mom ${up ? "up" : "down"}`}>
                {up ? "↗ Rising" : "↘ Declining"} · {c.pp}
              </span>
              <Spark vals={c.spark} color={col} />
            </div>
          </article>
        );
      })}
    </div>
  );
}
