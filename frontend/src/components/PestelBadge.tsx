import { getPestelInfo, type PestelDimension } from "@/lib/types";

export default function PestelBadge({
  dimension,
}: {
  dimension: PestelDimension;
}) {
  const info = getPestelInfo(dimension);

  return (
    <span
      className="font-mono text-[9px] uppercase tracking-[0.08em] px-1.5 py-0.5 border"
      style={{
        color: info.color,
        borderColor: `${info.color}55`,
        backgroundColor: `${info.color}10`,
      }}
      title={info.label}
    >
      {info.label}
    </span>
  );
}
