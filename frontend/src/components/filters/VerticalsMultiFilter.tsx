"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { VERTICALS, type Vertical } from "@/lib/types";
import {
  PARAM,
  buildQueryString,
  toggleListValue,
} from "@/lib/filter-params";

/**
 * Multi-select vertical filter — each chip toggles its membership in `?v=`.
 * Counts shown reflect the *current filtered scope minus this dimension* so
 * users don't land on 0 when toggling between verticals. Computed by the
 * parent page and passed in as `counts`.
 */
export default function VerticalsMultiFilter({
  active,
  counts,
}: {
  active: Vertical[];
  counts: Record<string, number>;
}) {
  const router = useRouter();
  const searchParams = useSearchParams();

  function handleClick(v: Vertical) {
    const nextList = toggleListValue(active.join(","), v);
    const qs = buildQueryString(searchParams, {
      [PARAM.verticals]: nextList,
    });
    router.push(`/trends${qs}`);
  }

  function handleAll() {
    const qs = buildQueryString(searchParams, {
      [PARAM.verticals]: null,
    });
    router.push(`/trends${qs}`);
  }

  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  const allActive = active.length === 0;

  return (
    <div className="flex flex-wrap items-stretch border border-border">
      <div className="font-mono text-[9px] uppercase tracking-[0.22em] text-muted px-4 flex items-center border-r border-border whitespace-nowrap">
        Vertical ——
      </div>
      <button
        onClick={handleAll}
        aria-pressed={allActive}
        className={`font-mono text-[10px] uppercase tracking-[0.1em] px-4 py-2 border-r border-border flex items-center gap-2 transition-colors ${
          allActive
            ? "text-accent bg-accent/5"
            : "text-muted hover:text-paper hover:bg-white/[0.02]"
        }`}
      >
        <span>All</span>
        <span className="text-[9px] opacity-60 tabular-nums">{total}</span>
      </button>
      {VERTICALS.map((v, idx) => {
        const count = counts[v.id] ?? 0;
        const isActive = active.includes(v.id);
        const isLast = idx === VERTICALS.length - 1;
        // Hide zero-count chips only when nothing is filtered in that dimension
        if (count === 0 && !isActive) return null;
        return (
          <button
            key={v.id}
            onClick={() => handleClick(v.id)}
            aria-pressed={isActive}
            className={`font-mono text-[10px] uppercase tracking-[0.1em] px-4 py-2 flex items-center gap-2 transition-colors ${
              !isLast ? "border-r border-border" : ""
            } ${
              isActive ? "bg-white/[0.04]" : "text-muted hover:text-paper hover:bg-white/[0.02]"
            }`}
            style={isActive ? { color: v.color } : undefined}
          >
            <span
              className="inline-block w-[8px] h-[3px]"
              style={{ backgroundColor: v.color, opacity: isActive ? 1 : 0.5 }}
              aria-hidden="true"
            />
            <span>{v.code}</span>
            <span className="text-[9px] opacity-60 tabular-nums">{count}</span>
          </button>
        );
      })}
    </div>
  );
}
