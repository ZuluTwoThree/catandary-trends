"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { PARAM, buildQueryString } from "@/lib/filter-params";

interface MegaTrendOption {
  key: string;
  name: string;
  count: number;
}

/**
 * Mega-trend chip filter. Collapses to the top 6 by count with an "expand"
 * button revealing the rest. Single-select (mega_trend is a 1:N taxonomy,
 * picking two at once makes no sense in the data model).
 */
export default function MegaTrendChips({
  active,
  options,
}: {
  active: string | null;
  options: MegaTrendOption[];
}) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [expanded, setExpanded] = useState(false);

  const visible = expanded ? options : options.slice(0, 6);

  function handleClick(key: string) {
    const next = active === key ? null : key;
    const qs = buildQueryString(searchParams, {
      [PARAM.mega]: next,
    });
    router.push(`/trends${qs}`);
  }

  if (options.length === 0) return null;

  return (
    <div className="border border-border p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="font-mono text-[9px] uppercase tracking-[0.22em] text-muted">
          Theme
        </span>
        {options.length > 6 && (
          <button
            onClick={() => setExpanded((e) => !e)}
            className="font-mono text-[9px] uppercase tracking-[0.18em] text-muted hover:text-accent transition-colors"
          >
            {expanded ? "Collapse ↑" : `+${options.length - 6} more ↓`}
          </button>
        )}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {visible.map((m) => {
          const isActive = active === m.key;
          return (
            <button
              key={m.key}
              onClick={() => handleClick(m.key)}
              aria-pressed={isActive}
              className={`font-mono text-[10px] uppercase tracking-[0.08em] px-2.5 py-1.5 border transition-colors inline-flex items-center gap-2 ${
                isActive
                  ? "border-accent text-accent bg-accent/5"
                  : "border-border text-muted hover:text-paper hover:border-rule"
              }`}
            >
              <span className="truncate max-w-[22ch]">{m.name}</span>
              <span className="text-[9px] opacity-60 tabular-nums">{m.count}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
