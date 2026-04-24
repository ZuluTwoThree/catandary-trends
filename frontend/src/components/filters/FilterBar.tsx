"use client";

import { useState } from "react";
import type { Vertical, PestelDimension, TrendSignalType } from "@/lib/types";
import type { ParsedFilters } from "@/lib/filter-params";
import { countActiveFilters } from "@/lib/filter-params";

import SearchInput from "./SearchInput";
import SortSelect from "./SortSelect";
import ViewModeToggle from "./ViewModeToggle";
import DateRangeChips from "./DateRangeChips";
import VerticalsMultiFilter from "./VerticalsMultiFilter";
import SignalTypeFilter from "./SignalTypeFilter";
import PestelFilter from "./PestelFilter";
import MegaTrendChips from "./MegaTrendChips";
import ScoreSlider from "./ScoreSlider";
import SourceExcludeToggle from "./SourceExcludeToggle";

interface MegaTrendOption {
  key: string;
  name: string;
  count: number;
}
interface SourceOption {
  source_name: string;
  count: number;
}

export default function FilterBar({
  filters,
  verticalCounts,
  megaOptions,
  sourceOptions,
}: {
  filters: ParsedFilters;
  verticalCounts: Record<string, number>;
  megaOptions: MegaTrendOption[];
  sourceOptions: SourceOption[];
}) {
  const [advancedOpen, setAdvancedOpen] = useState(
    // Auto-expand if any advanced filter is active
    !!(
      filters.pestel?.length ||
      filters.signal_types?.length ||
      filters.mega_trend ||
      filters.exclude_sources?.length ||
      (filters.min_trend_score && filters.min_trend_score > 0)
    )
  );

  const advancedCount =
    (filters.pestel?.length ?? 0) +
    (filters.signal_types?.length ?? 0) +
    (filters.mega_trend ? 1 : 0) +
    (filters.exclude_sources?.length ?? 0) +
    (filters.min_trend_score && filters.min_trend_score > 0 ? 1 : 0);

  const total = countActiveFilters(filters);

  return (
    <section
      aria-label="Trend filters"
      className="space-y-3"
    >
      {/* Row 1: search / sort / view */}
      <div className="flex flex-wrap gap-3 items-stretch">
        <div className="flex-1 min-w-[240px]">
          <SearchInput />
        </div>
        <SortSelect />
        <ViewModeToggle />
      </div>

      {/* Row 2: primary filters */}
      <div className="flex flex-wrap gap-3 items-stretch">
        <DateRangeChips />
        <VerticalsMultiFilter
          active={(filters.verticals ?? []) as Vertical[]}
          counts={verticalCounts}
        />
      </div>

      {/* Row 3: advanced toggle */}
      <div className="flex items-center gap-3 pt-1">
        <button
          onClick={() => setAdvancedOpen((o) => !o)}
          aria-expanded={advancedOpen}
          className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.2em] text-muted hover:text-accent transition-colors"
        >
          <span className="w-2 h-[1px] bg-current" aria-hidden="true" />
          Advanced
          <span className="text-border">——</span>
          {advancedCount > 0 && (
            <span className="text-accent tabular-nums">{advancedCount}</span>
          )}
          <span className="text-muted">{advancedOpen ? "▴" : "▾"}</span>
        </button>
        {total > 0 && (
          <span className="ml-auto font-mono text-[10px] uppercase tracking-[0.18em] text-muted">
            <span className="text-accent tabular-nums">{total}</span> active
          </span>
        )}
      </div>

      {/* Row 4: advanced panel (collapsible) */}
      {advancedOpen && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 pt-2 border-t border-dashed border-border">
          <div className="flex flex-wrap gap-3">
            <SignalTypeFilter
              active={(filters.signal_types ?? []) as TrendSignalType[]}
            />
            <PestelFilter
              active={(filters.pestel ?? []) as PestelDimension[]}
            />
            <SourceExcludeToggle
              active={filters.exclude_sources ?? []}
              options={sourceOptions}
            />
          </div>
          <div className="flex flex-col gap-3">
            <MegaTrendChips
              active={filters.mega_trend ?? null}
              options={megaOptions}
            />
            <ScoreSlider />
          </div>
        </div>
      )}
    </section>
  );
}
