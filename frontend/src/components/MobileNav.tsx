"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { PRIMARY_NAV, FORESIGHT_NAV, PLANS_NAV } from "@/lib/nav";

/**
 * Mobile navigation (< lg): hamburger + full-screen drawer with the grouped
 * nav (Explore / Foresight / Account). Dialog semantics with a focus trap:
 * focus moves into the drawer on open and returns to the hamburger on close
 * (A11Y-04).
 */
export default function MobileNav({
  authEnabled,
  signedIn,
}: {
  authEnabled: boolean;
  signedIn: boolean;
}) {
  // Drawer is "open" only for the pathname it was opened on — navigating
  // away closes it by derivation, no state-sync effect needed.
  const [openedOn, setOpenedOn] = useState<string | null>(null);
  const pathname = usePathname();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const drawerRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const open = openedOn === pathname;
  const setOpen = (v: boolean) => setOpenedOn(v ? pathname : null);

  // Lock body scroll, trap focus, close on Escape, restore focus on close.
  useEffect(() => {
    if (!open) return;
    const trigger = triggerRef.current;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpenedOn(null);
        return;
      }
      if (e.key !== "Tab" || !drawerRef.current) return;
      const focusables = drawerRef.current.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled])'
      );
      if (focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener("keydown", onKey);
      trigger?.focus();
    };
  }, [open]);

  const itemClass = (href: string) =>
    `py-3.5 border-b border-border/60 font-mono text-[13px] uppercase tracking-[0.14em] transition-colors ${
      pathname === href ? "text-accent" : "text-muted hover:text-paper"
    }`;

  const groupLabel =
    "pt-6 pb-2 font-mono text-[10px] uppercase tracking-[0.22em] text-accent";

  return (
    <div className="lg:hidden">
      <button
        ref={triggerRef}
        type="button"
        aria-label={open ? "Close menu" : "Open menu"}
        aria-expanded={open}
        onClick={() => setOpen(!open)}
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
        <div
          ref={drawerRef}
          role="dialog"
          aria-modal="true"
          aria-label="Navigation"
          className="fixed inset-0 z-50 bg-background/98 backdrop-blur-sm overflow-y-auto"
        >
          <div className="flex items-center justify-between h-16 px-6 border-b border-border">
            <span className="font-display text-[22px] tracking-tight text-paper">
              Catandary<span className="text-accent">.</span>
            </span>
            <button
              ref={closeRef}
              type="button"
              aria-label="Close menu"
              onClick={() => setOpen(false)}
              className="w-11 h-11 -mr-2 flex items-center justify-center text-paper text-2xl leading-none"
            >
              ×
            </button>
          </div>
          <nav className="flex flex-col px-6 pb-10" aria-label="Mobile">
            <div className={groupLabel}>Explore</div>
            {PRIMARY_NAV.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                aria-current={pathname === item.href ? "page" : undefined}
                className={itemClass(item.href)}
              >
                {item.label}
              </Link>
            ))}

            <div className={groupLabel}>Foresight</div>
            {FORESIGHT_NAV.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                aria-current={pathname === item.href ? "page" : undefined}
                className={itemClass(item.href)}
              >
                {item.label}
              </Link>
            ))}

            <div className={groupLabel}>Account</div>
            <Link href={PLANS_NAV.href} className={itemClass(PLANS_NAV.href)}>
              {PLANS_NAV.label}
            </Link>
            {authEnabled && (
              <Link
                href={signedIn ? "/account" : "/account/signin"}
                className={itemClass(signedIn ? "/account" : "/account/signin")}
              >
                {signedIn ? "Account" : "Sign in"}
              </Link>
            )}

            <Link
              href="/trends/newsletter"
              className="mt-8 text-center font-mono text-[12px] uppercase tracking-[0.14em] text-accent px-3 py-3 border border-accent bg-accent/5 hover:bg-accent/15 transition-colors"
            >
              Newsletter
            </Link>
          </nav>
        </div>
      )}
    </div>
  );
}
