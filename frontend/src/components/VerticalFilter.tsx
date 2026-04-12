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
    router.push(`/trends?${params.toString()}`);
  }

  const total = Object.values(counts).reduce((a, b) => a + b, 0);

  return (
    <div className="flex flex-wrap gap-2">
      <button
        onClick={() => handleClick(null)}
        className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
          active === null
            ? "bg-accent text-background"
            : "bg-card border border-border text-muted hover:text-foreground hover:border-accent/30"
        }`}
      >
        All
        <span className="ml-1.5 text-xs opacity-60">{total}</span>
      </button>
      {VERTICALS.map((v) => {
        const count = counts[v.id] ?? 0;
        if (count === 0) return null;
        const isActive = active === v.id;
        return (
          <button
            key={v.id}
            onClick={() => handleClick(v.id)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
              isActive
                ? "text-background"
                : "bg-card border border-border text-muted hover:text-foreground hover:border-accent/30"
            }`}
            style={
              isActive
                ? { backgroundColor: v.color }
                : undefined
            }
          >
            <span className="mr-1">{v.icon}</span>
            {v.label}
            <span className="ml-1.5 text-xs opacity-60">{count}</span>
          </button>
        );
      })}
    </div>
  );
}
