import Link from "next/link";
import { VERTICALS, type Vertical } from "@/lib/types";
import { listingPath } from "@/lib/staticListing";
import { linkPrefetch } from "@/lib/renderMode";

/**
 * Filter bar of the STATIC listing (design Schritt 4): the one dimension
 * that exists as pre-rendered pages — the vertical — as plain links, in the
 * look of VerticalsMultiFilter. Everything else (search, PESTEL, theme) is
 * the client-side search over /trends/index.json, rendered into the
 * `children` slot (Schritt 5). The search-param FilterBar of the
 * workstation feed is untouched.
 */
export default function StaticFilterBar({
  active,
  counts,
  children,
}: {
  active: Vertical | null;
  /** Published count per vertical inside the public window. */
  counts: Record<string, number>;
  children?: React.ReactNode;
}) {
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  const chip =
    "font-mono text-[10px] uppercase tracking-[0.1em] px-4 py-2 flex items-center gap-2 transition-colors";
  const idle = "text-muted hover:text-paper hover:bg-white/[0.02]";

  return (
    <section aria-label="Trend filters" className="space-y-3">
      {children}
      <nav
        aria-label="Vertical"
        className="flex flex-wrap items-stretch border border-border"
      >
        <div className="font-mono text-[9px] uppercase tracking-[0.22em] text-muted px-4 flex items-center border-r border-border whitespace-nowrap">
          Vertical ——
        </div>
        <Link
          prefetch={linkPrefetch()}
          href={listingPath(null, 1)}
          aria-current={active === null ? "page" : undefined}
          className={`${chip} border-r border-border ${
            active === null ? "text-accent bg-accent/5" : idle
          }`}
        >
          <span>All</span>
          <span className="text-[9px] opacity-60 tabular-nums">{total}</span>
        </Link>
        {VERTICALS.map((v, idx) => {
          const count = counts[v.id] ?? 0;
          const isActive = active === v.id;
          if (count === 0 && !isActive) return null;
          const isLast = idx === VERTICALS.length - 1;
          return (
            <Link
              prefetch={linkPrefetch()}
              key={v.id}
              href={listingPath(v.id, 1)}
              aria-current={isActive ? "page" : undefined}
              className={`${chip} ${!isLast ? "border-r border-border" : ""} ${
                isActive ? "bg-white/[0.04]" : idle
              }`}
              style={isActive ? { color: v.color } : undefined}
            >
              <span
                className="inline-block w-[8px] h-[3px]"
                style={{ backgroundColor: v.color, opacity: isActive ? 1 : 0.5 }}
                aria-hidden="true"
              />
              <span>{v.code}</span>
              <span className="text-[9px] opacity-60 tabular-nums">{count}</span>
            </Link>
          );
        })}
      </nav>
    </section>
  );
}
