"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  PARAM,
  buildQueryString,
  toggleListValue,
} from "@/lib/filter-params";

interface SourceOption {
  source_name: string;
  count: number;
}

/**
 * Dropdown listing top sources — each row toggles its membership in
 * `?exclude=`. Useful for hiding e.g. arXiv research papers when you want
 * business-flavoured signals.
 */
export default function SourceExcludeToggle({
  active,
  options,
}: {
  active: string[];
  options: SourceOption[];
}) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    }
    if (open) document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  function handleToggle(name: string) {
    const nextList = toggleListValue(active.join(","), name);
    const qs = buildQueryString(searchParams, {
      [PARAM.excludeSources]: nextList,
    });
    router.push(`/trends${qs}`);
  }

  /** Escape closes the dropdown and returns focus to the trigger. */
  function handleKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    if (e.key === "Escape" && open) {
      e.stopPropagation();
      setOpen(false);
      triggerRef.current?.focus();
    }
  }

  return (
    <div ref={rootRef} className="relative" onKeyDown={handleKeyDown}>
      <button
        ref={triggerRef}
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex items-stretch border border-border hover:border-rule transition-colors"
      >
        <span className="font-mono text-[9px] uppercase tracking-[0.22em] text-muted px-3 flex items-center border-r border-border whitespace-nowrap">
          Exclude
        </span>
        <span className="font-mono text-[10px] uppercase tracking-[0.1em] px-3 py-2 text-paper flex items-center gap-2">
          Sources
          {active.length > 0 && (
            <span className="font-mono text-[9px] text-accent tabular-nums">
              {active.length}
            </span>
          )}
          <span className="text-muted text-[9px]">{open ? "▴" : "▾"}</span>
        </span>
      </button>

      {open && (
        <div
          role="group"
          aria-label="Exclude sources"
          className="absolute top-full left-0 mt-1 z-20 bg-card border border-border min-w-[280px] max-h-[320px] overflow-y-auto shadow-[0_8px_24px_-12px_rgba(0,0,0,0.6)]"
        >
          {options.length === 0 ? (
            <div className="p-4 font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
              No sources available
            </div>
          ) : (
            options.map((o) => {
              const isExcluded = active.includes(o.source_name);
              return (
                <button
                  key={o.source_name}
                  type="button"
                  onClick={() => handleToggle(o.source_name)}
                  aria-pressed={isExcluded}
                  className={`w-full flex items-center justify-between px-3 py-2 text-left transition-colors border-b border-border last:border-b-0 hover:bg-white/[0.03] ${
                    isExcluded ? "bg-warn/10" : ""
                  }`}
                  style={isExcluded ? { color: "var(--color-warn)" } : undefined}
                >
                  <span className="flex items-center gap-2 min-w-0">
                    <span
                      className={`font-mono text-[10px] w-3 shrink-0 ${
                        isExcluded ? "text-warn" : "text-muted/50"
                      }`}
                      aria-hidden="true"
                    >
                      {isExcluded ? "✕" : "+"}
                    </span>
                    <span className="font-sans text-[12px] truncate">
                      {o.source_name}
                    </span>
                  </span>
                  <span className="font-mono text-[9px] text-muted tabular-nums shrink-0 ml-3">
                    {o.count}
                  </span>
                </button>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}
