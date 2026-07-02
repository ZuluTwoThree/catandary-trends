"use client";

import { useEffect, useState } from "react";

interface NavItem {
  href: string;
  label: string;
  external?: boolean;
}

/**
 * Mobile navigation (< md). The desktop nav is `hidden md:inline`, which left
 * the strongest pages (Foresight, Clusters, Mega Trends) unreachable on phones.
 * This adds a hamburger + full-screen drawer with every nav target.
 */
export default function MobileNav({ items }: { items: NavItem[] }) {
  const [open, setOpen] = useState(false);

  // Lock body scroll while the drawer is open; close on Escape.
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="md:hidden">
      <button
        type="button"
        aria-label={open ? "Close menu" : "Open menu"}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex flex-col justify-center gap-[5px] w-11 h-11 -mr-2 items-center text-paper"
      >
        <span
          className={`block h-[2px] w-6 bg-current transition-transform duration-200 ${
            open ? "translate-y-[7px] rotate-45" : ""
          }`}
        />
        <span
          className={`block h-[2px] w-6 bg-current transition-opacity duration-200 ${
            open ? "opacity-0" : ""
          }`}
        />
        <span
          className={`block h-[2px] w-6 bg-current transition-transform duration-200 ${
            open ? "-translate-y-[7px] -rotate-45" : ""
          }`}
        />
      </button>

      {open && (
        <div className="fixed inset-0 z-50 bg-background/98 backdrop-blur-sm">
          <div className="flex items-center justify-between h-16 px-6 border-b border-border">
            <span className="font-display text-[22px] tracking-tight text-paper">
              Catandary<span className="text-accent">.</span>
            </span>
            <button
              type="button"
              aria-label="Close menu"
              onClick={() => setOpen(false)}
              className="w-11 h-11 -mr-2 flex items-center justify-center text-paper text-2xl leading-none"
            >
              ×
            </button>
          </div>
          <nav className="flex flex-col px-6 py-4">
            {items.map((item) => (
              <a
                key={item.href}
                href={item.href}
                onClick={() => setOpen(false)}
                {...(item.external
                  ? { target: "_blank", rel: "noopener noreferrer" }
                  : {})}
                className="font-mono text-[13px] uppercase tracking-[0.14em] text-muted hover:text-paper py-4 border-b border-border/60 transition-colors"
              >
                {item.label}
              </a>
            ))}
            <a
              href="/trends/newsletter"
              onClick={() => setOpen(false)}
              className="mt-6 text-center font-mono text-[12px] uppercase tracking-[0.14em] text-accent px-3 py-3 border border-accent bg-accent/5 hover:bg-accent/15 transition-colors"
            >
              Newsletter
            </a>
          </nav>
        </div>
      )}
    </div>
  );
}
