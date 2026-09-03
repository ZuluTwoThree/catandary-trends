import Link from "next/link";
import { linkPrefetch } from "@/lib/renderMode";
import { isPublicMode } from "@/lib/publicMode";
import { PRIMARY_NAV } from "@/lib/nav";
import NavLink from "./NavLink";
import ForesightMenu from "./ForesightMenu";
import MobileNav from "./MobileNav";

const LINK_CLASS =
  "font-mono text-[11px] uppercase tracking-[0.14em] px-3 py-1.5 transition-colors";

/**
 * Global header. Content nav + the Foresight menu + the newsletter CTA.
 *
 * PUBLIC_MODE=1 (#93) drops the Foresight menu — those routes 404 there
 * (proxy.ts), so leaving the links up would just be dead links. Unset/0 is
 * the owner instance and shows everything. Account/plan links are gone for
 * good (no SaaS since #93, 2026-09-03).
 */
export default function Header() {
  const publicMode = isPublicMode();

  return (
    <header className="border-b border-border">
      <div className="mx-auto max-w-7xl px-6 md:px-12 h-16 flex items-center justify-between gap-4">
        <Link prefetch={linkPrefetch()} href="/" className="group shrink-0" aria-label="Catandary home">
          <span className="font-display text-[22px] font-normal tracking-tight text-paper">
            Catandary<span className="text-accent">.</span>
          </span>
        </Link>

        {/* Desktop nav */}
        <nav aria-label="Main" className="hidden lg:flex items-center gap-1">
          {PRIMARY_NAV.map((item) => (
            <NavLink key={item.href} href={item.href} className={LINK_CLASS}>
              {item.label}
            </NavLink>
          ))}
          {!publicMode && <ForesightMenu />}
        </nav>

        <div className="hidden lg:flex items-center gap-2 shrink-0">
          <Link
            prefetch={linkPrefetch()}
            href="/trends/newsletter"
            className="font-mono text-[11px] uppercase tracking-[0.14em] text-accent px-3 py-1.5 border border-accent bg-accent/5 hover:bg-accent/15 transition-colors"
          >
            Newsletter
          </Link>
        </div>

        {/* Mobile nav (hamburger + drawer), < lg */}
        <MobileNav publicMode={publicMode} />
      </div>
    </header>
  );
}
