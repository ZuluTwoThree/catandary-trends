"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { PARAM, buildQueryString } from "@/lib/filter-params";

export default function ViewModeToggle() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const current = searchParams.get(PARAM.view) ?? "grid";

  function handleClick(v: "grid" | "list") {
    const qs = buildQueryString(
      searchParams,
      { [PARAM.view]: v === "grid" ? null : v },
      { resetPage: true }
    );
    router.push(`/trends${qs}`);
  }

  return (
    <div
      className="flex items-stretch border border-border"
      role="group"
      aria-label="View mode"
    >
      <button
        onClick={() => handleClick("grid")}
        aria-pressed={current === "grid"}
        aria-label="Grid view"
        title="Grid view"
        className={`px-3 py-2 transition-colors ${
          current === "grid"
            ? "bg-white/[0.05] text-accent"
            : "text-muted hover:text-paper"
        }`}
      >
        <GridIcon />
      </button>
      <button
        onClick={() => handleClick("list")}
        aria-pressed={current === "list"}
        aria-label="List view"
        title="List view"
        className={`px-3 py-2 transition-colors border-l border-border ${
          current === "list"
            ? "bg-white/[0.05] text-accent"
            : "text-muted hover:text-paper"
        }`}
      >
        <ListIcon />
      </button>
    </div>
  );
}

function GridIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <rect x="0.5" y="0.5" width="5" height="5" stroke="currentColor" />
      <rect x="8.5" y="0.5" width="5" height="5" stroke="currentColor" />
      <rect x="0.5" y="8.5" width="5" height="5" stroke="currentColor" />
      <rect x="8.5" y="8.5" width="5" height="5" stroke="currentColor" />
    </svg>
  );
}

function ListIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <line x1="0" y1="2" x2="14" y2="2" stroke="currentColor" />
      <line x1="0" y1="7" x2="14" y2="7" stroke="currentColor" />
      <line x1="0" y1="12" x2="14" y2="12" stroke="currentColor" />
    </svg>
  );
}
