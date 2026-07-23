"use client";

import { useRouter, useSearchParams } from "next/navigation";
import {
  CLEAR_ALL_MUTATION,
  buildQueryString,
  getActiveChips,
  type ParsedFilters,
} from "@/lib/filter-params";

/**
 * Horizontal strip of dismissable filter-chips + "Clear all". Renders null
 * when no filters are active so the bar doesn't take vertical space.
 */
export default function ActiveChips({ filters }: { filters: ParsedFilters }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const chips = getActiveChips(filters);

  if (chips.length === 0) return null;

  function apply(mutation: Record<string, string | null>) {
    const qs = buildQueryString(searchParams, mutation);
    router.push(`/trends${qs}`);
  }

  return (
    <div
      role="group"
      className="flex flex-wrap items-center gap-2 py-3 border-y border-border"
      aria-label="Active filters"
    >
      <span className="font-mono text-[9px] uppercase tracking-[0.22em] text-accent shrink-0">
        Active ——
      </span>
      {chips.map((c) => (
        <button
          key={c.key}
          onClick={() => apply(c.mutation)}
          aria-label={`Remove filter: ${c.label}`}
          className="group inline-flex items-center gap-1.5 border border-border hover:border-warn px-2 py-1 font-mono text-[10px] uppercase tracking-[0.08em] text-paper transition-colors"
        >
          <span className="truncate max-w-[24ch]">{c.label}</span>
          <span
            className="text-muted group-hover:text-warn transition-colors"
            aria-hidden="true"
          >
            ×
          </span>
        </button>
      ))}
      <button
        onClick={() => apply(CLEAR_ALL_MUTATION)}
        className="ml-auto font-mono text-[10px] uppercase tracking-[0.15em] text-muted hover:text-warn transition-colors underline underline-offset-4 decoration-dotted"
      >
        Clear all
      </button>
    </div>
  );
}
