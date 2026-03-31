import { getPestelInfo, type PestelDimension } from "@/lib/types";

export default function PestelBadge({ dimension }: { dimension: PestelDimension }) {
  const info = getPestelInfo(dimension);

  return (
    <span
      className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium"
      style={{
        backgroundColor: `${info.color}20`,
        color: info.color,
        border: `1px solid ${info.color}40`,
      }}
    >
      {info.label}
    </span>
  );
}
