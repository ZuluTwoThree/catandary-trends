import { getVerticalInfo, type Vertical } from "@/lib/types";

export default function VerticalBadge({
  vertical,
  size = "sm",
}: {
  vertical: Vertical;
  size?: "sm" | "md";
}) {
  const info = getVerticalInfo(vertical);

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md font-medium ${
        size === "md" ? "px-2.5 py-1 text-sm" : "px-2 py-0.5 text-xs"
      }`}
      style={{
        backgroundColor: `${info.color}15`,
        color: info.color,
        border: `1px solid ${info.color}30`,
      }}
    >
      <span>{info.icon}</span>
      <span>{info.label}</span>
    </span>
  );
}
