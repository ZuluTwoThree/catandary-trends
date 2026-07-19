"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useRef, useState } from "react";
import { PARAM, buildQueryString } from "@/lib/filter-params";

/**
 * FTS5-backed search box. 300ms debounce, pushes to `?q=` on commit.
 */
export default function SearchInput() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const paramValue = searchParams.get(PARAM.search) ?? "";
  const [value, setValue] = useState(paramValue);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Keep local state in sync if the URL changes externally (e.g. chip removal).
  // Adjust-state-during-render (React's sanctioned pattern) instead of a
  // setState-in-effect: track the last URL value and reset only when it changes.
  const [lastParam, setLastParam] = useState(paramValue);
  if (paramValue !== lastParam) {
    setLastParam(paramValue);
    setValue(paramValue);
  }

  function commit(v: string) {
    const qs = buildQueryString(searchParams, {
      [PARAM.search]: v.trim() || null,
    });
    router.push(`/trends${qs}`);
  }

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const v = e.target.value;
    setValue(v);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => commit(v), 300);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      commit(value);
    } else if (e.key === "Escape") {
      setValue("");
      commit("");
    }
  }

  return (
    <div
      role="search"
      className="flex items-stretch border border-border bg-background/40 focus-within:border-accent/70 transition-colors"
    >
      <span
        className="font-mono text-[9px] uppercase tracking-[0.22em] text-accent px-3 flex items-center border-r border-border select-none"
        aria-hidden="true"
      >
        ?&nbsp;Query
      </span>
      <input
        type="search"
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        placeholder="e.g. longevity microbiome"
        aria-label="Search trends"
        className="flex-1 bg-transparent font-mono text-[11px] text-paper placeholder:text-muted/60 px-3 py-2 outline-none min-w-0"
      />
      {value && (
        <button
          onClick={() => {
            setValue("");
            commit("");
          }}
          className="px-3 font-mono text-[10px] text-muted hover:text-accent transition-colors border-l border-border"
          aria-label="Clear search"
        >
          ×
        </button>
      )}
    </div>
  );
}
