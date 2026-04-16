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
      className={`inline-flex items-center gap-2 font-mono uppercase tracking-[0.12em] border ${
        size === "md" ? "px-2.5 py-1 text-[11px]" : "px-2 py-0.5 text-[10px]"
      }`}
      style={{
        backgroundColor: `${info.color}12`,
        color: info.color,
        borderColor: `${info.color}55`,
      }}
    >
      <span
        className={size === "md" ? "inline-block w-2.5 h-[3px]" : "inline-block w-2 h-[3px]"}
        style={{ backgroundColor: info.color }}
        aria-hidden="true"
      />
      <span>{info.code}</span>
      <span className="text-muted/70 font-sans normal-case tracking-normal">
        {info.label}
      </span>
    </span>
  );
}
