import Link from "next/link";
import { isPublicMode } from "@/lib/publicMode";

const LINK = "hover:text-paper transition-colors";

/**
 * PUBLIC_MODE=1 (#93 Etappe 1) drops "Plans" — /trends/pricing 404s under
 * that flag (proxy.ts), so the link would otherwise be dead. Unset/0
 * changes nothing.
 */
export default function Footer() {
  const publicMode = isPublicMode();

  return (
    <footer className="border-t border-border mt-24">
      <div className="mx-auto max-w-7xl px-6 md:px-12 py-6 flex flex-col md:flex-row items-center justify-between gap-3">
        <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted flex flex-wrap items-center justify-center gap-x-4 gap-y-2">
          <span>&copy; {new Date().getFullYear()} Catandary</span>
          <Link href="/analysis" className={LINK}>
            Analyses
          </Link>
          <Link href="/trends/methodology" className={LINK}>
            How we measure
          </Link>
          {!publicMode && (
            <Link href="/trends/pricing" className={LINK}>
              Plans
            </Link>
          )}
          <Link href="/trends/newsletter" className={LINK}>
            Newsletter
          </Link>
          <Link href="/imprint" className={LINK}>
            Imprint
          </Link>
          <Link href="/privacy" className={LINK}>
            Privacy
          </Link>
        </span>
        <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
          Powered by{" "}
          <a
            href="https://catandary.de"
            target="_blank"
            rel="noopener noreferrer"
            className="text-accent hover:underline"
          >
            Catandary Foresight ↗
          </a>
        </span>
      </div>
    </footer>
  );
}
