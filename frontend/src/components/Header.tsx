import Link from "next/link";
import { AUTH_ENABLED, getSession } from "@/lib/auth";
import { isPublicMode } from "@/lib/publicMode";
import { PRIMARY_NAV, PLANS_NAV } from "@/lib/nav";
import NavLink from "./NavLink";
import ForesightMenu from "./ForesightMenu";
import MobileNav from "./MobileNav";

const LINK_CLASS =
  "font-mono text-[11px] uppercase tracking-[0.14em] px-3 py-1.5 transition-colors";

/**
 * Global header. Session-aware: with auth enabled it always offers a way in
 * (Sign in / Account) — previously the entire monetisation funnel was
 * unreachable from the navigation (ONB-02 / ARCH-05 / COPY-12).
 *
 * PUBLIC_MODE=1 (#93 Etappe 1) drops the Foresight menu, "Plans" and the
 * account links — those routes 404 (proxy.ts), so leaving the links up
 * would just be dead links. Unset/0 changes nothing.
 */
export default async function Header() {
  const publicMode = isPublicMode();
  const showAccount = AUTH_ENABLED && !publicMode;
  const session = showAccount ? await getSession() : null;

  return (
    <header className="border-b border-border">
      <div className="mx-auto max-w-7xl px-6 md:px-12 h-16 flex items-center justify-between gap-4">
        <Link href="/" className="group shrink-0" aria-label="Catandary home">
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
          {!publicMode && (
            <NavLink href={PLANS_NAV.href} className={LINK_CLASS}>
              {PLANS_NAV.label}
            </NavLink>
          )}
        </nav>

        <div className="hidden lg:flex items-center gap-2 shrink-0">
          {showAccount &&
            (session ? (
              <NavLink href="/account" className={LINK_CLASS}>
                Account
              </NavLink>
            ) : (
              <NavLink href="/account/signin" className={LINK_CLASS}>
                Sign in
              </NavLink>
            ))}
          <Link
            href="/trends/newsletter"
            className="font-mono text-[11px] uppercase tracking-[0.14em] text-accent px-3 py-1.5 border border-accent bg-accent/5 hover:bg-accent/15 transition-colors"
          >
            Newsletter
          </Link>
        </div>

        {/* Mobile nav (hamburger + drawer), < lg */}
        <MobileNav
          authEnabled={showAccount}
          signedIn={Boolean(session)}
          publicMode={publicMode}
        />
      </div>
    </header>
  );
}
