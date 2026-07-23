"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/**
 * Nav link with active state: aria-current for assistive tech, accent
 * underline for sighted users (ARCH-08 — the nav previously gave no
 * orientation at all and forced full page reloads via raw <a> tags).
 */
export default function NavLink({
  href,
  children,
  className = "",
  activeClassName = "text-paper border-b border-accent",
  inactiveClassName = "text-muted hover:text-paper",
  onClick,
}: {
  href: string;
  children: React.ReactNode;
  className?: string;
  activeClassName?: string;
  inactiveClassName?: string;
  onClick?: () => void;
}) {
  const pathname = usePathname();
  const active = pathname === href;
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      onClick={onClick}
      className={`${className} ${active ? activeClassName : inactiveClassName}`}
    >
      {children}
    </Link>
  );
}
