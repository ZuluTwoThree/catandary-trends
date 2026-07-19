"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useRef, useState } from "react";
import { PARAM, buildQueryString } from "@/lib/filter-params";

/**
 * Min-score slider (0–100). Debounced to avoid flooding the router on drag.
 */
export default function ScoreSlider() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const paramValue = parseInt(searchParams.get(PARAM.minScore) ?? "0", 10) || 0;
  const [value, setValue] = useState(paramValue);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Sync with the URL via adjust-state-during-render (not setState-in-effect):
  // reset local state only when the external param actually changes.
  const [lastParam, setLastParam] = useState(paramValue);
  if (paramValue !== lastParam) {
    setLastParam(paramValue);
    setValue(paramValue);
  }

  function commit(v: number) {
    const qs = buildQueryString(searchParams, {
      [PARAM.minScore]: v > 0 ? String(v) : null,
    });
    router.push(`/trends${qs}`);
  }

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const v = parseInt(e.target.value, 10);
    setValue(v);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => commit(v), 250);
  }

  return (
    <div className="border border-border p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="font-mono text-[9px] uppercase tracking-[0.22em] text-muted">
          Min Score
        </span>
        <span className="font-mono text-[11px] text-accent tabular-nums">
          ≥ {value}
        </span>
      </div>
      <input
        type="range"
        min={0}
        max={100}
        step={5}
        value={value}
        onChange={handleChange}
        aria-label="Minimum trend score"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={value}
        className="score-slider w-full"
      />
      <div className="flex justify-between mt-1 font-mono text-[9px] text-muted/60 tabular-nums">
        <span>0</span>
        <span>50</span>
        <span>100</span>
      </div>
      <style jsx>{`
        .score-slider {
          -webkit-appearance: none;
          appearance: none;
          height: 3px;
          background: linear-gradient(
            to right,
            var(--color-accent) 0%,
            var(--color-accent) ${value}%,
            var(--color-border) ${value}%,
            var(--color-border) 100%
          );
          outline: none;
          cursor: pointer;
        }
        .score-slider::-webkit-slider-thumb {
          -webkit-appearance: none;
          appearance: none;
          width: 14px;
          height: 14px;
          background: var(--color-paper);
          border: 2px solid var(--color-accent);
          border-radius: 0;
          cursor: grab;
        }
        .score-slider::-moz-range-thumb {
          width: 14px;
          height: 14px;
          background: var(--color-paper);
          border: 2px solid var(--color-accent);
          border-radius: 0;
          cursor: grab;
        }
      `}</style>
    </div>
  );
}
