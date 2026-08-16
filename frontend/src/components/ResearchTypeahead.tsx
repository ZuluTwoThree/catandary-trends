"use client";

import { useEffect, useRef, useState } from "react";
import { typeaheadContext, applyTypeahead, type TypeaheadContext } from "@/lib/research-search";

/** Suchfeld mit Operator-Typeahead (#83): tippt der Nutzer author:/
 *  institution:/journal:/funder:, erscheinen Vorschläge — journal/funder/
 *  institution aus lokalen Distinct-Aggregaten, author via OpenAlex-
 *  Autocomplete (Super Pro; `authorEnabled` kommt vom Server). Auswahl
 *  ersetzt den Operator-Wert gequotet, der übrige Text bleibt stehen. */
export default function ResearchTypeahead({
  name, defaultValue, placeholder, className, ariaLabel, authorEnabled,
}: {
  name: string;
  defaultValue: string;
  placeholder: string;
  className: string;
  ariaLabel: string;
  authorEnabled: boolean;
}) {
  const [value, setValue] = useState(defaultValue);
  const [items, setItems] = useState<{ v: string; n: number | null }[]>([]);
  const [ctx, setCtx] = useState<TypeaheadContext | null>(null);
  const [open, setOpen] = useState(false);
  const [hi, setHi] = useState(-1);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abort = useRef<AbortController | null>(null);

  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    const c = typeaheadContext(value);
    if (!c || c.value.length < 2 || (c.kind === "author" && !authorEnabled)) {
      setOpen(false); setCtx(null);
      return;
    }
    timer.current = setTimeout(async () => {
      abort.current?.abort();
      abort.current = new AbortController();
      try {
        const r = await fetch(
          `/trends/foresight/research/suggest?kind=${c.kind}&q=${encodeURIComponent(c.value)}`,
          { signal: abort.current.signal });
        const j = (await r.json()) as { s: { v: string; n: number | null }[] };
        setItems(j.s ?? []); setCtx(c); setHi(-1); setOpen((j.s ?? []).length > 0);
      } catch {
        /* Tipp-Abbruch/Netzfehler: Dropdown bleibt einfach zu */
      }
    }, 250);
    return () => { if (timer.current) clearTimeout(timer.current); };
  }, [value, authorEnabled]);

  const pick = (v: string) => {
    if (ctx) setValue(applyTypeahead(value, ctx, v));
    setOpen(false); setHi(-1);
  };

  return (
    <div className="relative flex-1 min-w-[220px]">
      <input
        type="search"
        name={name}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={(e) => {
          if (!open) return;
          if (e.key === "ArrowDown") { e.preventDefault(); setHi((h) => Math.min(h + 1, items.length - 1)); }
          else if (e.key === "ArrowUp") { e.preventDefault(); setHi((h) => Math.max(h - 1, -1)); }
          else if (e.key === "Enter" && hi >= 0) { e.preventDefault(); pick(items[hi].v); }
          else if (e.key === "Escape") { setOpen(false); setHi(-1); }
        }}
        placeholder={placeholder}
        className={`w-full ${className}`}
        aria-label={ariaLabel}
        aria-expanded={open}
        aria-autocomplete="list"
        autoComplete="off"
      />
      {open && (
        <ul className="absolute z-30 left-0 right-0 top-full mt-1 bg-card border border-border-strong shadow-xl max-h-72 overflow-y-auto">
          {items.map((it, i) => (
            <li key={it.v}>
              <button
                type="button"
                onMouseDown={(e) => { e.preventDefault(); pick(it.v); }}
                onMouseEnter={() => setHi(i)}
                className={`w-full text-left px-4 py-2 font-sans text-sm flex justify-between gap-3 ${
                  i === hi ? "bg-accent text-ink" : "text-paper hover:bg-accent hover:text-ink"}`}
              >
                <span className="truncate">{it.v}</span>
                {it.n !== null && (
                  <span className="font-mono text-[10px] shrink-0 self-center opacity-70">
                    {it.n.toLocaleString("en-US")}
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
