"use client";

import { useRouter, useSearchParams } from "next/navigation";
import {
  DATE_RANGE_LABELS,
  PARAM,
  VALID_DATE_RANGE,
  buildQueryString,
} from "@/lib/filter-params";

export default function DateRangeChips() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const current = searchParams.get(PARAM.dateRange) ?? "all";

  function handleClick(v: string) {
    const qs = buildQueryString(searchParams, {
      [PARAM.dateRange]: v === "all" ? null : v,
    });
    router.push(`/trends${qs}`);
  }

  return (
    <div
      className="flex items-stretch border border-border"
      role="group"
      aria-label="Date range"
    >
      <span
        className="font-mono text-[9px] uppercase tracking-[0.22em] text-muted px-3 flex items-center border-r border-border select-none"
        aria-hidden="true"
      >
        Since
      </span>
      {VALID_DATE_RANGE.map((r, i) => {
        const isActive = current === r;
        const isLast = i === VALID_DATE_RANGE.length - 1;
        return (
          <button
            key={r}
            onClick={() => handleClick(r)}
            aria-pressed={isActive}
            className={`font-mono text-[10px] uppercase tracking-[0.12em] px-3 py-2 transition-colors ${
              !isLast ? "border-r border-border" : ""
            } ${
              isActive
                ? "bg-accent text-ink font-semibold"
                : "text-muted hover:text-paper hover:bg-white/[0.02]"
            }`}
            style={
              isActive
                ? { backgroundColor: "var(--color-accent)", color: "var(--color-background)" }
                : undefined
            }
          >
            {DATE_RANGE_LABELS[r]}
          </button>
        );
      })}
    </div>
  );
}
