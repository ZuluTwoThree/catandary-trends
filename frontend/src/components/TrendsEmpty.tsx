"use client";

import { useRouter, useSearchParams } from "next/navigation";
import {
  CLEAR_ALL_MUTATION,
  buildQueryString,
  getActiveChips,
  type ParsedFilters,
} from "@/lib/filter-params";

export default function TrendsEmpty({
  filters,
}: {
  filters?: ParsedFilters;
}) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const chips = filters ? getActiveChips(filters) : [];
  const hasFilters = chips.length > 0;

  function clearAll() {
    const qs = buildQueryString(searchParams, CLEAR_ALL_MUTATION);
    router.push(`/trends${qs}`);
  }

  return (
    <div className="border border-border border-dashed px-8 py-16 text-center">
      <div className="font-mono text-[9px] uppercase tracking-[0.22em] text-muted mb-4">
        —— 404 · No signals
      </div>

      <h2 className="font-display text-[32px] leading-[1.1] text-paper mb-4">
        {hasFilters ? (
          <>
            No trends match <span className="italic text-accent">these filters</span>.
          </>
        ) : (
          <>
            The signal channel is <span className="italic">quiet</span>.
          </>
        )}
      </h2>

      <p className="font-sans text-[14px] text-muted max-w-md mx-auto leading-[1.55] mb-8">
        {hasFilters
          ? "Try loosening one of the constraints below, or clear all filters to see the full stream."
          : "The pipeline is running — new signals will appear here once classified."}
      </p>

      {hasFilters && (
        <>
          <div className="flex flex-wrap justify-center gap-2 mb-8 max-w-2xl mx-auto">
            {chips.map((c) => (
              <span
                key={c.key}
                className="font-mono text-[10px] uppercase tracking-[0.08em] text-muted border border-border px-2 py-1 inline-flex items-center gap-1.5"
              >
                <span>{c.label}</span>
              </span>
            ))}
          </div>
          <button
            onClick={clearAll}
            className="font-mono text-[10px] uppercase tracking-[0.18em] bg-accent text-ink px-5 py-3 hover:bg-accent-deep transition-colors"
            style={{
              backgroundColor: "var(--color-accent)",
              color: "var(--color-background)",
            }}
          >
            Clear all filters →
          </button>
        </>
      )}
    </div>
  );
}
