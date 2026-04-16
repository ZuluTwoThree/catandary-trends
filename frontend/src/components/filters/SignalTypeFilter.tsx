"use client";

import { useRouter, useSearchParams } from "next/navigation";
import {
  PARAM,
  SIGNAL_TYPE_LABELS,
  VALID_SIGNAL_TYPES,
  buildQueryString,
  toggleListValue,
} from "@/lib/filter-params";
import type { TrendSignalType } from "@/lib/types";

export default function SignalTypeFilter({
  active,
}: {
  active: TrendSignalType[];
}) {
  const router = useRouter();
  const searchParams = useSearchParams();

  function handleClick(s: TrendSignalType) {
    const nextList = toggleListValue(active.join(","), s);
    const qs = buildQueryString(searchParams, {
      [PARAM.signal]: nextList,
    });
    router.push(`/trends${qs}`);
  }

  return (
    <fieldset className="border border-border">
      <legend className="font-mono text-[9px] uppercase tracking-[0.22em] text-muted px-2 ml-3">
        Signal Type
      </legend>
      <div className="flex flex-wrap">
        {VALID_SIGNAL_TYPES.map((s, i) => {
          const isActive = active.includes(s);
          const isLast = i === VALID_SIGNAL_TYPES.length - 1;
          return (
            <button
              key={s}
              onClick={() => handleClick(s)}
              aria-pressed={isActive}
              className={`font-mono text-[10px] uppercase tracking-[0.1em] px-3 py-2 transition-colors ${
                !isLast ? "border-r border-border" : ""
              } ${
                isActive
                  ? "bg-accent/10 text-accent"
                  : "text-muted hover:text-paper hover:bg-white/[0.02]"
              }`}
            >
              {SIGNAL_TYPE_LABELS[s]}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}
