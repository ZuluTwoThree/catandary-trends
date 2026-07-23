"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { FORESIGHT_NAV, isForesightPath } from "@/lib/nav";

/**
 * Desktop disclosure menu grouping the Foresight tool suite under one nav
 * entry (ONB-12 / ARCH-18: five sub-pages used to sit flat in the top bar).
 * Closes on Escape, outside click and navigation; trigger reflects the
 * active section.
 */
export default function ForesightMenu() {
  // Menu is "open" only for the pathname it was opened on — navigating away
  // closes it by derivation, no state-sync effect needed.
  const [openedOn, setOpenedOn] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  const pathname = usePathname();
  const sectionActive = isForesightPath(pathname);
  const open = openedOn === pathname;
  const setOpen = (v: boolean) => setOpenedOn(v ? pathname : null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpenedOn(null);
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpenedOn(null);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onClick);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onClick);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-expanded={open}
        aria-haspopup="true"
        onClick={() => setOpen(!open)}
        className={`font-mono text-[11px] uppercase tracking-[0.14em] px-3 py-1.5 transition-colors inline-flex items-center gap-1.5 ${
          sectionActive ? "text-paper border-b border-accent" : "text-muted hover:text-paper"
        }`}
      >
        Foresight
        <span aria-hidden="true" className="text-[8px] translate-y-[1px]">
          {open ? "▲" : "▼"}
        </span>
      </button>
      {open && (
        <div className="absolute left-0 top-full mt-1 z-50 min-w-44 border border-border bg-card shadow-lg py-1">
          {FORESIGHT_NAV.map((item) => {
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`block px-4 py-2.5 font-mono text-[11px] uppercase tracking-[0.14em] transition-colors ${
                  active
                    ? "text-accent"
                    : "text-muted hover:text-paper hover:bg-card-hover"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
