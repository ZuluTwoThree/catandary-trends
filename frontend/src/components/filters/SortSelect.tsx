"use client";

import { useRouter, useSearchParams } from "next/navigation";
import {
  PARAM,
  SORT_LABELS,
  VALID_SORT_BY,
  buildQueryString,
  type SortOption,
} from "@/lib/filter-params";

export default function SortSelect() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const rawSort = searchParams.get(PARAM.sort) ?? "date_desc";
  // Unknown/legacy sort keys (e.g. old `source_date_desc` links) fall back
  // to the default so the select always shows a real option.
  const current: SortOption = (VALID_SORT_BY as readonly string[]).includes(rawSort)
    ? (rawSort as SortOption)
    : "date_desc";

  function handleChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const v = e.target.value;
    const qs = buildQueryString(searchParams, {
      [PARAM.sort]: v === "date_desc" ? null : v,
    });
    router.push(`/trends${qs}`);
  }

  return (
    <label className="flex items-stretch border border-border group focus-within:border-accent/70 transition-colors">
      <span
        className="font-mono text-[9px] uppercase tracking-[0.22em] text-muted px-3 flex items-center border-r border-border select-none"
        aria-hidden="true"
      >
        Sort ↕
      </span>
      <select
        value={current}
        onChange={handleChange}
        aria-label="Sort by"
        className="bg-transparent font-mono text-[10px] uppercase tracking-[0.12em] text-paper px-3 py-2 appearance-none cursor-pointer pr-8"
        style={{
          backgroundImage:
            "linear-gradient(45deg, transparent 50%, var(--color-muted) 50%), linear-gradient(135deg, var(--color-muted) 50%, transparent 50%)",
          backgroundPosition:
            "calc(100% - 14px) 50%, calc(100% - 10px) 50%",
          backgroundSize: "4px 4px",
          backgroundRepeat: "no-repeat",
        }}
      >
        {VALID_SORT_BY.map((s) => (
          <option
            key={s}
            value={s}
            className="bg-card text-paper font-mono text-[11px]"
          >
            {SORT_LABELS[s]}
          </option>
        ))}
      </select>
    </label>
  );
}
