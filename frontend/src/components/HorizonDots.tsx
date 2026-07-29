import { DIMENSION_META, HORIZON_META, type Horizon } from "@/lib/radar-shared";

/**
 * Horizon profile as three small dots (technology · regulatory · market) for
 * trend cards and article headers.
 *
 * A single trend is NOT a technology field, so the profile is inherited from the
 * radar field the trend belongs to. The field name therefore has to travel with
 * the badge — without it the dots would claim a precision they do not have.
 * Cards whose trend is in no radar field get no badge at all, rather than a row
 * of "unknown" noise.
 */

const ORDER = ["technology", "regulatory", "market"] as const;
const SHORT: Record<string, string> = {
  technology: "T",
  regulatory: "R",
  market: "M",
};

export default function HorizonDots({
  scopeLabel,
  cells,
  region,
}: {
  scopeLabel: string;
  cells: { dimension: string; horizon: Horizon }[];
  region?: string;
}) {
  const byDim = new Map(cells.map((c) => [c.dimension, c.horizon]));
  const present = ORDER.filter((d) => byDim.has(d));
  if (!present.length) return null;

  const summary = present
    .map(
      (d) =>
        `${DIMENSION_META[d]?.label ?? d} ${byDim.get(d)} (${
          HORIZON_META[byDim.get(d)!].action
        })`
    )
    .join(", ");

  return (
    <span
      className="inline-flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-[0.12em] text-muted"
      title={`${scopeLabel}${region ? ` · ${region}` : ""} — ${summary}`}
    >
      <span className="opacity-70">{scopeLabel}</span>
      <span className="inline-flex items-center gap-1">
        {present.map((d) => {
          const h = byDim.get(d)!;
          return (
            <span key={d} className="inline-flex items-center gap-[2px]">
              <span
                aria-hidden="true"
                style={{
                  display: "inline-block",
                  width: 6,
                  height: 6,
                  borderRadius: "50%",
                  // H1 filled, H2 half, H3 outline: the fill level reads as
                  // "how close to acting" without needing a legend.
                  background:
                    h === "H1"
                      ? HORIZON_META[h].color
                      : h === "H2"
                        ? `linear-gradient(90deg, ${HORIZON_META[h].color} 50%, transparent 50%)`
                        : "transparent",
                  border: `1px solid ${HORIZON_META[h].color}`,
                }}
              />
              <span style={{ color: HORIZON_META[h].color }}>
                {SHORT[d]}
                {h.slice(1)}
              </span>
            </span>
          );
        })}
      </span>
      <span className="sr-only">
        {scopeLabel}: {summary}
      </span>
    </span>
  );
}
