"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { VERTICALS, type Vertical } from "@/lib/types";

export default function VerticalFilter({
  active,
  counts,
}: {
  active: Vertical | null;
  counts: Record<string, number>;
}) {
  const router = useRouter();
  const searchParams = useSearchParams();

  function handleClick(vertical: Vertical | null) {
    const params = new URLSearchParams(searchParams.toString());
    if (vertical) {
      params.set("vertical", vertical);
    } else {
      params.delete("vertical");
    }
    // Reset page when changing vertical
    params.delete("page");
    router.push(`/trends?${params.toString()}`);
  }

  const total = Object.values(counts).reduce((a, b) => a + b, 0);

  return (
    <div className="flex flex-wrap items-stretch border border-border">
      <div className="font-mono text-[9px] uppercase tracking-[0.18em] text-muted px-4 py-3 border-r border-border flex items-center whitespace-nowrap">
        Vertical ——
      </div>
      <button
        onClick={() => handleClick(null)}
        className={`font-mono text-[10px] uppercase tracking-[0.08em] px-4 py-3 border-r border-border flex items-center gap-2 transition-colors ${
          active === null
            ? "text-accent bg-accent/5"
            : "text-muted hover:text-paper hover:bg-white/[0.02]"
        }`}
      >
        <span>All</span>
        <span className="text-[9px] opacity-60">{total}</span>
      </button>
      {VERTICALS.map((v, idx) => {
        const count = counts[v.id] ?? 0;
        if (count === 0) return null;
        const isActive = active === v.id;
        const isLast = idx === VERTICALS.length - 1;
        return (
          <button
            key={v.id}
            onClick={() => handleClick(v.id)}
            className={`font-mono text-[10px] uppercase tracking-[0.08em] px-4 py-3 flex items-center gap-2 transition-colors ${
              !isLast ? "border-r border-border" : ""
            } ${
              isActive
                ? "bg-accent/5"
                : "text-muted hover:text-paper hover:bg-white/[0.02]"
            }`}
            style={isActive ? { color: v.color } : undefined}
          >
            <span
              className="inline-block w-[8px] h-[3px]"
              style={{ backgroundColor: v.color }}
              aria-hidden="true"
            />
            <span>{v.code}</span>
            <span className="text-[9px] opacity-60">{count}</span>
          </button>
        );
      })}
    </div>
  );
}
