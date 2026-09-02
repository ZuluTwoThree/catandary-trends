"use client";

import Link from "next/link";
import { linkPrefetch } from "@/lib/renderMode";
import { useSearchParams } from "next/navigation";

/**
 * Pagination as real links (KEY-09: buttons with router.push allowed no
 * open-in-new-tab and no crawlable hrefs), inside a labelled nav landmark
 * with aria-current on the active page (A11Y-09).
 */
export default function Pagination({
  total,
  page,
  perPage,
}: {
  total: number;
  page: number;
  perPage: number;
}) {
  const searchParams = useSearchParams();
  const totalPages = Math.ceil(total / perPage);

  if (totalPages <= 1) return null;

  function hrefFor(p: number): string {
    const params = new URLSearchParams(searchParams.toString());
    if (p <= 1) params.delete("page");
    else params.set("page", String(p));
    const qs = params.toString();
    return `/trends${qs ? `?${qs}` : ""}`;
  }

  const base =
    "font-mono text-[10px] uppercase tracking-[0.14em] transition-colors";
  const enabled = "text-muted hover:text-paper hover:border-accent/40";
  const disabled = "opacity-30 pointer-events-none";

  const pages = Array.from({ length: totalPages }, (_, i) => i + 1)
    .filter((p) => p === 1 || p === totalPages || Math.abs(p - page) <= 2)
    .reduce<number[]>((acc, p) => {
      if (acc.length > 0 && p - acc[acc.length - 1] > 1) acc.push(-1);
      acc.push(p);
      return acc;
    }, []);

  return (
    <nav
      aria-label="Pagination"
      className="flex items-center justify-center gap-2 mt-12 pt-6 border-t border-border"
    >
      <Link
        prefetch={linkPrefetch()}
        href={hrefFor(page - 1)}
        aria-disabled={page <= 1 || undefined}
        tabIndex={page <= 1 ? -1 : undefined}
        className={`${base} px-3 py-2 border border-border ${page <= 1 ? disabled : enabled}`}
      >
        ← Previous
      </Link>

      <div className="flex items-center gap-1">
        {pages.map((p, i) =>
          p === -1 ? (
            <span
              key={`ellipsis-${i}`}
              className="px-2 font-mono text-[10px] text-muted"
              aria-hidden="true"
            >
              …
            </span>
          ) : (
            <Link
              prefetch={linkPrefetch()}
              key={p}
              href={hrefFor(p)}
              aria-current={p === page ? "page" : undefined}
              aria-label={`Page ${p}`}
              className={`${base} w-9 h-9 inline-flex items-center justify-center border ${
                p === page
                  ? "bg-accent text-ink border-accent"
                  : `border-border ${enabled}`
              }`}
            >
              {p}
            </Link>
          )
        )}
      </div>

      <Link
        prefetch={linkPrefetch()}
        href={hrefFor(page + 1)}
        aria-disabled={page >= totalPages || undefined}
        tabIndex={page >= totalPages ? -1 : undefined}
        className={`${base} px-3 py-2 border border-border ${
          page >= totalPages ? disabled : enabled
        }`}
      >
        Next →
      </Link>
    </nav>
  );
}
