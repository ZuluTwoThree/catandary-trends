"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { PESTEL, type PestelDimension } from "@/lib/types";
import {
  PARAM,
  buildQueryString,
  toggleListValue,
} from "@/lib/filter-params";

/**
 * PESTEL = Political / Economic / Social / Technological / Environmental / Legal.
 * Renders 6 single-letter toggles, each colour-coded per dimension.
 */
export default function PestelFilter({
  active,
}: {
  active: PestelDimension[];
}) {
  const router = useRouter();
  const searchParams = useSearchParams();

  function handleClick(p: PestelDimension) {
    const nextList = toggleListValue(active.join(","), p);
    const qs = buildQueryString(searchParams, {
      [PARAM.pestel]: nextList,
    });
    router.push(`/trends${qs}`);
  }

  return (
    <div className="flex items-stretch border border-border">
      <span className="font-mono text-[9px] uppercase tracking-[0.22em] text-muted px-3 flex items-center border-r border-border whitespace-nowrap">
        PESTEL
      </span>
      {PESTEL.map((p, i) => {
        const isActive = active.includes(p.id);
        const isLast = i === PESTEL.length - 1;
        return (
          <button
            key={p.id}
            onClick={() => handleClick(p.id)}
            aria-pressed={isActive}
            aria-label={`Toggle ${p.label}`}
            title={p.label}
            className={`font-mono text-[12px] font-semibold px-3 py-2 transition-colors min-w-[40px] ${
              !isLast ? "border-r border-border" : ""
            } ${isActive ? "bg-white/[0.05]" : "hover:bg-white/[0.02]"}`}
            style={{
              color: isActive ? p.color : "var(--color-muted)",
            }}
          >
            {p.id}
          </button>
        );
      })}
    </div>
  );
}
